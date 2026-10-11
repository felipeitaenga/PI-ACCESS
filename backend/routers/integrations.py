"""Configuração MQTT, tokens do agente local e API usada pelo nx-access-agent."""
import asyncio
import hashlib
import secrets
from fastapi import APIRouter, Depends, HTTPException, Request
from database import db
from security import require_role, encrypt_secret, decrypt_secret
from models import new_id, now_iso
from mqtt_bus import bus, probe
from beward_ingest import controller_by_device, heartbeat, record
from util import log_audit, client_ip

router = APIRouter(tags=["integrations"])
ADMIN = require_role("admin")


# ---------- MQTT ----------
@router.get("/integrations/mqtt")
async def get_mqtt(user: dict = Depends(ADMIN)):
    s = await db.settings.find_one({"id": "mqtt"}, {"_id": 0, "password_enc": 0}) or {}
    return {"config": s, "status": bus.status()}


@router.put("/integrations/mqtt")
async def put_mqtt(body: dict, request: Request, user: dict = Depends(ADMIN)):
    upd = {k: body.get(k) for k in ("host", "port", "username", "client_id", "enabled") if k in body}
    if body.get("password"):
        upd["password_enc"] = encrypt_secret(body["password"])
    if body.get("clear_password"):
        upd["password_enc"] = ""
    await db.settings.update_one({"id": "mqtt"}, {"$set": upd}, upsert=True)
    await log_audit(user, "editar", "settings", "mqtt", f"MQTT {upd.get('host')}:{upd.get('port')}", client_ip(request))
    await bus.start()
    await asyncio.sleep(1.5)
    return {"ok": True, "status": bus.status()}


@router.post("/integrations/mqtt/test")
async def test_mqtt(body: dict, user: dict = Depends(ADMIN)):
    s = await db.settings.find_one({"id": "mqtt"}, {"_id": 0}) or {}
    host = body.get("host") or s.get("host")
    port = body.get("port") or s.get("port") or 1883
    pwd = body.get("password") or decrypt_secret(s.get("password_enc", ""))
    if not host:
        raise HTTPException(status_code=400, detail="Informe o endereço do broker")
    return await probe(host, port, body.get("username", s.get("username", "")), pwd)


@router.get("/integrations/mqtt/log")
async def mqtt_log(user: dict = Depends(require_role("admin", "operator"))):
    return {"status": bus.status(), "messages": list(bus.log)}


# ---------- Tokens do agente (por site) ----------
def _hash(t):
    return hashlib.sha256(t.encode()).hexdigest()


@router.get("/agents")
async def list_agents(site_id: str = "", user: dict = Depends(ADMIN)):
    q = {"revoked": {"$ne": True}, **({"site_id": site_id} if site_id else {})}
    return await db.agent_tokens.find(q, {"_id": 0, "token_hash": 0}).sort("created_at", -1).to_list(50)


@router.post("/agents")
async def new_agent(body: dict, request: Request, user: dict = Depends(ADMIN)):
    site_id = body.get("site_id")
    if not site_id:
        raise HTTPException(status_code=400, detail="Selecione o site da controladora")
    await db.agent_tokens.update_many({"site_id": site_id, "revoked": {"$ne": True}}, {"$set": {"revoked": True, "revoked_at": now_iso()}})
    token = "nxa_" + secrets.token_urlsafe(32)
    doc = {"id": new_id(), "site_id": site_id, "token_hash": _hash(token), "prefix": token[:10], "created_at": now_iso(),
           "created_by": user.get("email"), "last_used_at": None, "last_ip": None, "revoked": False}
    await db.agent_tokens.insert_one(dict(doc))
    await log_audit(user, "gerar", "agent_token", doc["id"], f"site {site_id}", client_ip(request))
    doc.pop("token_hash")
    return {**doc, "token": token}


@router.post("/agents/{aid}/revoke")
async def revoke_agent(aid: str, request: Request, user: dict = Depends(ADMIN)):
    await db.agent_tokens.update_one({"id": aid}, {"$set": {"revoked": True, "revoked_at": now_iso()}})
    await log_audit(user, "revogar", "agent_token", aid, "", client_ip(request))
    return {"ok": True}


async def agent_auth(request: Request):
    auth = request.headers.get("authorization", "")
    tok = auth[7:] if auth.lower().startswith("bearer ") else ""
    a = await db.agent_tokens.find_one({"token_hash": _hash(tok), "revoked": {"$ne": True}}, {"_id": 0}) if tok else None
    if not a:
        raise HTTPException(status_code=401, detail="Token do agente inválido ou revogado")
    ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "")).split(",")[0].strip()
    await db.agent_tokens.update_one({"id": a["id"]}, {"$set": {"last_used_at": now_iso(), "last_ip": ip}})
    return a


# ---------- API do agente ----------
@router.get("/agent/config")
async def agent_config(agent: dict = Depends(agent_auth)):
    ctrls = await db.controllers.find({"site_id": agent["site_id"], "deleted": {"$ne": True}, "brand": "beward_http"},
                                      {"_id": 0}).to_list(200)
    return {"site_id": agent["site_id"], "devices": [
        {"controller_id": c["id"], "name": c["name"], "device_id": c.get("beward_device_id"), "ip": c.get("ip"),
         "port": c.get("port") or 80, "username": c.get("username", "admin"),
         "password": decrypt_secret(c.get("password_enc", "")), "decision_mode": c.get("decision_mode", "servidor")}
        for c in ctrls]}


def _rec_from_http(b):
    return {"person_ref": b.get("PersonUUID") or b.get("PersonID"), "name": b.get("Name"),
            "verify_status": b.get("VerifyStatus"), "verify_type": b.get("VerfyType") or b.get("VerifyType"),
            "sendintime": b.get("Sendintime", 1), "direction": b.get("Direction"),
            "record_id": b.get("RecordID") or b.get("CreateTime"), "time": b.get("CreateTime"),
            "pic": b.get("SanpPic") or b.get("SnapPic") or "", "similarity": b.get("Similarity1", 0)}


@router.post("/agent/events/{kind}")
async def agent_event(kind: str, body: dict, agent: dict = Depends(agent_auth)):
    payload = body.get("payload") or {}
    info = payload.get("info") if isinstance(payload.get("info"), dict) else payload
    dev = str(body.get("device_id") or info.get("DeviceID") or "")
    ok = {"code": 200, "desc": "OK"}
    ctrl = await controller_by_device(dev)
    if not ctrl or ctrl.get("site_id") != agent["site_id"]:
        return {**ok, "warning": f"DeviceID {dev} não cadastrado neste site"}
    k = kind.lower()
    if k == "heartbeat":
        await heartbeat(dev, True, info.get("IP") or info.get("ip"))
        return ok
    await heartbeat(dev, True)
    if k in ("verify", "verifywithsnap"):
        r = _rec_from_http(info)
        if body.get("queued"):
            r["sendintime"] = 0
        res = await record(ctrl, r, "http")
        if res.get("decided_online"):
            return {**ok, "openDoor": 1 if res["granted"] else 0, "showInfo": res["show"]}
        return ok
    if k == "alarm":
        from drivers.beward_common import ALARM_CODES
        from beward_ingest import raise_alarm
        atype, msg, prio = ALARM_CODES.get(int(info.get("AlarmCode") or info.get("code") or 0), ("alarme", "Alarme Beward", "media"))
        await raise_alarm(ctrl, atype, msg, prio)
    return ok


@router.get("/agent/commands")
async def agent_commands(wait: int = 20, agent: dict = Depends(agent_auth)):
    ids = [c["id"] for c in await db.controllers.find({"site_id": agent["site_id"]}, {"_id": 0, "id": 1}).to_list(500)]
    for _ in range(max(1, min(wait, 25)) * 2):
        cmds = await db.agent_commands.find({"controller_id": {"$in": ids}, "status": "pending"}, {"_id": 0}).to_list(20)
        if cmds:
            await db.agent_commands.update_many({"id": {"$in": [c["id"] for c in cmds]}}, {"$set": {"status": "dispatched", "dispatched_at": now_iso()}})
            return cmds
        await asyncio.sleep(0.5)
    return []


@router.post("/agent/commands/{cid}/result")
async def agent_command_result(cid: str, body: dict, agent: dict = Depends(agent_auth)):
    await db.agent_commands.update_one({"id": cid}, {"$set": {"status": "done", "result": body, "done_at": now_iso()}})
    return {"ok": True}


async def run_via_agent(ctrl, operator, info, timeout=15):
    """Usado pelo driver HTTP: enfileira o comando para o agente local e aguarda o resultado."""
    cmd = {"id": new_id(), "controller_id": ctrl["id"], "ip": ctrl.get("ip"), "port": ctrl.get("port") or 80,
           "operator": operator, "info": info or {}, "status": "pending", "created_at": now_iso()}
    await db.agent_commands.insert_one(dict(cmd))
    for _ in range(timeout * 4):
        await asyncio.sleep(0.25)
        c = await db.agent_commands.find_one({"id": cmd["id"]}, {"_id": 0})
        if c and c["status"] == "done":
            r = c.get("result") or {}
            data = r.get("body") or {}
            code = data.get("code", r.get("http_status", 0))
            return {"ok": code == 200, "code": code, "detail": (data.get("info") or {}).get("Detail", "") or r.get("error", ""),
                    "info": data.get("info", {})}
    await db.agent_commands.update_one({"id": cmd["id"], "status": "pending"}, {"$set": {"status": "expired"}})
    return {"ok": False, "code": 0, "detail": "Agente local não respondeu — verifique se o nx-access-agent está rodando", "info": {}}

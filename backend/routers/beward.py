"""Recebimento de eventos BEWARD (HTTP Subscribe) + decisão online + imagem pública de face."""
import base64
import logging
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Request, Depends
from fastapi.responses import Response, RedirectResponse
from database import db
from security import get_current_user, require_role
from realtime import manager
from access_service import evaluate
from drivers.factory import get_driver
from drivers.beward_common import map_verify, dedup_key, ALARM_CODES
from beward_faces import make_face_token, decode_face_token
from models import new_id, now_iso
from app_config import PUBLIC_URL
from scope import stamp_event
import os

logger = logging.getLogger(__name__)
router = APIRouter(tags=["beward"])
OK = {"code": 200, "desc": "OK"}


async def _seen(key):
    if not key:
        return False
    if await db.beward_dedup.find_one({"_id": key}):
        return True
    await db.beward_dedup.insert_one({"_id": key, "at": datetime.now(timezone.utc)})
    return False


async def _controller_by_device(device_id):
    return await db.controllers.find_one(
        {"$or": [{"beward_device_id": device_id}, {"beward_device_id": str(device_id)}]}, {"_id": 0})


async def _access_point_for(ctrl):
    if not ctrl:
        return None
    return await db.access_points.find_one(
        {"controller_id": ctrl["id"], "direction": "entrada", "deleted": {"$ne": True}}, {"_id": 0})


# ---------- Imagem pública de face (picURI com token assinado) ----------
@router.get("/public/faces/{token}.jpg")
async def public_face(token: str):
    pid = decode_face_token(token)
    if not pid:
        return Response(status_code=403)
    person = await db.people.find_one({"id": pid}, {"_id": 0, "photo": 1})
    photo = (person or {}).get("photo", "")
    if photo.startswith("data:"):
        try:
            return Response(content=base64.b64decode(photo.split(",", 1)[-1]), media_type="image/jpeg")
        except Exception:
            return Response(status_code=404)
    if photo.startswith("http"):
        return RedirectResponse(photo)
    return Response(status_code=404)


# ---------- Webhooks de assinatura (por site) ----------
@router.post("/beward/{site}/heartbeat")
async def hb(site: str, request: Request):
    body = await request.json()
    did = body.get("DeviceID")
    ctrl = await _controller_by_device(did)
    if ctrl:
        await db.controllers.update_one({"id": ctrl["id"]}, {"$set": {"online": True, "last_heartbeat": now_iso()}})
    return OK


@router.post("/beward/{site}/verify")
async def verify(site: str, request: Request):
    body = await request.json()
    did = body.get("DeviceID")
    m = map_verify(body.get("VerifyStatus"), body.get("VerfyType"), body.get("Sendintime", 1))
    key = dedup_key(did, body.get("CreateTime"), body.get("PersonID") or body.get("PersonUUID"))
    duplicate = await _seen(key)

    ctrl = await _controller_by_device(did)
    ap = await _access_point_for(ctrl)
    person = await db.people.find_one({"id": body.get("PersonUUID")}, {"_id": 0})

    captured = body.get("SanpPic") or body.get("SnapPic") or ""
    if captured and not captured.startswith("data:"):
        captured = f"data:image/jpeg;base64,{captured}"

    decision_mode = (ctrl or {}).get("decision_mode", "servidor")
    online = decision_mode == "servidor" and not m["retroactive"] and not duplicate and person and ap

    if online:
        res = await evaluate(person, ap, persist=True)
        ev = res["event"]
        ev["captured_photo"] = captured or ev.get("captured_photo", "")
        await manager.broadcast({"type": "access_event", "data": ev})
        show = (f"{person.get('name')}, acesso liberado" if res["granted"]
                else f"Acesso negado: {res['reason']}")[:64]
        return {**OK, "openDoor": 1 if res["granted"] else 0, "showInfo": show}

    # Modos local / retroativo / duplicado: apenas registra, não reabre a porta
    if not duplicate:
        ev = {"id": new_id(), "timestamp": now_iso(), "site_id": (ctrl or {}).get("site_id"),
              "site_name": (ctrl or {}).get("site_name", ""),
              "area_id": (ap or {}).get("dest_area_id"), "area_name": (ap or {}).get("dest_area_name", ""),
              "door_id": (ap or {}).get("id"), "door_name": (ap or {}).get("description", "Facial Beward"),
              "controller_id": (ctrl or {}).get("id"), "device_id": (ctrl or {}).get("id"),
              "person_id": body.get("PersonUUID"), "person_name": body.get("Name", "Desconhecido"),
              "person_photo": (person or {}).get("photo", ""), "captured_photo": captured,
              "credential_type": m["verify_type"], "direction": {1: "entrada", 2: "saida"}.get(body.get("Direction"), "entrada"),
              "access_result": m["access_result"], "reason": m["reason"] + (" (retroativo)" if m["retroactive"] else ""),
              "match_score": body.get("Similarity1", 0)}
        await db.access_events.insert_one(dict(await stamp_event(ev))); ev.pop("_id", None)
        await manager.broadcast({"type": "access_event", "data": ev})
    return OK


@router.post("/beward/{site}/{topic}")
async def generic_topic(site: str, topic: str, request: Request):
    body = await request.json()
    if topic == "alarm":
        code = int(body.get("AlarmCode") or body.get("code") or 0)
        atype, msg, prio = ALARM_CODES.get(code, ("alarme", "Alarme Beward", "media"))
        ctrl = await _controller_by_device(body.get("DeviceID"))
        alarm = {"id": new_id(), "timestamp": now_iso(), "type": atype, "message": msg, "priority": prio,
                 "site_id": (ctrl or {}).get("site_id"), "site_name": (ctrl or {}).get("site_name", ""),
                 "door_id": (ctrl or {}).get("id"), "door_name": (ctrl or {}).get("name", "Facial Beward"),
                 "acknowledged": False, "ack_by": None, "comment": ""}
        await db.alarms.insert_one(dict(alarm)); alarm.pop("_id", None)
        await manager.broadcast({"type": "alarm", "data": alarm})
    return OK


# ---------- Operações da controladora Beward ----------
@router.post("/beward/controllers/{cid}/subscribe")
async def do_subscribe(cid: str, user: dict = Depends(require_role("admin", "operator"))):
    ctrl = await db.controllers.find_one({"id": cid}, {"_id": 0})
    if not ctrl:
        return {"ok": False, "detail": "Controladora não encontrada"}
    site = ctrl.get("site_id")
    base = PUBLIC_URL
    driver = get_driver(ctrl)
    payload = {"DeviceID": ctrl.get("beward_device_id"), "Num": 1,
               "Topics": ["Snap", "VerifyWithSnap", "Card", "QRCode", "Alarm"],
               "SubscribeAddr": base,
               "SubscribeUrl": {"Verify": f"/api/beward/{site}/verify", "HeartBeat": f"/api/beward/{site}/heartbeat",
                                "Snap": f"/api/beward/{site}/snap", "Card": f"/api/beward/{site}/card",
                                "QRCode": f"/api/beward/{site}/qrcode", "PassWord": f"/api/beward/{site}/password",
                                "Alarm": f"/api/beward/{site}/alarm"},
               "BeatInterval": 30, "Auth": "Basic", "User": ctrl.get("username"), "Passwd": "***"}
    r = await driver.subscribe(payload)
    return {"ok": r.get("ok", False), "payload": payload, "result": r}


@router.post("/beward/controllers/{cid}/sync-strategies")
async def sync_strategies(cid: str, user: dict = Depends(require_role("admin", "operator"))):
    """Sincroniza faixas horárias -> AccessStrategy e vincula pessoas (substituição total)."""
    ctrl = await db.controllers.find_one({"id": cid}, {"_id": 0})
    if not ctrl:
        return {"ok": False, "detail": "não encontrada"}
    driver = get_driver(ctrl)
    trs = await db.time_ranges.find({"deleted": {"$ne": True}}, {"_id": 0}).to_list(200)
    hols = await db.holidays.find({"deleted": {"$ne": True}}, {"_id": 0}).to_list(500)
    ap = await _access_point_for(ctrl)
    log = []
    for tr in trs:
        r = await driver.add_strategy(tr, hols)
        log.append({"cmd": "AddAccessStrategy", "strategy": tr.get("description"), "code": r.get("code"), "detail": r.get("detail")})
    # vincular pessoas conforme categorias que contêm a área de destino do ponto
    from drivers.beward_common import strategy_id_for
    dest = (ap or {}).get("dest_area_id")
    people = await db.people.find({"status": "ativo", "deleted": {"$ne": True}}, {"_id": 0}).to_list(2000)
    bound = 0
    for p in people:
        cats = await db.categories.find({"id": {"$in": p.get("category_ids", [])}, "enabled": True}, {"_id": 0}).to_list(50)
        sids = {strategy_id_for(cfg["time_range_id"]) for c in cats for cfg in c.get("access_areas", [])
                if cfg.get("area_id") == dest and cfg.get("time_range_id")}
        if sids:
            await driver.bind_person_strategies(p["id"], sids)
            bound += 1
    job = {"id": new_id(), "controller_id": cid, "device_id": cid, "device_name": ctrl["name"],
           "started_at": now_iso(), "finished_at": now_iso(), "status": "concluido",
           "totals": {"time_zones": len(trs), "areas": 0, "portals": 1 if ap else 0, "access_rules": len(trs), "people": bound},
           "total": bound, "success": bound, "errors": [], "log": log}
    await db.sync_jobs.insert_one(dict(job))
    return {"ok": True, "strategies": len(trs), "people_bound": bound}

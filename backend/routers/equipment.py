from fastapi import APIRouter, Depends, HTTPException, Request
from database import db
from security import get_current_user, require_role, encrypt_secret
from crud import make_crud
from drivers.factory import get_driver
from models import new_id, now_iso
from realtime import manager
from util import log_audit, client_ip

router = APIRouter(prefix="/equipment", tags=["equipment"])


async def _ctrl_enrich(doc):
    pwd = doc.pop("password", None)
    if pwd:
        doc["password_enc"] = encrypt_secret(pwd)
    if doc.get("site_id"):
        s = await db.sites.find_one({"id": doc["site_id"]}, {"_id": 0})
        doc["site_name"] = s["name"] if s else ""
    doc.setdefault("brand", "simulado")
    doc.setdefault("online", True)
    return doc


async def _ap_enrich(doc):
    c = await db.controllers.find_one({"id": doc.get("controller_id")}, {"_id": 0})
    if c:
        doc["controller_name"] = c.get("name", "")
        doc["site_id"] = c.get("site_id")
        s = await db.sites.find_one({"id": c.get("site_id")}, {"_id": 0})
        doc["site_name"] = s["name"] if s else ""
    o = await db.areas.find_one({"id": doc.get("origin_area_id")}, {"_id": 0})
    doc["origin_area_name"] = o["description"] if o else ""
    d = await db.areas.find_one({"id": doc.get("dest_area_id")}, {"_id": 0})
    doc["dest_area_name"] = d["description"] if d else ""
    return doc


make_crud(router, "/controllers", "controllers", search_fields=["name", "ip", "model"], sort="name", enrich=_ctrl_enrich)
make_crud(router, "/access-points", "access_points", search_fields=["description"], sort="description", enrich=_ap_enrich)


@router.post("/controllers/{cid}/test")
async def test_controller(cid: str, user: dict = Depends(get_current_user)):
    ctrl = await db.controllers.find_one({"id": cid}, {"_id": 0})
    if not ctrl:
        raise HTTPException(status_code=404, detail="Controladora não encontrada")
    driver = get_driver(ctrl)
    ok = await driver.connect()
    status = await driver.get_status()
    info = await driver.get_device_info()
    await db.controllers.update_one({"id": cid}, {"$set": {"online": ok, "firmware": info.get("firmware", ""), "last_heartbeat": now_iso()}})
    return {"ok": ok, "status": status, "info": info}


@router.post("/controllers/{cid}/sync")
async def sync_controller(cid: str, request: Request, user: dict = Depends(require_role("admin", "operator"))):
    ctrl = await db.controllers.find_one({"id": cid}, {"_id": 0})
    if not ctrl:
        raise HTTPException(status_code=404, detail="Controladora não encontrada")
    driver = get_driver(ctrl)
    await driver.connect()
    trs = await db.time_ranges.find({"deleted": {"$ne": True}}, {"_id": 0}).to_list(200)
    areas = await db.areas.find({"deleted": {"$ne": True}}, {"_id": 0}).to_list(200)
    aps = await db.access_points.find({"controller_id": cid, "deleted": {"$ne": True}}, {"_id": 0}).to_list(100)
    cats = await db.categories.find({"enabled": True, "deleted": {"$ne": True}}, {"_id": 0}).to_list(200)
    people = await db.people.find({"status": "ativo", "deleted": {"$ne": True}}, {"_id": 0}).to_list(2000)
    job = {"id": new_id(), "controller_id": cid, "device_id": cid, "device_name": ctrl["name"],
           "started_at": now_iso(), "status": "concluido",
           "totals": {"time_zones": len(trs), "areas": len(areas), "portals": len(aps),
                      "access_rules": len(cats), "people": len(people)},
           "total": len(people), "success": 0, "errors": []}
    await driver.sync_access_rules()
    for p in people:
        r = await driver.sync_person(p)
        if r.get("ok"):
            job["success"] += 1
            if p.get("photo"):
                await driver.sync_face(p["id"], p["photo"])
        else:
            job["errors"].append({"person_id": p["id"], "name": p.get("name"), "error": "falha"})
    job["finished_at"] = now_iso()
    await db.sync_jobs.insert_one(dict(job))
    job.pop("_id", None)
    await log_audit(user, "sincronizar", "controllers", cid,
                    f"TZ:{len(trs)} Áreas:{len(areas)} Pontos:{len(aps)} Regras:{len(cats)} Pessoas:{job['success']}/{len(people)}",
                    client_ip(request))
    return job


@router.get("/sync-jobs")
async def list_sync_jobs(user: dict = Depends(get_current_user)):
    return await db.sync_jobs.find({}, {"_id": 0}).sort("started_at", -1).limit(50).to_list(50)


@router.post("/access-points/{apid}/open")
async def open_point(apid: str, body: dict, request: Request,
                     user: dict = Depends(require_role("admin", "operator", "reception"))):
    ap = await db.access_points.find_one({"id": apid}, {"_id": 0})
    if not ap:
        raise HTTPException(status_code=404, detail="Ponto de acesso não encontrado")
    ctrl = await db.controllers.find_one({"id": ap.get("controller_id")}, {"_id": 0})
    driver = get_driver(ctrl or {"brand": "simulado"})
    await driver.open_door(apid, int(body.get("seconds", 5)))
    dest = await db.areas.find_one({"id": ap.get("dest_area_id")}, {"_id": 0}) or {}
    event = {"id": new_id(), "timestamp": now_iso(), "site_id": ap.get("site_id"), "site_name": ap.get("site_name", ""),
             "area_id": dest.get("id"), "area_name": dest.get("description", ""),
             "door_id": apid, "door_name": ap.get("description"), "access_point_id": apid,
             "controller_id": ap.get("controller_id"), "device_id": ap.get("controller_id"),
             "person_id": None, "person_name": f"Abertura remota — {user.get('name')}",
             "person_photo": "", "captured_photo": "", "credential_type": "remoto",
             "direction": ap.get("direction", "entrada"), "access_result": "granted",
             "reason": body.get("reason") or "Abertura remota pelo operador", "match_score": 100.0}
    await db.access_events.insert_one(dict(event))
    event.pop("_id", None)
    await manager.broadcast({"type": "access_event", "data": event})
    await log_audit(user, "abrir_ponto", "access_points", apid, f"{ap.get('description')} ({body.get('reason','')})", client_ip(request))
    return {"ok": True, "event": event}


@router.post("/access-points/{apid}/mode")
async def set_point_mode(apid: str, body: dict, request: Request,
                         user: dict = Depends(require_role("admin", "operator"))):
    mode = body.get("mode")
    if mode not in ("normal", "liberada", "bloqueada"):
        raise HTTPException(status_code=400, detail="Modo inválido")
    await db.access_points.update_one({"id": apid}, {"$set": {"mode": mode}})
    await log_audit(user, "modo_ponto", "access_points", apid, f"-> {mode}", client_ip(request))
    await manager.broadcast({"type": "door_mode", "data": {"door_id": apid, "mode": mode}})
    return {"ok": True, "mode": mode}

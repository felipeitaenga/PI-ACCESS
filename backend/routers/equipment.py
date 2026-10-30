import asyncio
from fastapi import APIRouter, Depends, HTTPException, Request
from database import db
from scope import stamp_event
from security import get_current_user, require_role, encrypt_secret
from crud import make_crud
from drivers.factory import get_driver
import device_catalog as catalog
from models import new_id, now_iso
from realtime import manager
from util import log_audit, client_ip

router = APIRouter(prefix="/equipment", tags=["equipment"])


MODEL_TYPES = {
    "simulado": {"label": "Simulado (demonstração)", "max": 8, "point_type": "catraca"},
    "beward_facial": {"label": "Facial Beward", "max": 1, "point_type": "facial"},
    "hikvision_facial": {"label": "Facial Hikvision", "max": 1, "point_type": "facial", "brand": "hikvision"},
    "controlid_facial": {"label": "Facial Control iD", "max": 1, "point_type": "facial", "brand": "controlid"},
    "intelbras_facial": {"label": "Facial Intelbras", "max": 1, "point_type": "facial", "brand": "intelbras"},
    "ct300_2l": {"label": "CT300-2L", "max": 2, "point_type": "catraca", "brand": "ct300"},
}
POINT_FIELDS = ["passage_mode", "passage_timeout", "notify_not_passed", "unauthorized_alarm", "unauthorized_priority", "sensor_type",
                "description", "type", "origin_area_id", "dest_area_id", "direction", "relay_time",
                "door_open_time", "door_sensor", "button", "camera_id"]


def _brand_for(doc):
    mt = doc.get("model_type")
    if mt == "beward_facial":
        return "beward_mqtt" if doc.get("transport") == "mqtt" else "beward_http"
    return MODEL_TYPES[mt].get("brand", mt)


async def _save_points(ctrl, points):
    n = ctrl["num_access_points"]
    areas = {a["id"]: a.get("description") or a.get("name", "") for a in await db.areas.find({}, {"_id": 0, "id": 1, "description": 1, "name": 1}).to_list(1000)}
    existing = {p["id"]: p for p in await db.access_points.find({"controller_id": ctrl["id"], "deleted": {"$ne": True}}, {"_id": 0}).to_list(50)}
    kept = []
    for i in range(n):
        data = points[i] if i < len(points) else {}
        doc = {k: data[k] for k in POINT_FIELDS if k in data}
        doc.setdefault("type", MODEL_TYPES[ctrl["model_type"]]["point_type"])
        doc.setdefault("description", f"{ctrl['name']} - Ponto {i + 1}")
        doc.setdefault("direction", "entrada")
        doc.update({"controller_id": ctrl["id"], "controller_name": ctrl["name"], "site_id": ctrl.get("site_id"),
                    "site_name": ctrl.get("site_name", ""), "reader": i + 1, "relay": i + 1,
                    "origin_area_name": areas.get(doc.get("origin_area_id"), ""),
                    "dest_area_name": areas.get(doc.get("dest_area_id"), "")})
        pid = data.get("id")
        if pid in existing:
            await db.access_points.update_one({"id": pid}, {"$set": doc})
        else:
            pid = new_id()
            await db.access_points.insert_one({**doc, "id": pid, "enabled": True, "deleted": False, "mode": "normal",
                                               "relay_time": doc.get("relay_time", 5), "door_open_time": doc.get("door_open_time", 20),
                                               "created_at": now_iso()})
        kept.append(pid)
    gone = [pid for pid in existing if pid not in kept]
    if gone:
        await db.access_points.update_many({"id": {"$in": gone}}, {"$set": {"deleted": True, "enabled": False}})


async def _ctrl_enrich(doc):
    pwd = doc.pop("password", None)
    if pwd:
        doc["password_enc"] = encrypt_secret(pwd)
    if doc.get("site_id"):
        s = await db.sites.find_one({"id": doc["site_id"]}, {"_id": 0})
        doc["site_name"] = s["name"] if s else ""
    # catálogo fabricante/modelo (cadastros antigos só têm model_type → modelo padrão da família)
    cm = catalog.BY_ID.get(doc.get("catalog_model") or "")
    if doc.get("catalog_model") and not cm:
        raise HTTPException(status_code=422, detail="Modelo de controladora desconhecido")
    if cm and doc.get("model_type") not in MODEL_TYPES:
        doc["model_type"] = cm["family"]
    if doc.get("model_type") not in MODEL_TYPES:
        doc["model_type"] = "beward_facial" if str(doc.get("brand", "")).startswith("beward") else "simulado"
    if not cm or cm["family"] != doc["model_type"]:
        cm = catalog.resolve({"model_type": doc["model_type"]})
    if cm["status"] == "em_breve":
        raise HTTPException(status_code=422, detail=f"{catalog.MANUFACTURER_NAME[cm['manufacturer']]} {cm['name']}: integração ainda não disponível")
    doc.update({"catalog_model": cm["id"], "manufacturer": cm["manufacturer"], "model_type": cm["family"]})
    mt = MODEL_TYPES[doc["model_type"]]
    doc["brand"] = _brand_for(doc)
    doc["model"] = f"{catalog.MANUFACTURER_NAME[cm['manufacturer']]} {cm['name']}" if cm["manufacturer"] != "simulado" else cm["name"]
    doc["num_access_points"] = max(1, min(int(doc.get("num_access_points") or 1), mt["max"], cm["max_points"]))
    for k in ("num_readers", "num_relays"):
        doc.pop(k, None)
    doc.setdefault("online", True)
    points = doc.pop("access_points", None)
    if points is not None:
        await _save_points(doc, points)
    return doc


async def _ap_enrich(doc):
    c = await db.controllers.find_one({"id": doc.get("controller_id")}, {"_id": 0})
    if c:
        doc["controller_name"] = c.get("name", "")
        doc["site_id"] = c.get("site_id")
        s = await db.sites.find_one({"id": c.get("site_id")}, {"_id": 0})
        doc["site_name"] = s["name"] if s else ""
    o = await db.areas.find_one({"id": doc.get("origin_area_id")}, {"_id": 0})
    doc["origin_area_name"] = (o.get("description") or o.get("name", "")) if o else ""
    d = await db.areas.find_one({"id": doc.get("dest_area_id")}, {"_id": 0})
    doc["dest_area_name"] = (d.get("description") or d.get("name", "")) if d else ""
    return doc


async def _ctrl_deleted(ids):
    await db.access_points.update_many({"controller_id": {"$in": ids}}, {"$set": {"deleted": True, "enabled": False}})


make_crud(router, "/controllers", "controllers", search_fields=["name", "ip", "model"], sort="name", enrich=_ctrl_enrich, hidden=("intelbras_token",),
          on_delete=_ctrl_deleted)
make_crud(router, "/access-points", "access_points", search_fields=["description"], sort="description", enrich=_ap_enrich)


@router.get("/model-types")
async def model_types(user: dict = Depends(get_current_user)):
    return MODEL_TYPES


@router.get("/catalog")
async def device_catalog(user: dict = Depends(get_current_user)):
    """Fabricantes e modelos suportados, com recursos e status (homologado / em teste / em breve)."""
    return catalog.catalog()


@router.get("/controllers/{cid}/access-points")
async def controller_points(cid: str, user: dict = Depends(get_current_user)):
    return await db.access_points.find({"controller_id": cid, "deleted": {"$ne": True}}, {"_id": 0}).sort("reader", 1).to_list(50)


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
    clock = None
    if ok and ctrl.get("model_type") == "beward_facial":
        from beward_ingest import sync_time
        clock = await sync_time(ctrl, force=True)
    if ok and ctrl.get("brand") == "intelbras":
        from intelbras_ingest import sync_time as ib_sync_time
        clock = await ib_sync_time(ctrl)
    return {"ok": ok, "status": status, "info": info, "clock": clock}


async def _remove_stale(driver, keep_ids, job):
    """Tira do facial quem não deveria estar lá: fixos excluídos/inativos e visitantes sem visita ativa.
    (Até a 1.6.4 a exclusão no facial não funcionava, então podem ter sobrado cadastros antigos.)"""
    from visits_core import ACTIVE
    active_vis = await db.visits.distinct("visitor_id", {"deleted": {"$ne": True}, "status": {"$in": list(ACTIVE)}})
    stale = [p["id"] async for p in db.people.find({"$or": [{"deleted": True}, {"status": {"$ne": "ativo"}}]}, {"_id": 0, "id": 1})]
    stale += [v["id"] async for v in db.visitors.find({"id": {"$nin": active_vis}}, {"_id": 0, "id": 1})]
    stale = [i for i in dict.fromkeys(stale) if i and i not in keep_ids]
    for i in range(0, len(stale), 100):
        try:
            r = await asyncio.wait_for(driver.delete_person(stale[i:i + 100]), 30)
        except Exception as e:  # noqa: BLE001
            r = {"ok": False, "detail": str(e)[:120] or "timeout"}
        if not r.get("ok") and not r.get("queued") and not r.get("info"):  # só sem resposta; "não encontrado" é normal
            job["errors"].append({"person_id": None, "name": "Limpeza de cadastros antigos",
                                  "error": str(r.get("detail") or r.get("error") or "falha")[:200]})
    return len(stale)


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
    if ctrl.get("brand") == "intelbras":  # validade de visitantes depende do relógio do facial
        from intelbras_ingest import sync_time as ib_sync_time
        await ib_sync_time(ctrl)
        if aps:  # relé, porta aberta, porta forçada e sensor (confirmação de passagem)
            d = await driver.configure_door(aps[0])
            if not d.get("ok"):
                job["errors"].append({"person_id": None, "name": "Configuração da porta no facial", "error": str(d.get("detail"))[:200]})
    # visitantes com visita ativa também vão para o facial (com a validade da visita)
    from visits_core import visit_subject, ACTIVE
    subjects = list(people)
    async for v in db.visits.find({"deleted": {"$ne": True}, "status": {"$in": list(ACTIVE)}}, {"_id": 0}):
        vis = await db.visitors.find_one({"id": v["visitor_id"], "deleted": {"$ne": True}}, {"_id": 0})
        if vis:
            subjects.append(visit_subject(vis, v))
    job["total"] = job["totals"]["people"] = len(subjects)
    if str(ctrl.get("brand", "")).startswith("beward") or ctrl.get("brand") == "intelbras":
        job["removed"] = await _remove_stale(driver, {p["id"] for p in subjects}, job)
    for p in subjects:
        try:
            r = await asyncio.wait_for(driver.sync_person(p), 45)
            if r.get("ok") and p.get("photo"):
                f = await asyncio.wait_for(driver.sync_face(p["id"], p["photo"]), 15) or {}
                if not f.get("ok"):
                    r = {"ok": False, "detail": "foto: " + str(f.get("detail") or f.get("error") or "falha")}
        except Exception as e:  # noqa: BLE001
            r = {"ok": False, "detail": str(e)[:120] or "timeout"}
        if r.get("ok"):
            job["success"] += 1
        else:
            job["errors"].append({"person_id": p["id"], "name": p.get("name"),
                                  "error": str(r.get("detail") or r.get("error") or "falha")[:200],
                                  **({"message_id": r["message_id"]} if r.get("queued") and r.get("message_id") else {})})
    if job["errors"]:
        job["status"] = "erro"
    job["finished_at"] = now_iso()
    await db.sync_jobs.insert_one(dict(job))
    job.pop("_id", None)
    await log_audit(user, "sincronizar", "controllers", cid,
                    f"TZ:{len(trs)} Áreas:{len(areas)} Pontos:{len(aps)} Regras:{len(cats)} Pessoas:{job['success']}/{job['total']}"
                    + (f" Removidos:{job['removed']}" if job.get("removed") else ""),
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
    await db.access_events.insert_one(dict(await stamp_event(event)))
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

from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request
from database import db, clean
from scope import stamp_event
from models import DeviceInput, DoorActionInput, DoorModeInput, new_id, now_iso
from security import get_current_user, require_role, encrypt_secret
from drivers.factory import get_driver, available_brands
from realtime import manager
from util import log_audit, client_ip

router = APIRouter(prefix="/devices", tags=["devices"])


def _public_device(doc):
    doc = clean(doc)
    if doc:
        doc.pop("password_enc", None)
        doc["has_password"] = True
    return doc


@router.get("/brands")
async def brands(user: dict = Depends(get_current_user)):
    labels = {"simulado": "Simulado", "controlid": "Control iD", "hikvision": "Hikvision",
              "intelbras": "Intelbras", "zkteco": "ZKTeco"}
    return [{"value": b, "label": labels.get(b, b)} for b in ["simulado", "controlid", "hikvision", "intelbras", "zkteco"]]


@router.get("")
async def list_devices(site_id: str = None, status: str = None, user: dict = Depends(get_current_user)):
    q = {}
    if site_id:
        q["site_id"] = site_id
    if status:
        q["online"] = (status == "online")
    docs = await db.devices.find(q, {"_id": 0}).to_list(500)
    for d in docs:
        d.pop("password_enc", None)
    return docs


@router.post("")
async def create_device(payload: DeviceInput, request: Request, user: dict = Depends(require_role("admin", "operator"))):
    data = payload.model_dump()
    pwd = data.pop("password", "")
    doc = {
        "id": new_id(), **data, "password_enc": encrypt_secret(pwd),
        "online": True, "firmware": "", "last_heartbeat": now_iso(),
        "created_at": now_iso(),
    }
    site = await db.sites.find_one({"id": payload.site_id})
    doc["site_name"] = site["name"] if site else ""
    await db.devices.insert_one(dict(doc))
    await log_audit(user, "criar", "device", doc["id"], payload.name, client_ip(request))
    return _public_device(doc)


@router.put("/{device_id}")
async def update_device(device_id: str, payload: DeviceInput, user: dict = Depends(require_role("admin", "operator"))):
    data = payload.model_dump()
    pwd = data.pop("password", "")
    if pwd:
        data["password_enc"] = encrypt_secret(pwd)
    site = await db.sites.find_one({"id": payload.site_id})
    data["site_name"] = site["name"] if site else ""
    await db.devices.update_one({"id": device_id}, {"$set": data})
    return _public_device(await db.devices.find_one({"id": device_id}))


@router.delete("/{device_id}")
async def delete_device(device_id: str, user: dict = Depends(require_role("admin"))):
    await db.devices.delete_one({"id": device_id})
    return {"ok": True}


@router.post("/{device_id}/test")
async def test_device(device_id: str, user: dict = Depends(get_current_user)):
    device = await db.devices.find_one({"id": device_id}, {"_id": 0})
    if not device:
        raise HTTPException(status_code=404, detail="Dispositivo não encontrado")
    driver = get_driver(device)
    ok = await driver.connect()
    status = await driver.get_status()
    info = await driver.get_device_info()
    await db.devices.update_one({"id": device_id}, {"$set": {
        "online": ok, "last_heartbeat": now_iso(), "firmware": info.get("firmware", "")}})
    return {"ok": ok, "status": status, "info": info}


@router.post("/{device_id}/sync")
async def sync_device(device_id: str, request: Request, user: dict = Depends(require_role("admin", "operator"))):
    device = await db.devices.find_one({"id": device_id}, {"_id": 0})
    if not device:
        raise HTTPException(status_code=404, detail="Dispositivo não encontrado")
    driver = get_driver(device)
    await driver.connect()
    people = await db.people.find({"status": "ativo"}, {"_id": 0}).to_list(1000)
    job = {
        "id": new_id(), "device_id": device_id, "device_name": device["name"],
        "started_at": now_iso(), "status": "concluido",
        "total": len(people), "success": 0, "errors": [],
    }
    for p in people:
        r = await driver.sync_person(p)
        if r.get("ok"):
            job["success"] += 1
            if p.get("photo"):
                await driver.sync_face(p["id"], p["photo"])
        else:
            job["errors"].append({"person_id": p["id"], "name": p["name"], "error": "falha"})
    job["finished_at"] = now_iso()
    await db.sync_jobs.insert_one(dict(job))
    await log_audit(user, "sincronizar", "device", device_id, f"{job['success']}/{job['total']} pessoas", client_ip(request))
    clean(job)
    return job


@router.get("/sync-jobs/list")
async def list_sync_jobs(user: dict = Depends(get_current_user)):
    return await db.sync_jobs.find({}, {"_id": 0}).sort("started_at", -1).limit(50).to_list(50)


# ---------- Controle de porta ----------
@router.post("/doors/{door_id}/open")
async def open_door(door_id: str, payload: DoorActionInput, request: Request,
                    user: dict = Depends(require_role("admin", "operator", "reception"))):
    door = await db.doors.find_one({"id": door_id}, {"_id": 0})
    if not door:
        raise HTTPException(status_code=404, detail="Porta não encontrada")
    device = await db.devices.find_one({"door_id": door_id}, {"_id": 0})
    driver = get_driver(device or {"brand": "simulado"})
    await driver.open_door(door_id, payload.seconds)
    event = {
        "id": new_id(), "timestamp": now_iso(),
        "site_id": door.get("site_id"), "site_name": door.get("site_name", ""),
        "area_id": door.get("area_id"), "area_name": door.get("area_name", ""),
        "door_id": door_id, "door_name": door.get("name"),
        "device_id": device.get("id") if device else None,
        "device_name": device.get("name") if device else "",
        "person_id": None, "person_name": f"Abertura remota — {user.get('name')}",
        "person_photo": "", "captured_photo": "",
        "credential_type": "remoto", "direction": "entrada",
        "access_result": "granted", "reason": payload.reason or "Abertura remota pelo operador",
        "match_score": 100.0,
    }
    await db.access_events.insert_one(dict(await stamp_event(event)))
    clean(event)
    await manager.broadcast({"type": "access_event", "data": event})
    await log_audit(user, "abrir_porta", "door", door_id, f"{door.get('name')} ({payload.reason})", client_ip(request))
    return {"ok": True, "event": event}


@router.post("/doors/{door_id}/mode")
async def set_door_mode(door_id: str, payload: DoorModeInput, request: Request,
                        user: dict = Depends(require_role("admin", "operator"))):
    if payload.mode not in ("normal", "liberada", "bloqueada"):
        raise HTTPException(status_code=400, detail="Modo inválido")
    door = await db.doors.find_one({"id": door_id}, {"_id": 0})
    if not door:
        raise HTTPException(status_code=404, detail="Porta não encontrada")
    device = await db.devices.find_one({"door_id": door_id}, {"_id": 0})
    driver = get_driver(device or {"brand": "simulado"})
    await driver.set_door_mode(door_id, payload.mode)
    await db.doors.update_one({"id": door_id}, {"$set": {"mode": payload.mode}})
    await log_audit(user, "modo_porta", "door", door_id, f"{door.get('name')} -> {payload.mode}", client_ip(request))
    await manager.broadcast({"type": "door_mode", "data": {"door_id": door_id, "mode": payload.mode}})
    return {"ok": True, "mode": payload.mode}

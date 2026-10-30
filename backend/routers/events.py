from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, Request
from database import db
from scope import scope_filter
from models import new_id, now_iso
from security import get_current_user, require_role
from realtime import generate_event, manager
from util import log_audit, client_ip

router = APIRouter(prefix="/events", tags=["events"])


@router.get("")
async def list_events(site_id: str = None, door_id: str = None, result: str = None, manual: bool = False,
                      page: int = 1, limit: int = 30, user: dict = Depends(get_current_user)):
    q = dict(await scope_filter(user, "access_events"))
    if manual:
        q["manual"] = True
    if site_id:
        q["site_id"] = site_id
    if door_id:
        q["door_id"] = door_id
    if result:
        q["access_result"] = result
    total = await db.access_events.count_documents(q)
    skip = (page - 1) * limit
    items = await db.access_events.find(q, {"_id": 0}).sort("timestamp", -1).skip(skip).limit(limit).to_list(limit)
    return {"items": items, "total": total, "page": page, "limit": limit}


@router.post("/{event_id}/release")
async def release_denied(event_id: str, body: dict, request: Request,
                         user: dict = Depends(require_role("admin", "operator", "reception"))):
    """Liberação manual de um acesso NEGADO pelo operador (abre o ponto e registra pessoa + operador)."""
    import manual_release
    return await manual_release.release(user, None, body.get("reason"), client_ip(request), event_id=event_id)


@router.post("/simulate")
async def simulate_event(user: dict = Depends(get_current_user)):
    ev = await generate_event()
    return {"ok": True, "event": ev}


# ---------- Alarmes ----------
alarms_router = APIRouter(prefix="/alarms", tags=["alarms"])


@alarms_router.get("")
async def list_alarms(acknowledged: str = None, user: dict = Depends(get_current_user)):
    q = {}
    if acknowledged in ("true", "false"):
        q["acknowledged"] = (acknowledged == "true")
    return await db.alarms.find(q, {"_id": 0}).sort("timestamp", -1).limit(100).to_list(100)


@alarms_router.post("/{alarm_id}/ack")
async def ack_alarm(alarm_id: str, request: Request, body: dict = None,
                    user: dict = Depends(require_role("admin", "operator"))):
    comment = (body or {}).get("comment", "")
    await db.alarms.update_one({"id": alarm_id}, {"$set": {
        "acknowledged": True, "ack_by": user.get("name"), "comment": comment,
        "ack_at": now_iso()}})
    await log_audit(user, "reconhecer_alarme", "alarm", alarm_id, comment, client_ip(request))
    return {"ok": True}


# ---------- Emergência ----------
emergency_router = APIRouter(prefix="/emergency", tags=["emergency"])


@emergency_router.post("/lockdown/{site_id}")
async def lockdown(site_id: str, request: Request, body: dict = None,
                   user: dict = Depends(require_role("admin", "operator"))):
    """Liberação geral de rota de fuga (incêndio) — todas as portas em modo liberado."""
    mode = (body or {}).get("mode", "liberada")  # liberada | normal
    doors = await db.access_points.find({"site_id": site_id}, {"_id": 0}).to_list(500)
    for d in doors:
        await db.access_points.update_one({"id": d["id"]}, {"$set": {"mode": mode}})
    await manager.broadcast({"type": "emergency", "data": {"site_id": site_id, "mode": mode, "by": user.get("name")}})
    action = "liberacao_geral" if mode == "liberada" else "fim_emergencia"
    await log_audit(user, action, "site", site_id, f"{len(doors)} pontos -> {mode}", client_ip(request))
    return {"ok": True, "doors_affected": len(doors), "mode": mode}


@emergency_router.get("/muster/{site_id}")
async def muster_report(site_id: str, user: dict = Depends(get_current_user)):
    """Lista de evacuação: quem está dentro de cada área (último evento = entrada)."""
    areas = await db.areas.find({"site_id": site_id, "is_exterior": {"$ne": True}}, {"_id": 0}).to_list(100)
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    report = []
    for area in areas:
        events = await db.access_events.find(
            {"area_id": area["id"], "access_result": "granted", "timestamp": {"$gte": since}, "person_id": {"$ne": None}},
            {"_id": 0}).sort("timestamp", -1).to_list(2000)
        last_dir = {}
        for e in events:
            if e["person_id"] not in last_dir:
                last_dir[e["person_id"]] = e
        inside = [{"person_id": pid, "name": e["person_name"], "photo": e.get("person_photo", ""),
                   "since": e["timestamp"]} for pid, e in last_dir.items() if e["direction"] == "entrada"]
        report.append({"area_id": area["id"], "area_name": area.get("description", ""), "count": len(inside), "people": inside})
    return {"site_id": site_id, "areas": report}


# ---------- Administração: auditoria ----------
admin_router = APIRouter(prefix="/admin", tags=["admin"])


@admin_router.get("/audit")
async def list_audit(page: int = 1, limit: int = 50, user: dict = Depends(require_role("admin"))):
    total = await db.audit_logs.count_documents({})
    skip = (page - 1) * limit
    items = await db.audit_logs.find({}, {"_id": 0}).sort("timestamp", -1).skip(skip).limit(limit).to_list(limit)
    return {"items": items, "total": total, "page": page, "limit": limit}


@admin_router.get("/settings")
async def get_settings(user: dict = Depends(require_role("admin"))):
    s = await db.settings.find_one({"id": "global"}, {"_id": 0})
    return s or {"id": "global", "retention_days": 90, "photo_retention_days": 180, "timezone": "America/Sao_Paulo"}


@admin_router.put("/settings")
async def update_settings(body: dict, user: dict = Depends(require_role("admin"))):
    body["id"] = "global"
    await db.settings.update_one({"id": "global"}, {"$set": body}, upsert=True)
    return body

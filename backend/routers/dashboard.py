from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends
from database import db
from security import get_current_user
from scope import scope_filter, is_manager

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
SP_TZ = ZoneInfo("America/Sao_Paulo")


@router.get("/stats")
async def dashboard_stats(user: dict = Depends(get_current_user)):
    now = datetime.now(SP_TZ)
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start_utc = start_of_day.astimezone(timezone.utc).isoformat()

    ev = await scope_filter(user, "access_events")
    ps = await scope_filter(user, "people")
    mgr = is_manager(user)
    granted = await db.access_events.count_documents({**ev, "timestamp": {"$gte": start_utc}, "access_result": "granted"})
    denied = await db.access_events.count_documents({**ev, "timestamp": {"$gte": start_utc}, "access_result": "denied"})

    total_devices = 0 if mgr else await db.controllers.count_documents({"deleted": {"$ne": True}})
    online = 0 if mgr else await db.controllers.count_documents({"online": True, "deleted": {"$ne": True}})
    offline = total_devices - online

    total_doors = 0 if mgr else await db.access_points.count_documents({"deleted": {"$ne": True}})
    doors_liberated = 0 if mgr else await db.access_points.count_documents({"mode": "liberada", "deleted": {"$ne": True}})

    open_alarms = 0 if mgr else await db.alarms.count_documents({"acknowledged": False})
    forced = 0 if mgr else await db.alarms.count_documents({"type": "porta_forcada", "acknowledged": False})

    total_people = await db.people.count_documents({**ps, "deleted": {"$ne": True}})
    active_people = await db.people.count_documents({**ps, "status": "ativo", "deleted": {"$ne": True}})
    vs = {**(await scope_filter(user, "visits")), "deleted": {"$ne": True}}
    visits_present = await db.visits.count_documents({**vs, "status": "presente"})
    visits_today = await db.visits.count_documents({**vs, "$or": [{"start_at": {"$gte": start_utc}}, {"expected_start": {"$gte": start_utc}}]})

    # Fluxo por hora (últimas 24h) no fuso SP
    flow = []
    events_24 = await db.access_events.find(
        {**ev, "timestamp": {"$gte": (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()}},
        {"_id": 0, "timestamp": 1, "access_result": 1}).to_list(10000)
    buckets = {}
    for e in events_24:
        try:
            ts = datetime.fromisoformat(e["timestamp"])
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            hour = ts.astimezone(SP_TZ).strftime("%H:00")
        except Exception:
            continue
        b = buckets.setdefault(hour, {"liberados": 0, "negados": 0})
        if e["access_result"] == "granted":
            b["liberados"] += 1
        else:
            b["negados"] += 1
    for h in range(24):
        key = f"{h:02d}:00"
        b = buckets.get(key, {"liberados": 0, "negados": 0})
        flow.append({"hour": key, **b})

    recent = await db.access_events.find(ev, {"_id": 0}).sort("timestamp", -1).limit(10).to_list(10)

    return {
        "today": {"granted": granted, "denied": denied, "total": granted + denied},
        "devices": {"total": total_devices, "online": online, "offline": offline},
        "doors": {"total": total_doors, "liberated": doors_liberated},
        "alarms": {"open": open_alarms, "forced": forced},
        "people": {"total": total_people, "active": active_people},
        "visits": {"present": visits_present, "today": visits_today},
        "flow": flow,
        "recent_events": recent,
    }


# ---------- Relatórios ----------
reports_router = APIRouter(prefix="/reports", tags=["reports"])


@reports_router.get("/access")
async def access_report(start: str = None, end: str = None, person_id: str = None,
                        door_id: str = None, result: str = None, user: dict = Depends(get_current_user)):
    q = dict(await scope_filter(user, "access_events"))
    if start:
        q.setdefault("timestamp", {})["$gte"] = start
    if end:
        q.setdefault("timestamp", {})["$lte"] = end
    if person_id:
        q["person_id"] = person_id
    if door_id:
        q["door_id"] = door_id
    if result:
        q["access_result"] = result
    items = await db.access_events.find(q, {"_id": 0}).sort("timestamp", -1).limit(1000).to_list(1000)
    return {"items": items, "total": len(items)}


@reports_router.get("/occupancy")
async def occupancy_report(user: dict = Depends(get_current_user)):
    areas = await db.areas.find({"deleted": {"$ne": True}, "is_exterior": {"$ne": True}}, {"_id": 0}).sort("description", 1).to_list(100)
    result = [{"area_id": a["id"], "area_name": a.get("description", ""),
               "max_occupancy": a.get("max_occupancy", 0), "current": a.get("current_occupancy", 0)} for a in areas]
    return {"areas": result}


@reports_router.get("/presence")
async def presence_report(user: dict = Depends(get_current_user)):
    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    events = await db.access_events.find(
        {**(await scope_filter(user, "access_events")), "timestamp": {"$gte": start}, "access_result": "granted", "person_id": {"$ne": None}},
        {"_id": 0}).sort("timestamp", 1).to_list(10000)
    by_person = {}
    for e in events:
        p = by_person.setdefault(e["person_id"], {"person_id": e["person_id"], "name": e["person_name"],
                                                  "first": e["timestamp"], "last": e["timestamp"]})
        p["last"] = e["timestamp"]
    return {"items": list(by_person.values()), "total": len(by_person)}

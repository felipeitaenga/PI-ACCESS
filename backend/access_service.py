import random
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from database import db
from models import new_id
from engine import decide

SP = ZoneInfo("America/Sao_Paulo")
CRED = ["facial", "cartao", "qrcode", "pin", "placa"]


def _event(person, ap, dest, origin, res, when):
    granted = res["granted"]
    return {
        "id": new_id(), "timestamp": when.astimezone(timezone.utc).isoformat(),
        "site_id": ap.get("site_id"), "site_name": ap.get("site_name", ""),
        "area_id": dest.get("id"), "area_name": dest.get("description", ""),
        "origin_area_id": origin.get("id"), "origin_area_name": origin.get("description", ""),
        "door_id": ap.get("id"), "door_name": ap.get("description"),
        "access_point_id": ap.get("id"), "controller_id": ap.get("controller_id"),
        "device_id": ap.get("controller_id"), "device_name": ap.get("controller_name", ""),
        "person_id": person.get("id"), "person_name": person.get("name"),
        "person_photo": person.get("photo", ""), "captured_photo": person.get("photo", ""),
        "credential_type": random.choice(CRED), "direction": ap.get("direction", "entrada"),
        "access_result": "granted" if granted else "denied", "reason": res.get("reason", ""),
        "match_score": round(random.uniform(92, 99.8), 1) if granted else round(random.uniform(10, 60), 1),
        "escort_required": res.get("escort_required", False), "category_code": res.get("category_code"),
    }


async def evaluate(person, ap, when=None, persist=True):
    when = when or datetime.now(SP)
    if when.tzinfo is None:
        when = when.replace(tzinfo=SP)
    dest = await db.areas.find_one({"id": ap.get("dest_area_id")}, {"_id": 0}) or {}
    origin = await db.areas.find_one({"id": ap.get("origin_area_id")}, {"_id": 0}) or {}
    cats = await db.categories.find(
        {"id": {"$in": person.get("category_ids", [])}, "enabled": True, "deleted": {"$ne": True}},
        {"_id": 0}).to_list(50)
    trs = await db.time_ranges.find({"deleted": {"$ne": True}}, {"_id": 0}).to_list(200)
    tr_by = {t["id"]: t for t in trs}
    hols = await db.holidays.find({"deleted": {"$ne": True}}, {"_id": 0}).to_list(500)
    company_active = True
    if person.get("company_id"):
        comp = await db.companies.find_one({"id": person["company_id"]}, {"_id": 0})
        company_active = bool(comp and comp.get("enabled", True) and not comp.get("deleted"))
    recent = await db.access_events.find({"person_id": person.get("id")}, {"_id": 0}).sort("timestamp", -1).limit(10).to_list(10)
    res = decide(person, ap, dest, origin, cats, tr_by, hols, when, company_active, recent, ap.get("site_id"))
    event = _event(person, ap, dest, origin, res, when)
    res["event"] = event
    if persist:
        await db.access_events.insert_one(dict(event))
        event.pop("_id", None)
        if res["granted"]:
            if dest and not dest.get("is_exterior"):
                await db.areas.update_one({"id": dest["id"]}, {"$inc": {"current_occupancy": 1}})
            if origin and not origin.get("is_exterior") and person.get("current_area_id") == origin.get("id"):
                await db.areas.update_one({"id": origin["id"]}, {"$inc": {"current_occupancy": -1}})
            await db.people.update_one({"id": person["id"]}, {"$set": {"current_area_id": dest.get("id")}})
    return res

from fastapi import APIRouter, Depends, HTTPException, Request
from database import db, clean
from models import SiteInput, AreaInput, DoorInput, new_id, now_iso
from security import get_current_user, require_role
from util import log_audit, client_ip

router = APIRouter(prefix="/structure", tags=["structure"])


# ---------- Sites ----------
@router.get("/sites")
async def list_sites(user: dict = Depends(get_current_user)):
    return await db.sites.find({}, {"_id": 0}).to_list(500)


@router.post("/sites")
async def create_site(payload: SiteInput, request: Request, user: dict = Depends(require_role("admin", "operator"))):
    doc = {"id": new_id(), **payload.model_dump(), "created_at": now_iso()}
    await db.sites.insert_one(dict(doc))
    await log_audit(user, "criar", "site", doc["id"], payload.name, client_ip(request))
    return clean(doc)


@router.put("/sites/{site_id}")
async def update_site(site_id: str, payload: SiteInput, user: dict = Depends(require_role("admin", "operator"))):
    await db.sites.update_one({"id": site_id}, {"$set": payload.model_dump()})
    return clean(await db.sites.find_one({"id": site_id}))


@router.put("/sites/{site_id}/business-hours")
async def site_hours(site_id: str, body: dict, user: dict = Depends(require_role("admin", "operator"))):
    hours = {"days": [int(d) for d in body.get("days", []) if 1 <= int(d) <= 7], "start": body.get("start", "07:00"),
             "end": body.get("end", "19:00")}
    await db.sites.update_one({"id": site_id}, {"$set": {"business_hours": hours}})
    return hours


@router.delete("/sites/{site_id}")
async def delete_site(site_id: str, user: dict = Depends(require_role("admin"))):
    await db.sites.delete_one({"id": site_id})
    await db.areas.delete_many({"site_id": site_id})
    await db.doors.delete_many({"site_id": site_id})
    return {"ok": True}


# ---------- Areas ----------
@router.get("/areas")
async def list_areas(site_id: str = None, user: dict = Depends(get_current_user)):
    q = {"site_id": site_id} if site_id else {}
    return await db.areas.find(q, {"_id": 0}).to_list(500)


@router.post("/areas")
async def create_area(payload: AreaInput, request: Request, user: dict = Depends(require_role("admin", "operator"))):
    site = await db.sites.find_one({"id": payload.site_id})
    if not site:
        raise HTTPException(status_code=404, detail="Site não encontrado")
    doc = {"id": new_id(), **payload.model_dump(), "site_name": site["name"], "created_at": now_iso()}
    await db.areas.insert_one(dict(doc))
    await log_audit(user, "criar", "area", doc["id"], payload.name, client_ip(request))
    return clean(doc)


@router.put("/areas/{area_id}")
async def update_area(area_id: str, payload: AreaInput, user: dict = Depends(require_role("admin", "operator"))):
    site = await db.sites.find_one({"id": payload.site_id})
    upd = payload.model_dump()
    upd["site_name"] = site["name"] if site else ""
    await db.areas.update_one({"id": area_id}, {"$set": upd})
    return clean(await db.areas.find_one({"id": area_id}))


@router.delete("/areas/{area_id}")
async def delete_area(area_id: str, user: dict = Depends(require_role("admin"))):
    await db.areas.delete_one({"id": area_id})
    await db.doors.delete_many({"area_id": area_id})
    return {"ok": True}


# ---------- Doors ----------
@router.get("/doors")
async def list_doors(site_id: str = None, area_id: str = None, user: dict = Depends(get_current_user)):
    q = {}
    if site_id:
        q["site_id"] = site_id
    if area_id:
        q["area_id"] = area_id
    return await db.doors.find(q, {"_id": 0}).to_list(500)


@router.post("/doors")
async def create_door(payload: DoorInput, request: Request, user: dict = Depends(require_role("admin", "operator"))):
    site = await db.sites.find_one({"id": payload.site_id})
    area = await db.areas.find_one({"id": payload.area_id})
    doc = {
        "id": new_id(), **payload.model_dump(),
        "site_name": site["name"] if site else "",
        "area_name": area["name"] if area else "",
        "mode": "normal", "state": "fechada", "created_at": now_iso(),
    }
    await db.doors.insert_one(dict(doc))
    await log_audit(user, "criar", "door", doc["id"], payload.name, client_ip(request))
    return clean(doc)


@router.put("/doors/{door_id}")
async def update_door(door_id: str, payload: DoorInput, user: dict = Depends(require_role("admin", "operator"))):
    site = await db.sites.find_one({"id": payload.site_id})
    area = await db.areas.find_one({"id": payload.area_id})
    upd = payload.model_dump()
    upd["site_name"] = site["name"] if site else ""
    upd["area_name"] = area["name"] if area else ""
    await db.doors.update_one({"id": door_id}, {"$set": upd})
    return clean(await db.doors.find_one({"id": door_id}))


@router.delete("/doors/{door_id}")
async def delete_door(door_id: str, user: dict = Depends(require_role("admin"))):
    await db.doors.delete_one({"id": door_id})
    return {"ok": True}

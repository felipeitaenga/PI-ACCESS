from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from database import db
from security import get_current_user, require_role
from crud import make_crud
from access_service import evaluate, SP
from util import log_audit, client_ip

router = APIRouter(prefix="/access", tags=["access"])


async def _area_enrich(doc):
    if doc.get("site_id"):
        s = await db.sites.find_one({"id": doc["site_id"]}, {"_id": 0})
        doc["site_name"] = s["name"] if s else ""
    doc.setdefault("current_occupancy", 0)
    return doc


make_crud(router, "/time-ranges", "time_ranges", search_fields=["description"], sort="description")
make_crud(router, "/holidays", "holidays", search_fields=["description"], sort="date")
make_crud(router, "/areas", "areas", search_fields=["description"], sort="description", enrich=_area_enrich)
make_crud(router, "/categories", "categories", search_fields=["code", "description"], sort="code")


@router.post("/areas/{area_id}/occupancy")
async def set_occupancy(area_id: str, body: dict, request: Request,
                        user: dict = Depends(require_role("admin", "operator"))):
    val = int(body.get("value", 0))
    await db.areas.update_one({"id": area_id}, {"$set": {"current_occupancy": val}})
    await log_audit(user, "ajuste_lotacao", "areas", area_id, f"lotação ajustada para {val}", client_ip(request))
    return {"ok": True, "current_occupancy": val}


@router.get("/categories/{cat_id}/people")
async def cat_people(cat_id: str, user: dict = Depends(get_current_user)):
    return await db.people.find({"category_ids": cat_id, "deleted": {"$ne": True}}, {"_id": 0}).to_list(2000)


@router.post("/categories/{cat_id}/people")
async def cat_people_update(cat_id: str, body: dict, user: dict = Depends(require_role("admin", "operator"))):
    ids = body.get("person_ids", [])
    if body.get("action", "add") == "add":
        await db.people.update_many({"id": {"$in": ids}}, {"$addToSet": {"category_ids": cat_id}})
    else:
        await db.people.update_many({"id": {"$in": ids}}, {"$pull": {"category_ids": cat_id}})
    return {"ok": True, "affected": len(ids)}


@router.post("/simulate")
async def simulate(body: dict, user: dict = Depends(get_current_user)):
    person = await db.people.find_one({"id": body.get("person_id")}, {"_id": 0})
    ap = await db.access_points.find_one({"id": body.get("access_point_id")}, {"_id": 0})
    if not person or not ap:
        raise HTTPException(status_code=404, detail="Pessoa ou ponto de acesso não encontrado")
    when = None
    if body.get("datetime"):
        try:
            when = datetime.fromisoformat(body["datetime"])
            if when.tzinfo is None:
                when = when.replace(tzinfo=SP)
        except Exception:
            when = None
    res = await evaluate(person, ap, when=when, persist=False)
    return res

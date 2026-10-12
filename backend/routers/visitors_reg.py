import secrets
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from database import db
from security import get_current_user, require_role
from models import new_id, now_iso
from photo_quality import make_thumb
from registry_common import ND, only_digits, valid_cpf, fmt_cpf, today, refresh_expired, sync_to_devices
from util import log_audit, client_ip
from scope import scope_filter, find_scoped

router = APIRouter(prefix="/registry", tags=["registry-visitors"])
WRITE = ("admin", "operator", "reception")
VISITOR_FIELDS = ["name", "document", "cpf", "rg", "birth", "phone", "email", "origin_company", "notes", "photo"]


def _visit_subject(visitor, visit):
    return {"id": visitor["id"], "name": visitor["name"], "photo": visitor.get("photo", ""),
            "status": "ativo" if visit.get("status") in ("agendado", "presente") else "inativo",
            "category_ids": [visit.get("category_id")] if visit.get("category_id") else [],
            "valid_from": visit.get("expected_start"), "valid_until": visit.get("expected_end"),
            "credential_type": visit.get("credential_type"), "credential_value": visit.get("credential_value")}


async def _with_last_visit(visitors):
    ids = [v["id"] for v in visitors]
    last = {}
    for vi in await db.visits.find({**ND, "visitor_id": {"$in": ids}}, {"_id": 0}).sort("created_at", -1).to_list(5000):
        last.setdefault(vi["visitor_id"], vi)
    for v in visitors:
        v["last_visit"] = last.get(v["id"])
    return visitors


@router.get("/visitor-companies")
async def visitor_companies(user: dict = Depends(get_current_user)):
    await refresh_expired()
    vsc = await scope_filter(user, "visits")
    present = {v["visitor_id"] for v in await db.visits.find({**ND, **vsc, "status": "presente"}, {"_id": 0, "visitor_id": 1}).to_list(5000)}
    out = {}
    for v in await db.visitors.find({**ND, **(await scope_filter(user, "visitors"))}, {"_id": 0, "id": 1, "origin_company": 1, "blacklist": 1}).to_list(20000):
        k = v.get("origin_company") or "Sem empresa"
        s = out.setdefault(k, {"name": k, "total": 0, "present": 0, "blacklist": 0})
        s["total"] += 1
        s["present"] += v["id"] in present
        s["blacklist"] += bool(v.get("blacklist"))
    t = today()
    today_count = await db.visits.count_documents({**ND, **vsc, "$or": [{"status": "presente"},
                                                                  {"expected_start": {"$regex": f"^{t}"}}]})
    return {"companies": sorted(out.values(), key=lambda x: x["name"]), "today": today_count,
            "present": len(present)}


@router.get("/visitors")
async def list_visitors(origin: str = "", today_only: str = "", q: str = "", present: str = "",
                        user: dict = Depends(get_current_user)):
    query = {**ND, **(await scope_filter(user, "visitors"))}
    if origin:
        query["origin_company"] = "" if origin == "Sem empresa" else origin
    if q:
        query["$or"] = [{"name": {"$regex": q, "$options": "i"}}, {"document": {"$regex": q, "$options": "i"}}]
    if today_only == "true" or present == "true":
        vq = {**ND, "status": "presente"} if present == "true" else \
            {**ND, "$or": [{"status": "presente"}, {"expected_start": {"$regex": f"^{today()}"}}]}
        ids = await db.visits.distinct("visitor_id", {**vq, **(await scope_filter(user, "visits"))})
        query["id"] = {"$in": [i for i in ids if i in set(query.get("id", {}).get("$in", ids))]}
    items = await db.visitors.find(query, {"_id": 0, "photo": 0}).sort("name", 1).to_list(500)
    return {"items": await _with_last_visit(items), "total": len(items)}


@router.get("/visitors/lookup")
async def lookup(document: str, user: dict = Depends(get_current_user)):
    dig = only_digits(document)
    ors = [{"document": document.strip()}]
    if dig:
        ors += [{"document_digits": dig}, {"cpf_digits": dig}]
    v = await db.visitors.find_one({**ND, **(await scope_filter(user, "visitors")), "$or": ors}, {"_id": 0})
    if not v:
        return {"found": False}
    v["visits"] = await db.visits.find({**ND, **(await scope_filter(user, "visits")), "visitor_id": v["id"]}, {"_id": 0}).sort("created_at", -1).limit(5).to_list(5)
    return {"found": True, "visitor": v}


@router.get("/visitors/{vid}")
async def get_visitor(vid: str, user: dict = Depends(get_current_user)):
    v = await find_scoped(user, "visitors", vid, msg="Visitante não encontrado")
    v["visits"] = await db.visits.find({**ND, **(await scope_filter(user, "visits")), "visitor_id": vid}, {"_id": 0}).sort("created_at", -1).limit(20).to_list(20)
    return v


@router.get("/visits/present")
async def visits_present(user: dict = Depends(get_current_user)):
    visits = await db.visits.find({**ND, **(await scope_filter(user, "visits")), "status": "presente"}, {"_id": 0}).sort("checkin_at", -1).to_list(500)
    thumbs = {v["id"]: v.get("photo_thumb", "") for v in await db.visitors.find(
        {"id": {"$in": [x["visitor_id"] for x in visits]}}, {"_id": 0, "id": 1, "photo_thumb": 1}).to_list(500)}
    now = now_iso()
    for x in visits:
        x["photo"] = thumbs.get(x["visitor_id"], "")
        x["overstay"] = bool(x.get("expected_end") and x["expected_end"] < now)
    return visits


def _validate(vis, visit):
    f = {}
    if not (vis.get("name") or "").strip():
        f["name"] = "Informe o nome completo"
    if not (vis.get("document") or "").strip():
        f["document"] = "Informe o documento"
    if vis.get("cpf") and not valid_cpf(vis["cpf"]):
        f["cpf"] = "CPF inválido"
    if not visit.get("host_id"):
        f["host_id"] = "Selecione o anfitrião"
    if not visit.get("expected_start"):
        f["expected_start"] = "Informe a entrada prevista"
    if not visit.get("expected_end"):
        f["expected_end"] = "Informe a saída prevista"
    if visit.get("expected_start") and visit.get("expected_end") and visit["expected_end"] <= visit["expected_start"]:
        f["expected_end"] = "Saída deve ser após a entrada"
    return f


def _iso(local):
    """'YYYY-MM-DDTHH:MM' (horário de Brasília) -> ISO UTC."""
    if not local or "+" in local or local.endswith("Z"):
        return local
    from zoneinfo import ZoneInfo
    dt = datetime.fromisoformat(local).replace(tzinfo=ZoneInfo("America/Sao_Paulo"))
    return dt.astimezone(timezone.utc).isoformat()


@router.post("/visits")
async def save_visit(body: dict, request: Request, user: dict = Depends(require_role(*WRITE))):
    vis, visit = body.get("visitor") or {}, body.get("visit") or {}
    errs = _validate(vis, visit)
    if errs:
        raise HTTPException(status_code=422, detail={"msg": "Verifique os campos destacados", "fields": errs})
    dig = only_digits(vis["document"])
    existing = None
    if vis.get("id"):
        existing = await db.visitors.find_one({"id": vis["id"]}, {"_id": 0})
    if not existing:
        existing = await db.visitors.find_one({**ND, "$or": [{"document": vis["document"].strip()},
                                                             *([{"document_digits": dig}] if dig else [])]}, {"_id": 0})
    if existing and existing.get("blacklist"):
        raise HTTPException(status_code=409, detail=f"Visitante em LISTA NEGRA: {existing.get('blacklist_reason') or 'acesso proibido'}")
    host = await db.people.find_one({"id": visit["host_id"]}, {"_id": 0, "id": 1, "name": 1, "company_name": 1})
    if not host:
        raise HTTPException(status_code=422, detail={"msg": "Anfitrião não encontrado", "fields": {"host_id": "Anfitrião inválido"}})
    vdoc = {k: vis.get(k) for k in VISITOR_FIELDS if k in vis}
    if existing and not vis.get("photo"):
        vdoc.pop("photo", None)
    vdoc.update({"document": vis["document"].strip(), "document_digits": dig, "updated_at": now_iso()})
    if vis.get("cpf"):
        vdoc["cpf"], vdoc["cpf_digits"] = fmt_cpf(vis["cpf"]), only_digits(vis["cpf"])
    if "photo" in vdoc:
        vdoc["photo_thumb"] = make_thumb(vdoc["photo"] or "")
    if existing:
        vid = existing["id"]
        await db.visitors.update_one({"id": vid}, {"$set": vdoc})
    else:
        vid = new_id()
        await db.visitors.insert_one({**vdoc, "id": vid, "blacklist": False, "enabled": True, "deleted": False,
                                      "created_at": now_iso()})
    visitor = await db.visitors.find_one({"id": vid}, {"_id": 0})
    cat = visit.get("category_id")
    if not cat:
        c = await db.categories.find_one({**ND, "code": "VISITANTE"}, {"_id": 0, "id": 1})
        cat = c["id"] if c else None
    cred = visit.get("credential_type") or "qrcode"
    cred_val = (visit.get("credential_value") or "").strip()
    if cred == "qrcode" and not cred_val:
        cred_val = "NXV-" + secrets.token_hex(6).upper()
    vfields = {"visitor_id": vid, "visitor_name": visitor["name"], "visitor_document": visitor["document"],
               "origin_company": visitor.get("origin_company", ""), "host_id": host["id"], "host_name": host["name"],
               "reason": visit.get("reason", ""), "expected_start": _iso(visit["expected_start"]),
               "expected_end": _iso(visit["expected_end"]), "category_id": cat,
               "require_escort": bool(visit.get("require_escort", True)), "credential_type": cred,
               "credential_value": cred_val, "vehicle_plate": (visit.get("vehicle_plate") or "").upper(),
               "updated_at": now_iso()}
    old = await db.visits.find_one({"id": visit["id"], "visitor_id": vid}, {"_id": 0}) if visit.get("id") else None
    if old and old.get("status") in ("agendado", "presente"):
        visit_id = old["id"]
        await db.visits.update_one({"id": visit_id}, {"$set": vfields})
    else:
        visit_id = new_id()
        await db.visits.insert_one({**vfields, "id": visit_id, "status": "agendado", "enabled": True,
                                    "deleted": False, "created_at": now_iso()})
    if body.get("checkin"):
        await db.visits.update_one({"id": visit_id}, {"$set": {"status": "presente", "checkin_at": now_iso()}})
    vrec = await db.visits.find_one({"id": visit_id}, {"_id": 0})
    await log_audit(user, "visita", "visit", visit_id, f"{visitor['name']} → {host['name']} ({vrec['status']})", client_ip(request))
    sync = await sync_to_devices(_visit_subject(visitor, vrec), "Visitante")
    visitor.pop("photo", None)
    return {"visitor": visitor, "visit": vrec, "sync": sync}


@router.post("/visits/{visit_id}/checkin")
async def checkin(visit_id: str, request: Request, user: dict = Depends(require_role(*WRITE))):
    v = await db.visits.find_one({"id": visit_id}, {"_id": 0})
    if not v:
        raise HTTPException(status_code=404, detail="Visita não encontrada")
    if v["status"] not in ("agendado",):
        raise HTTPException(status_code=400, detail=f"Visita com status '{v['status']}' não permite check-in")
    visitor = await db.visitors.find_one({"id": v["visitor_id"]}, {"_id": 0})
    if visitor and visitor.get("blacklist"):
        raise HTTPException(status_code=409, detail="Visitante em LISTA NEGRA")
    await db.visits.update_one({"id": visit_id}, {"$set": {"status": "presente", "checkin_at": now_iso()}})
    await log_audit(user, "checkin", "visit", visit_id, v["visitor_name"], client_ip(request))
    return {"ok": True}


@router.post("/visits/{visit_id}/checkout")
async def checkout(visit_id: str, request: Request, user: dict = Depends(require_role(*WRITE))):
    v = await db.visits.find_one({"id": visit_id}, {"_id": 0})
    if not v:
        raise HTTPException(status_code=404, detail="Visita não encontrada")
    if v["status"] != "presente":
        raise HTTPException(status_code=400, detail="Visitante não está presente")
    await db.visits.update_one({"id": visit_id}, {"$set": {"status": "finalizado", "checkout_at": now_iso()}})
    visitor = await db.visitors.find_one({"id": v["visitor_id"]}, {"_id": 0}) or {"id": v["visitor_id"], "name": v["visitor_name"]}
    await sync_to_devices(visitor, "Check-out", remove=True)
    await log_audit(user, "checkout", "visit", visit_id, v["visitor_name"], client_ip(request))
    return {"ok": True}

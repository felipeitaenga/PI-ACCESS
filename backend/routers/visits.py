"""Cadastro de visita (portaria), tipos de visita e configurações de visitantes."""
import re
import secrets
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from database import db
from security import get_current_user, require_role
from models import new_id, now_iso
from photo_quality import make_thumb
from registry_common import ND, sync_to_devices
from util import log_audit, client_ip
from visits_core import (get_settings, validate_doc, doc_key, compute_end, type_hours, parse_dt, card_decimal,
                         norm_plate, visit_subject, end_visit, DOC_TYPES, ID_TYPES, ACTIVE)

router = APIRouter(prefix="/visits", tags=["visits"])
WRITE = ("admin", "operator", "reception")
ADMIN = require_role("admin")
TYPE_FIELDS = ("name", "category_ids", "default_hours", "require_escort", "require_photo", "active")


def _type_body(b):
    errs = {}
    if not (b.get("name") or "").strip():
        errs["name"] = "Informe o nome"
    if not b.get("category_ids"):
        errs["category_ids"] = "Selecione ao menos uma categoria"
    try:
        h = float(str(b.get("default_hours", 8)).replace(",", "."))
        if h <= 0:
            raise ValueError
    except ValueError:
        errs["default_hours"] = "Duração inválida"
        h = 8
    if errs:
        raise HTTPException(status_code=422, detail={"msg": "Verifique os campos destacados", "fields": errs})
    return {"name": b["name"].strip(), "category_ids": list(b["category_ids"]), "default_hours": h,
            "require_escort": bool(b.get("require_escort")), "require_photo": bool(b.get("require_photo")),
            "active": bool(b.get("active", True))}


@router.get("/types")
async def list_types(active: str = "", user: dict = Depends(get_current_user)):
    q = {**ND, **({"active": True} if active == "true" else {})}
    return await db.visit_types.find(q, {"_id": 0}).sort("name", 1).to_list(500)


@router.post("/types")
async def create_type(body: dict, request: Request, user: dict = Depends(ADMIN)):
    doc = {**_type_body(body), "id": new_id(), "deleted": False, "created_at": now_iso()}
    await db.visit_types.insert_one(dict(doc))
    await log_audit(user, "criar", "visit_type", doc["id"], doc["name"], client_ip(request))
    return doc


@router.put("/types/{tid}")
async def update_type(tid: str, body: dict, request: Request, user: dict = Depends(ADMIN)):
    doc = _type_body(body)
    r = await db.visit_types.update_one({"id": tid}, {"$set": {**doc, "updated_at": now_iso()}})
    if not r.matched_count:
        raise HTTPException(status_code=404, detail="Tipo de visita não encontrado")
    await log_audit(user, "editar", "visit_type", tid, doc["name"], client_ip(request))
    return await db.visit_types.find_one({"id": tid}, {"_id": 0})


@router.delete("/types/{tid}")
async def delete_type(tid: str, request: Request, user: dict = Depends(ADMIN)):
    await db.visit_types.update_one({"id": tid}, {"$set": {"deleted": True}})
    await log_audit(user, "excluir", "visit_type", tid, "", client_ip(request))
    return {"ok": True}


@router.get("/settings")
async def read_settings(user: dict = Depends(get_current_user)):
    return await get_settings()


@router.put("/settings")
async def write_settings(body: dict, request: Request, user: dict = Depends(ADMIN)):
    try:
        h = float(str(body.get("default_hours", 8)).replace(",", "."))
        assert h > 0
    except (ValueError, AssertionError):
        raise HTTPException(status_code=422, detail="Duração padrão inválida")
    s = {"validate_cpf": bool(body.get("validate_cpf", True)), "validate_rg": bool(body.get("validate_rg")),
         "default_hours": h, "updated_at": now_iso()}
    await db.settings.update_one({"id": "visitors"}, {"$set": s}, upsert=True)
    await log_audit(user, "editar", "settings", "visitors", str(s), client_ip(request))
    return await get_settings()


@router.get("/lookup")
async def lookup(doc_type: str, doc_number: str, user: dict = Depends(get_current_user)):
    key = doc_key(doc_type, doc_number)
    if len(key) < 3:
        return {"found": False}
    v = await db.visitors.find_one({**ND, "doc_type": doc_type, "doc_key": key}, {"_id": 0})
    if not v and doc_type == "cpf":
        v = await db.visitors.find_one({**ND, "$or": [{"cpf_digits": key}, {"document_digits": key}]}, {"_id": 0})
    if not v:
        return {"found": False}
    return {"found": True, "visitor": {k: v.get(k) for k in ("id", "name", "origin_company", "photo", "plate",
                                                              "blacklist", "blacklist_reason")}}


@router.get("/visitor-search")
async def visitor_search(q: str, user: dict = Depends(get_current_user)):
    q = q.strip()
    if len(q) < 3:
        return []
    rxq = {"$regex": re.escape(q), "$options": "i"}
    ors = [{"name": rxq}, {"doc_number": rxq}, {"document": rxq}]
    dig = re.sub(r"\D", "", q)
    if len(dig) >= 3:
        ors += [{"doc_key": {"$regex": dig}}, {"cpf_digits": {"$regex": dig}}, {"document_digits": {"$regex": dig}}]
    items = await db.visitors.find({**ND, "$or": ors}, {"_id": 0, "id": 1, "name": 1, "doc_type": 1, "doc_number": 1, "document": 1,
                                                       "cpf": 1, "cpf_digits": 1, "origin_company": 1, "photo_thumb": 1,
                                                       "blacklist": 1}).sort("updated_at", -1).limit(8).to_list(8)
    for v in items:
        if not v.get("doc_type"):
            v["doc_type"] = "cpf" if v.get("cpf_digits") else "outro"
        v["doc_number"] = v.get("doc_number") or (v.get("cpf") if v["doc_type"] == "cpf" else v.get("document", ""))
        v.pop("cpf_digits", None)
    return items


@router.get("/visitor/{vid}/prefill")
async def prefill(vid: str, user: dict = Depends(get_current_user)):
    v = await db.visitors.find_one({**ND, "id": vid}, {"_id": 0})
    if not v:
        raise HTTPException(status_code=404, detail="Visitante não encontrado")
    doc_type = v.get("doc_type") or ("cpf" if v.get("cpf_digits") else "outro")
    out = {"visitor": {"id": v["id"], "name": v.get("name", ""), "doc_type": doc_type,
                       "doc_number": v.get("doc_number") or (v.get("cpf") if doc_type == "cpf" else v.get("document", "")),
                       "origin_company": v.get("origin_company", ""), "photo": v.get("photo", ""),
                       "plate": v.get("plate", ""), "blacklist": bool(v.get("blacklist")),
                       "blacklist_reason": v.get("blacklist_reason", "")}, "last_visit": None}
    last = await db.visits.find_one({**ND, "visitor_id": vid}, {"_id": 0}, sort=[("created_at", -1)])
    if last:
        vt = await db.visit_types.find_one({**ND, "id": last.get("visit_type_id"), "active": True}, {"_id": 0, "id": 1})
        host = await db.people.find_one({**ND, "id": last.get("host_person_id") or last.get("host_id"), "status": "ativo",
                                         "can_authorize_visits": {"$ne": False}}, {"_id": 0, "id": 1, "name": 1, "company_id": 1})
        ident = last.get("identifier") or {"type": last.get("credential_type") or "facial", "value": last.get("credential_value", "")}
        out["last_visit"] = {"visit_type_id": vt["id"] if vt else "",
                             "host_company_id": (host or {}).get("company_id") or last.get("host_company_id", ""),
                             "host_person_id": (host or {}).get("id", ""), "host_name": (host or {}).get("name", ""),
                             "id_type": ident.get("type") if ident.get("type") in ID_TYPES else "facial",
                             "id_value": ident.get("value", "") if ident.get("type") == "cartao" else "",
                             "notes": last.get("notes", ""), "plate": last.get("plate") or last.get("vehicle_plate", "")}
    return out


@router.get("/visitor-companies")
async def visitor_companies(q: str = "", user: dict = Depends(get_current_user)):
    names = await db.visitors.distinct("origin_company", ND)
    ql = q.strip().lower()
    return sorted([n for n in names if n and (not ql or ql in n.lower())])[:10]


@router.get("/present")
async def present(user: dict = Depends(get_current_user)):
    now = datetime.now(timezone.utc).isoformat()
    items = await db.visits.find({**ND, "status": "presente", "start_at": {"$lte": now}}, {"_id": 0}).sort("end_at", 1).to_list(500)
    thumbs = {v["id"]: v.get("photo_thumb", "") for v in await db.visitors.find(
        {"id": {"$in": [x["visitor_id"] for x in items]}}, {"_id": 0, "id": 1, "photo_thumb": 1}).to_list(500)}
    for x in items:
        x["photo"] = thumbs.get(x["visitor_id"], "")
        x["remaining_min"] = int((parse_dt(x["end_at"]) - datetime.now(timezone.utc)).total_seconds() // 60)
    return items


async def _check(body, settings):
    errs = {}
    vtype = await db.visit_types.find_one({**ND, "id": body.get("visit_type_id"), "active": True}, {"_id": 0})
    if not vtype:
        errs["visit_type_id"] = "Selecione o tipo da visita"
    try:
        start = parse_dt(body.get("start_at") or datetime.now(timezone.utc).isoformat())
    except ValueError:
        errs["start_at"] = "Data/hora de início inválida"
        start = datetime.now(timezone.utc)
    end = None
    try:
        end = parse_dt(body["end_at"]) if body.get("end_at") else compute_end(start.isoformat(), type_hours(vtype, settings))
        if end <= start:
            errs["end_at"] = "O fim deve ser depois do início"
    except ValueError:
        errs["end_at"] = "Data/hora do fim inválida"
    comp = await db.companies.find_one({**ND, "id": body.get("host_company_id")}, {"_id": 0, "id": 1, "name": 1})
    if not comp:
        errs["host_company_id"] = "Selecione a empresa visitada"
    host = await db.people.find_one({**ND, "id": body.get("host_person_id"), "status": "ativo", "can_authorize_visits": {"$ne": False}},
                                    {"_id": 0, "id": 1, "name": 1, "company_id": 1})
    if not host or (comp and host.get("company_id") != comp["id"]):
        errs["host_person_id"] = "Selecione o anfitrião (pessoa ativa da empresa visitada que pode autorizar visitas)"
    if not (body.get("name") or "").strip():
        errs["name"] = "Informe o nome completo"
    dt = body.get("doc_type")
    if dt not in DOC_TYPES:
        errs["doc_type"] = "Selecione o tipo de documento"
    doc_number, derr = validate_doc(dt, body.get("doc_number"), settings)
    if derr and dt in DOC_TYPES:
        errs["doc_number"] = derr
    ident = body.get("identifier") or {}
    itype = ident.get("type") or "facial"
    ivalue = (ident.get("value") or "").strip()
    if itype not in ID_TYPES:
        errs["identifier"] = "Identificador inválido"
    elif itype == "cartao":
        try:
            ivalue = card_decimal(ivalue)
            if not ivalue:
                errs["identifier"] = "Informe o número do cartão"
        except ValueError as e:
            errs["identifier"] = str(e)
    elif itype == "qrcode" and not ivalue:
        ivalue = "PIV-" + secrets.token_hex(6).upper()
    plate, perr = norm_plate(body.get("plate"))
    if perr:
        errs["plate"] = perr
    return errs, {"vtype": vtype, "start": start, "end": end, "comp": comp, "host": host, "doc_number": doc_number,
                  "identifier": {"type": itype, "value": ivalue}, "plate": plate}


@router.post("")
async def create_visit(body: dict, request: Request, user: dict = Depends(require_role(*WRITE))):
    settings = await get_settings()
    errs, c = await _check(body, settings)
    key = doc_key(body.get("doc_type"), c["doc_number"])
    existing = await db.visitors.find_one({**ND, "doc_type": body.get("doc_type"), "doc_key": key}, {"_id": 0}) if key else None
    photo = body.get("photo") or ""
    if c["identifier"]["type"] == "facial" and not photo and not (existing or {}).get("photo"):
        errs["photo"] = "Foto obrigatória para identificador Facial"
    if c["vtype"] and c["vtype"].get("require_photo") and not photo and not (existing or {}).get("photo"):
        errs["photo"] = "Este tipo de visita exige foto"
    if errs:
        raise HTTPException(status_code=422, detail={"msg": "Verifique os campos destacados", "fields": errs})
    override = ""
    if existing and existing.get("blacklist"):
        just = (body.get("blacklist_justification") or "").strip()
        if user.get("role") != "admin" or len(just) < 5:
            raise HTTPException(status_code=409, detail=f"Visitante em LISTA NEGRA: {existing.get('blacklist_reason') or 'acesso proibido'}. "
                                                        "Somente Administrador pode liberar, com justificativa.")
        override = just
    vdoc = {"name": body["name"].strip(), "doc_type": body["doc_type"], "doc_number": c["doc_number"], "doc_key": key,
            "document": c["doc_number"], "document_digits": key if body["doc_type"] == "cpf" else "",
            "origin_company": (body.get("visitor_company") or "").strip(), "plate": c["plate"], "updated_at": now_iso()}
    if body["doc_type"] == "cpf":
        vdoc.update({"cpf": c["doc_number"], "cpf_digits": key})
    if photo:
        vdoc.update({"photo": photo, "photo_thumb": make_thumb(photo)})
    if existing:
        vid = existing["id"]
        await db.visitors.update_one({"id": vid}, {"$set": vdoc})
    else:
        vid = new_id()
        await db.visitors.insert_one({**vdoc, "id": vid, "blacklist": False, "enabled": True, "deleted": False, "created_at": now_iso()})
    visitor = await db.visitors.find_one({"id": vid}, {"_id": 0})
    now = datetime.now(timezone.utc)
    start_iso, end_iso = c["start"].astimezone(timezone.utc).isoformat(), c["end"].astimezone(timezone.utc).isoformat()
    status = "presente" if c["start"] <= now else "agendado"
    vt = c["vtype"]
    visit = {"id": new_id(), "visitor_id": vid, "visitor_name": visitor["name"], "visitor_document": c["doc_number"],
             "origin_company": vdoc["origin_company"], "visitor_company": vdoc["origin_company"],
             "visit_type_id": vt["id"], "visit_type_name": vt["name"], "category_ids": vt["category_ids"],
             "category_id": vt["category_ids"][0], "require_escort": vt.get("require_escort", False),
             "host_company_id": c["comp"]["id"], "host_company_name": c["comp"]["name"],
             "host_person_id": c["host"]["id"], "host_id": c["host"]["id"], "host_name": c["host"]["name"],
             "doc_type": body["doc_type"], "doc_number": c["doc_number"], "identifier": c["identifier"],
             "credential_type": c["identifier"]["type"], "credential_value": c["identifier"]["value"],
             "plate": c["plate"], "vehicle_plate": c["plate"], "notes": (body.get("notes") or "").strip(),
             "start_at": start_iso, "end_at": end_iso, "expected_start": start_iso, "expected_end": end_iso,
             "end_at_manual": bool(body.get("end_at_manual")), "status": status,
             **({"checkin_at": now.isoformat()} if status == "presente" else {}),
             "blacklist_override": override, "created_by": user.get("email"), "enabled": True, "deleted": False,
             "created_at": now_iso()}
    await db.visits.insert_one(dict(visit))
    visit.pop("_id", None)
    detail = f"{visitor['name']} → {c['host']['name']} ({status})" + (f" · LIBERADO LISTA NEGRA: {override}" if override else "")
    await log_audit(user, "visita", "visit", visit["id"], detail, client_ip(request))
    sync = await sync_to_devices(visit_subject(visitor, visit), "Visitante")
    await db.visits.update_one({"id": visit["id"]}, {"$set": {"sync": sync}})
    visitor.pop("photo", None)
    return {"visit": visit, "visitor": visitor, "sync": sync}


@router.post("/{visit_id}/end")
async def finish(visit_id: str, request: Request, user: dict = Depends(require_role(*WRITE))):
    v = await db.visits.find_one({"id": visit_id}, {"_id": 0})
    if not v:
        raise HTTPException(status_code=404, detail="Visita não encontrada")
    if v.get("status") not in ACTIVE:
        raise HTTPException(status_code=400, detail=f"Visita já encerrada ({v.get('status')})")
    sync = await end_visit(v, "finalizado", "Check-out antecipado", user.get("email"))
    await log_audit(user, "checkout", "visit", visit_id, v.get("visitor_name", ""), client_ip(request))
    return {"ok": True, "sync": sync}

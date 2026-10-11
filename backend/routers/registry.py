import re
from fastapi import APIRouter, Depends, HTTPException, Request
from database import db
from security import get_current_user, require_role
from models import new_id, now_iso
from photo_quality import check_photo, make_thumb
from registry_common import (ND, only_digits, valid_cpf, fmt_cpf, today, in_days, d10,
                             inside_area_ids, refresh_expired, sync_to_devices)
from util import log_audit, client_ip

router = APIRouter(prefix="/registry", tags=["registry"])
WRITE = ("admin", "operator", "reception")
LIST_FIELDS = {"_id": 0, "photo": 0}
PERSON_FIELDS = ["person_type", "name", "cpf", "rg", "document", "birth", "phone", "email", "company_id",
                 "notes", "matricula", "department", "role_title", "manager", "admission_date", "valid_from",
                 "valid_until", "category_ids", "status", "photo", "consent", "function", "contract_manager"]


def rx(q):
    return {"$regex": re.escape(q), "$options": "i"}


@router.post("/photo/check")
async def photo_check(body: dict, user: dict = Depends(get_current_user)):
    if not body.get("image"):
        raise HTTPException(status_code=400, detail="Imagem não enviada")
    return check_photo(body["image"])


@router.get("/companies")
async def companies(q: str = "", type: str = "", user: dict = Depends(get_current_user)):
    await refresh_expired()
    query = {**ND}
    if q:
        query["$or"] = [{"name": rx(q)}, {"trade_name": rx(q)}, {"cnpj": rx(q)}]
    if type:
        query["type"] = type
    comps = await db.companies.find(query, {"_id": 0}).sort("name", 1).to_list(2000)
    groups = {g["id"]: g["name"] for g in await db.company_groups.find(ND, {"_id": 0}).to_list(500)}
    inside = set(await inside_area_ids())
    people = await db.people.find(ND, {"_id": 0, "id": 1, "company_id": 1, "status": 1, "current_area_id": 1,
                                       "valid_until": 1}).to_list(50000)
    soon, t = in_days(7), today()
    docs = await db.person_documents.find({**ND, "valid_until": {"$lte": soon}}, {"_id": 0, "file": 0}).to_list(50000)
    pcomp = {p["id"]: p.get("company_id") for p in people}
    stats = {}
    for p in people:
        s = stats.setdefault(p.get("company_id"), {"total": 0, "active": 0, "blocked": 0, "present": 0, "expiring": 0, "docs": 0})
        s["total"] += 1
        s["active"] += p.get("status") == "ativo"
        s["blocked"] += p.get("status") in ("bloqueado", "vencido")
        s["present"] += p.get("current_area_id") in inside and p.get("status") == "ativo"
        vu = d10(p.get("valid_until"))
        s["expiring"] += bool(vu and t <= vu <= soon)
    for d in docs:
        cid = pcomp.get(d["person_id"])
        if cid in stats:
            stats[cid]["docs"] += 1
    for c in comps:
        s = stats.get(c["id"], {"total": 0, "active": 0, "blocked": 0, "present": 0, "expiring": 0, "docs": 0})
        alerts = []
        cv = d10(c.get("contract_valid_until"))
        if cv and cv < t:
            alerts.append("Contrato vencido")
        elif cv and cv <= soon:
            alerts.append("Contrato vence em até 7 dias")
        if s["docs"]:
            alerts.append(f"{s['docs']} documento(s) vencido(s)/vencendo em 7 dias")
        if s["expiring"]:
            alerts.append(f"{s['expiring']} validade(s) vencendo em 7 dias")
        c.update({"stats": s, "alerts": alerts, "group_name": groups.get(c.get("group_id"), "")})
    return comps


@router.get("/people")
async def list_people(company_id: str = "", q: str = "", status: str = "", category_id: str = "",
                      department: str = "", present: str = "", skip: int = 0, limit: int = 50,
                      user: dict = Depends(get_current_user)):
    query = {**ND}
    if company_id:
        query["company_id"] = company_id
    if q:
        ors = [{"name": rx(q)}, {"cpf": rx(q)}, {"matricula": rx(q)}, {"document": rx(q)}, {"rg": rx(q)}]
        if len(only_digits(q)) >= 3:
            ors.append({"cpf_digits": {"$regex": only_digits(q)}})
        query["$or"] = ors
    if status:
        query["status"] = status
    if category_id:
        query["category_ids"] = category_id
    if department:
        query["department"] = department
    inside = await inside_area_ids()
    if present == "true":
        query["current_area_id"] = {"$in": inside}
        query["status"] = "ativo"
    total = await db.people.count_documents(query)
    items = await db.people.find(query, LIST_FIELDS).sort("name", 1).skip(skip).limit(min(limit, 200)).to_list(200)
    ids = [p["id"] for p in items]
    creds = {}
    for i in await db.identifiers.find({**ND, "person_id": {"$in": ids}}, {"_id": 0, "person_id": 1, "type": 1}).to_list(5000):
        creds.setdefault(i["person_id"], set()).add(i["type"])
    for v in await db.vehicles.find({**ND, "person_id": {"$in": ids}}, {"_id": 0, "person_id": 1}).to_list(5000):
        creds.setdefault(v["person_id"], set()).add("placa")
    cats = {c["id"]: c["code"] for c in await db.categories.find(ND, {"_id": 0, "id": 1, "code": 1}).to_list(500)}
    for p in items:
        p["cred_types"] = sorted(creds.get(p["id"], set()))
        p["present"] = p.get("current_area_id") in inside
        p["category_names"] = [cats[c] for c in p.get("category_ids", []) if c in cats]
    stats = None
    if company_id:
        base = {**ND, "company_id": company_id}
        stats = {"total": await db.people.count_documents(base),
                 "active": await db.people.count_documents({**base, "status": "ativo"}),
                 "blocked": await db.people.count_documents({**base, "status": {"$in": ["bloqueado", "vencido"]}}),
                 "present": await db.people.count_documents({**base, "status": "ativo", "current_area_id": {"$in": inside}})}
    depts = await db.people.distinct("department", {**ND, **({"company_id": company_id} if company_id else {})})
    return {"items": items, "total": total, "stats": stats, "departments": sorted([d for d in depts if d])}


@router.get("/search")
async def global_search(q: str = "", user: dict = Depends(get_current_user)):
    q = q.strip()
    if len(q) < 2:
        return []
    dig = only_digits(q)
    ors = [{"name": rx(q)}, {"cpf": rx(q)}, {"document": rx(q)}, {"matricula": rx(q)}, {"rg": rx(q)}]
    if len(dig) >= 3:
        ors.append({"cpf_digits": {"$regex": dig}})
    found = {}
    for p in await db.people.find({**ND, "$or": ors}, LIST_FIELDS).limit(15).to_list(15):
        found[p["id"]] = (p, "Cadastro")
    idents = await db.identifiers.find({**ND, "type": {"$ne": "facial"}, "$or": [{"value": rx(q)}, {"hex": rx(q)}]},
                                       {"_id": 0}).limit(10).to_list(10)
    plate = re.sub(r"[^A-Za-z0-9]", "", q).upper()
    vehs = await db.vehicles.find({**ND, "person_id": {"$ne": None}, "plate": {"$regex": re.escape(plate)}},
                                  {"_id": 0}).limit(10).to_list(10) if len(plate) >= 3 else []
    extra = [(i["person_id"], f"{'Cartão' if i['type'] == 'cartao' else i['type'].upper()} {i.get('value')}") for i in idents]
    extra += [(v["person_id"], f"Placa {v['plate']}") for v in vehs]
    for pid, match in extra:
        if pid and pid not in found:
            p = await db.people.find_one({**ND, "id": pid}, LIST_FIELDS)
            if p:
                found[pid] = (p, match)
    out = [{"kind": "person", "id": p["id"], "name": p["name"], "company_id": p.get("company_id"),
            "company_name": p.get("company_name", ""), "photo": p.get("photo_thumb", ""), "status": p.get("status"),
            "person_type": p.get("person_type"), "match": m, "document": p.get("cpf") or p.get("matricula")}
           for p, m in found.values()]
    vq = [{"name": rx(q)}, {"document": rx(q)}]
    if len(dig) >= 3:
        vq += [{"document_digits": {"$regex": dig}}, {"cpf_digits": {"$regex": dig}}]
    for v in await db.visitors.find({**ND, "$or": vq}, {"_id": 0, "photo": 0}).limit(10).to_list(10):
        out.append({"kind": "visitor", "id": v["id"], "name": v["name"], "company_name": v.get("origin_company", ""),
                    "photo": v.get("photo_thumb", ""), "status": "lista negra" if v.get("blacklist") else "visitante",
                    "person_type": "visitante", "match": "Visitante", "document": v.get("document")})
    return out[:25]


@router.get("/people/{pid}")
async def get_person(pid: str, user: dict = Depends(get_current_user)):
    p = await db.people.find_one({"id": pid}, {"_id": 0})
    if not p:
        raise HTTPException(status_code=404, detail="Pessoa não encontrada")
    p["identifiers"] = await db.identifiers.find({**ND, "person_id": pid, "type": {"$ne": "facial"}}, {"_id": 0}).to_list(50)
    p["vehicles"] = await db.vehicles.find({**ND, "person_id": pid}, {"_id": 0}).to_list(20)
    p["documents"] = await db.person_documents.find({**ND, "person_id": pid}, {"_id": 0}).to_list(50)
    p["history"] = await db.access_events.find(
        {"person_id": pid}, {"_id": 0, "id": 1, "timestamp": 1, "door_name": 1, "area_name": 1,
                             "access_result": 1, "reason": 1, "direction": 1, "credential_type": 1}
    ).sort("timestamp", -1).limit(20).to_list(20)
    area = await db.areas.find_one({"id": p.get("current_area_id")}, {"_id": 0, "description": 1})
    p["current_area_name"] = area["description"] if area else "—"
    p["present"] = p.get("current_area_id") in await inside_area_ids()
    return p


def _validate(b):
    f = {}
    t = b.get("person_type")
    if t not in ("funcionario", "terceiro"):
        f["person_type"] = "Selecione o tipo"
    if not (b.get("name") or "").strip():
        f["name"] = "Informe o nome completo"
    if not valid_cpf(b.get("cpf")):
        f["cpf"] = "CPF inválido"
    if not b.get("company_id"):
        f["company_id"] = "Selecione a empresa"
    if not b.get("category_ids"):
        f["category_ids"] = "Selecione ao menos uma categoria"
    if t == "funcionario" and not (b.get("matricula") or "").strip():
        f["matricula"] = "Informe a matrícula"
    if t == "terceiro":
        if not b.get("valid_from"):
            f["valid_from"] = "Informe o início da validade"
        if not b.get("valid_until"):
            f["valid_until"] = "Informe o fim da validade"
    for i, idt in enumerate(b.get("identifiers") or []):
        if idt.get("type") == "cartao" and not only_digits(idt.get("value")):
            f[f"identifiers.{i}"] = "Número do cartão inválido"
        if idt.get("type") == "pin" and not re.fullmatch(r"\d{4,8}", idt.get("value") or ""):
            f[f"identifiers.{i}"] = "PIN deve ter de 4 a 8 dígitos"
    return f


async def _save_children(pid, b, valid_until):
    await db.identifiers.delete_many({"person_id": pid})
    idents = [i for i in (b.get("identifiers") or []) if i.get("type") and (i.get("value") or "").strip()]
    if b.get("photo"):
        idents.append({"type": "facial", "value": "template"})
    for i in idents:
        doc = {"id": new_id(), "person_id": pid, "type": i["type"], "value": str(i["value"]).strip(),
               "format": i.get("format", ""), "active": i.get("active", True), "valid_until": valid_until,
               "enabled": True, "deleted": False, "created_at": now_iso()}
        if i["type"] == "cartao":
            doc["value"] = only_digits(i["value"])
            doc["hex"] = format(int(doc["value"]), "X")
        await db.identifiers.insert_one(doc)
    await db.vehicles.delete_many({"person_id": pid})
    for v in b.get("vehicles") or []:
        plate = re.sub(r"[^A-Za-z0-9]", "", v.get("plate") or "").upper()
        if plate:
            await db.vehicles.insert_one({"id": new_id(), "person_id": pid, "plate": plate, "model": v.get("model", ""),
                                          "color": v.get("color", ""), "enabled": True, "deleted": False, "created_at": now_iso()})
    await db.person_documents.delete_many({"person_id": pid})
    for d in b.get("documents") or []:
        if d.get("type"):
            await db.person_documents.insert_one({"id": new_id(), "person_id": pid, "type": d["type"],
                                                  "valid_until": d.get("valid_until") or None, "file": d.get("file", ""),
                                                  "file_name": d.get("file_name", ""), "deleted": False,
                                                  "created_at": now_iso()})


async def _save(b, request, user, pid=None):
    errs = _validate(b)
    cpf_d = only_digits(b.get("cpf"))
    dup = await db.people.find_one({**ND, "cpf_digits": cpf_d, **({"id": {"$ne": pid}} if pid else {})}, {"_id": 0, "name": 1})
    if dup:
        errs["cpf"] = f"CPF já cadastrado ({dup['name']})"
    for i, idt in enumerate(b.get("identifiers") or []):
        if idt.get("type") == "cartao" and only_digits(idt.get("value")):
            other = await db.identifiers.find_one({**ND, "type": "cartao", "value": only_digits(idt["value"]),
                                                   **({"person_id": {"$ne": pid}} if pid else {})})
            if other:
                errs[f"identifiers.{i}"] = "Cartão já vinculado a outra pessoa"
    if errs:
        raise HTTPException(status_code=422, detail={"msg": "Verifique os campos destacados", "fields": errs})
    comp = await db.companies.find_one({"id": b["company_id"]}, {"_id": 0})
    if not comp:
        raise HTTPException(status_code=422, detail={"msg": "Empresa não encontrada", "fields": {"company_id": "Empresa inválida"}})
    doc = {k: b.get(k) for k in PERSON_FIELDS if k in b}
    doc.update({"cpf": fmt_cpf(cpf_d), "cpf_digits": cpf_d, "company_name": comp["name"],
                "company_group_id": comp.get("group_id"), "photo_thumb": make_thumb(b.get("photo") or ""),
                "status": b.get("status") or "ativo", "updated_at": now_iso()})
    if pid:
        if not await db.people.find_one({"id": pid}):
            raise HTTPException(status_code=404, detail="Pessoa não encontrada")
        await db.people.update_one({"id": pid}, {"$set": doc})
        action = "editar"
    else:
        ext = await db.areas.find_one({**ND, "description": {"$regex": "Externa Pedestre"}}, {"_id": 0}) or \
            await db.areas.find_one({"is_exterior": True}, {"_id": 0}) or {}
        pid = new_id()
        doc.update({"id": pid, "enabled": True, "deleted": False, "created_at": now_iso(),
                    "current_area_id": ext.get("id")})
        await db.people.insert_one(dict(doc))
        action = "criar"
    await _save_children(pid, b, b.get("valid_until"))
    await refresh_expired([pid])
    person = await db.people.find_one({"id": pid}, {"_id": 0})
    await log_audit(user, action, "person", pid, f"{person['name']} ({person['person_type']})", client_ip(request))
    sync = await sync_to_devices(person, "Pessoa")
    person.pop("photo", None)
    return {"person": person, "sync": sync}


@router.post("/people")
async def create_person(body: dict, request: Request, user: dict = Depends(require_role(*WRITE))):
    return await _save(body, request, user)


@router.put("/people/{pid}")
async def update_person(pid: str, body: dict, request: Request, user: dict = Depends(require_role(*WRITE))):
    return await _save(body, request, user, pid)


@router.delete("/people/{pid}")
async def delete_person(pid: str, request: Request, user: dict = Depends(require_role("admin", "operator"))):
    p = await db.people.find_one({"id": pid}, {"_id": 0})
    if not p:
        raise HTTPException(status_code=404, detail="Pessoa não encontrada")
    await db.people.update_one({"id": pid}, {"$set": {"deleted": True, "enabled": False, "status": "inativo"}})
    await log_audit(user, "excluir", "person", pid, f"exclusão lógica: {p['name']}", client_ip(request))
    await sync_to_devices(p, "Remoção", remove=True)
    return {"ok": True}


@router.post("/people/bulk")
async def bulk(body: dict, request: Request, user: dict = Depends(require_role(*WRITE))):
    ids, action = body.get("ids") or [], body.get("action")
    if not ids:
        raise HTTPException(status_code=400, detail="Nenhuma pessoa selecionada")
    q = {"id": {"$in": ids}}
    if action == "set_category":
        if not body.get("category_ids"):
            raise HTTPException(status_code=400, detail="Selecione a categoria")
        await db.people.update_many(q, {"$set": {"category_ids": body["category_ids"]}})
    elif action == "block":
        await db.people.update_many(q, {"$set": {"status": "bloqueado", "status_reason": body.get("reason") or "Bloqueio manual"}})
    elif action == "unblock":
        await db.people.update_many(q, {"$set": {"status": "ativo", "status_reason": ""}})
        await refresh_expired(ids)
    elif action == "renew":
        if not body.get("valid_until"):
            raise HTTPException(status_code=400, detail="Informe a nova validade")
        await db.people.update_many(q, {"$set": {"valid_until": body["valid_until"]}})
        await db.identifiers.update_many({"person_id": {"$in": ids}}, {"$set": {"valid_until": body["valid_until"]}})
        await refresh_expired(ids)
    elif action != "sync":
        raise HTTPException(status_code=400, detail="Ação inválida")
    ok = err = 0
    for p in await db.people.find(q, {"_id": 0}).to_list(len(ids)):
        res = await sync_to_devices(p, "Lote")
        ok += all(r["status"] == "ok" for r in res)
        err += any(r["status"] == "erro" for r in res)
    await log_audit(user, f"bulk_{action}", "person", ",".join(ids[:5]), f"{len(ids)} pessoas", client_ip(request))
    return {"ok": True, "affected": len(ids), "synced": ok, "sync_errors": err}

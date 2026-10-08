import io
import csv
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from fastapi.responses import StreamingResponse
from database import db, clean
from models import PersonInput, new_id, now_iso
from security import get_current_user, require_role
from util import log_audit, client_ip

router = APIRouter(prefix="/people", tags=["people"])


@router.get("")
async def list_people(q: str = "", status: str = "", department: str = "",
                      page: int = 1, limit: int = 20, user: dict = Depends(get_current_user)):
    query = {}
    if q:
        query["$or"] = [
            {"name": {"$regex": q, "$options": "i"}},
            {"matricula": {"$regex": q, "$options": "i"}},
            {"document": {"$regex": q, "$options": "i"}},
        ]
    if status:
        query["status"] = status
    if department:
        query["department"] = department
    total = await db.people.count_documents(query)
    skip = (page - 1) * limit
    items = await db.people.find(query, {"_id": 0}).sort("name", 1).skip(skip).limit(limit).to_list(limit)
    return {"items": items, "total": total, "page": page, "limit": limit}


@router.get("/{person_id}")
async def get_person(person_id: str, user: dict = Depends(get_current_user)):
    person = await db.people.find_one({"id": person_id}, {"_id": 0})
    if not person:
        raise HTTPException(status_code=404, detail="Pessoa não encontrada")
    person["credentials"] = await db.credentials.find({"person_id": person_id}, {"_id": 0}).to_list(50)
    return person


@router.post("")
async def create_person(payload: PersonInput, request: Request, user: dict = Depends(require_role("admin", "operator", "reception"))):
    doc = {"id": new_id(), **payload.model_dump(), "created_at": now_iso()}
    await db.people.insert_one(dict(doc))
    await log_audit(user, "criar", "person", doc["id"], payload.name, client_ip(request))
    return clean(doc)


@router.put("/{person_id}")
async def update_person(person_id: str, payload: PersonInput, request: Request, user: dict = Depends(require_role("admin", "operator", "reception"))):
    if not await db.people.find_one({"id": person_id}):
        raise HTTPException(status_code=404, detail="Pessoa não encontrada")
    await db.people.update_one({"id": person_id}, {"$set": payload.model_dump()})
    await log_audit(user, "editar", "person", person_id, payload.name, client_ip(request))
    return clean(await db.people.find_one({"id": person_id}))


@router.delete("/{person_id}")
async def delete_person(person_id: str, request: Request, user: dict = Depends(require_role("admin"))):
    """Exclusão definitiva (LGPD): remove pessoa, credenciais e biometria."""
    await db.people.delete_one({"id": person_id})
    await db.credentials.delete_many({"person_id": person_id})
    await log_audit(user, "excluir_lgpd", "person", person_id, "Exclusão definitiva com remoção de biometria", client_ip(request))
    return {"ok": True}


@router.get("/export/csv")
async def export_csv(user: dict = Depends(get_current_user)):
    people = await db.people.find({}, {"_id": 0}).to_list(5000)
    buf = io.StringIO()
    fields = ["name", "matricula", "document", "company", "department", "role_title", "person_type", "status", "valid_until"]
    writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for p in people:
        writer.writerow(p)
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=pessoas.csv"})


@router.post("/import/csv")
async def import_csv(request: Request, file: UploadFile = File(...), user: dict = Depends(require_role("admin", "operator"))):
    content = (await file.read()).decode("utf-8", errors="ignore")
    reader = csv.DictReader(io.StringIO(content))
    created = 0
    for row in reader:
        name = (row.get("name") or row.get("nome") or "").strip()
        if not name:
            continue
        doc = {
            "id": new_id(), "name": name,
            "matricula": (row.get("matricula") or "").strip(),
            "document": (row.get("document") or row.get("documento") or "").strip(),
            "company": (row.get("company") or row.get("empresa") or "").strip(),
            "department": (row.get("department") or row.get("departamento") or "").strip(),
            "role_title": (row.get("role_title") or row.get("cargo") or "").strip(),
            "person_type": (row.get("person_type") or "colaborador").strip(),
            "status": (row.get("status") or "ativo").strip(),
            "photo": "", "valid_until": row.get("valid_until") or None,
            "consent": False, "created_at": now_iso(),
        }
        await db.people.insert_one(doc)
        created += 1
    await log_audit(user, "importar_csv", "person", "", f"{created} pessoas importadas", client_ip(request))
    return {"ok": True, "created": created}

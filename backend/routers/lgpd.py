"""Exclusão definitiva (LGPD): apaga cadastro, foto, face, cartões e placas; anonimiza o histórico."""
import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request

from database import db
from models import new_id, now_iso
from registry_common import sync_to_devices
from security import require_role
from util import log_audit, client_ip

router = APIRouter(prefix="/lgpd", tags=["lgpd"])
ANON = "Pessoa removida (LGPD)"
_BG = set()


def _initials(name):
    return "".join(p[0].upper() for p in str(name or "").split() if p)[:4] or "?"


async def _remove_from_devices(sid):
    try:
        await sync_to_devices({"id": sid, "name": ANON}, "LGPD", remove=True)
    except Exception:  # noqa: BLE001
        pass


@router.post("/erase")
async def erase(body: dict, request: Request, user: dict = Depends(require_role("admin"))):
    kind = str(body.get("kind") or "")
    sid = str(body.get("id") or "")
    just = str(body.get("justification") or "").strip()
    if kind not in ("person", "visitor") or not sid:
        raise HTTPException(status_code=400, detail="Informe o tipo e o cadastro")
    if len(just) < 10:
        raise HTTPException(status_code=422, detail="Justificativa obrigatória (mínimo 10 caracteres)")
    coll = db.people if kind == "person" else db.visitors
    rec = await coll.find_one({"id": sid}, {"_id": 0, "id": 1, "name": 1, "email": 1, "doc_key": 1})
    if not rec:
        raise HTTPException(status_code=404, detail="Cadastro não encontrado")
    n = {}
    n["eventos"] = (await db.access_events.update_many(
        {"person_id": sid}, {"$set": {"person_id": None, "person_name": ANON, "person_photo": "", "captured_photo": "",
                                      "document": "", "person_document": "", "anonymized": True}})).modified_count
    if kind == "visitor":
        n["visitas"] = (await db.visits.update_many(
            {"visitor_id": sid}, {"$set": {"visitor_id": None, "visitor_name": ANON, "visitor_document": "", "doc_number": "",
                                           "doc_key": "", "visitor_company": "", "origin_company": "", "plate": "",
                                           "vehicle_plate": "", "email": "", "phone": "", "credential_value": "",
                                           "anonymized": True}})).modified_count
        await db.visit_history.update_many({"visitor_id": sid}, {"$set": {"visitor_id": None, "visitor_name": ANON}})
        ors = [{"visitor_id": sid}] + ([{"doc_key": rec["doc_key"]}] if rec.get("doc_key") else [])
        n["solicitacoes"] = (await db.self_registrations.delete_many({"$or": ors})).deleted_count
    else:
        n["visitas_anfitriao"] = (await db.visits.update_many(
            {"$or": [{"host_id": sid}, {"host_person_id": sid}]}, {"$set": {"host_name": ANON}})).modified_count
        n["identificadores"] = (await db.identifiers.delete_many({"person_id": sid})).deleted_count
        n["veiculos"] = (await db.vehicles.delete_many({"person_id": sid})).deleted_count
    await db.sync_jobs.update_many({"person_id": sid}, {"$set": {"device_name": f"LGPD: {ANON}", "person_id": None}})
    n["comandos_mqtt"] = (await db.mqtt_commands.delete_many({"payload.info.customId": sid})).deleted_count
    await db.audit_logs.update_many({"entity_id": sid}, {"$set": {"details": ANON}})
    if rec.get("email"):
        await db.notifications.delete_many({"to": rec["email"]})
    await coll.delete_one({"id": sid})
    await db.lgpd_erasures.insert_one({"id": new_id(), "kind": kind, "subject_id": sid, "initials": _initials(rec.get("name")),
                                       "justification": just[:500], "by": user.get("email"), "at": now_iso(), "counts": n})
    await log_audit(user, "lgpd-exclusao", kind, sid, f"{_initials(rec.get('name'))} · {just[:200]}", client_ip(request))
    _BG.add(t := asyncio.create_task(_remove_from_devices(sid)))
    t.add_done_callback(_BG.discard)
    return {"ok": True, "counts": n}


@router.get("/erasures")
async def erasures(user: dict = Depends(require_role("admin"))):
    return await db.lgpd_erasures.find({}, {"_id": 0}).sort("at", -1).to_list(500)

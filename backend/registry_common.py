import re
import asyncio
from datetime import datetime, timezone, timedelta
from database import db
from drivers.factory import get_driver
from models import new_id, now_iso

ND = {"deleted": {"$ne": True}}


def only_digits(s):
    return re.sub(r"\D", "", s or "")


def valid_cpf(cpf):
    d = only_digits(cpf)
    if len(d) != 11 or d == d[0] * 11:
        return False
    for i in (9, 10):
        s = sum(int(d[k]) * ((i + 1) - k) for k in range(i))
        if (s * 10 % 11) % 10 != int(d[i]):
            return False
    return True


def fmt_cpf(d):
    d = only_digits(d)
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}" if len(d) == 11 else d


def today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def in_days(n):
    return (datetime.now(timezone.utc) + timedelta(days=n)).strftime("%Y-%m-%d")


def d10(s):
    return (s or "")[:10]


async def inside_area_ids():
    areas = await db.areas.find(ND, {"_id": 0, "id": 1, "description": 1, "is_exterior": 1}).to_list(500)
    return [a["id"] for a in areas if not a.get("is_exterior") and "extern" not in a.get("description", "").lower()]


def expiry_reason(p, docs, comp, t):
    vu = d10(p.get("valid_until"))
    if vu and vu < t:
        return "Validade do acesso expirada"
    for d in docs:
        dv = d10(d.get("valid_until"))
        if dv and dv < t:
            return f"Documento vencido: {d.get('type')}"
    if comp and comp.get("type") not in (None, "propria"):
        cv = d10(comp.get("contract_valid_until"))
        if cv and cv < t:
            return "Contrato da empresa vencido"
    return None


async def refresh_expired(ids=None):
    """Bloqueio automático por vencimento (validade, documento ou contrato)."""
    t = today()
    q = {**ND, "status": {"$in": ["ativo", "vencido"]}}
    if ids:
        q["id"] = {"$in": ids}
    people = await db.people.find(q, {"_id": 0, "id": 1, "status": 1, "valid_until": 1, "company_id": 1}).to_list(20000)
    docs = await db.person_documents.find({**ND, "person_id": {"$in": [p["id"] for p in people]}},
                                          {"_id": 0, "file": 0}).to_list(100000)
    by = {}
    for d in docs:
        by.setdefault(d["person_id"], []).append(d)
    comps = {c["id"]: c for c in await db.companies.find({}, {"_id": 0, "id": 1, "type": 1, "contract_valid_until": 1}).to_list(5000)}
    changed = 0
    for p in people:
        r = expiry_reason(p, by.get(p["id"], []), comps.get(p.get("company_id")), t)
        new = "vencido" if r else "ativo"
        if new != p["status"]:
            await db.people.update_one({"id": p["id"]}, {"$set": {"status": new, "status_reason": r or ""}})
            changed += 1
    now = now_iso()
    await db.visits.update_many({**ND, "status": "agendado", "expected_end": {"$lt": now}},
                                {"$set": {"status": "expirada"}})
    return changed


async def sync_to_devices(subject: dict, label: str, remove=False):
    """Envia (ou remove) a pessoa/visitante a todas as controladoras ativas e registra o log."""
    ctrls = await db.controllers.find({**ND, "enabled": {"$ne": False}}, {"_id": 0}).to_list(200)
    results = []
    for c in ctrls:
        try:
            drv = get_driver(c)
            if remove or subject.get("status") != "ativo":
                r = await asyncio.wait_for(drv.delete_person(subject["id"]), 12)
            else:
                r = await asyncio.wait_for(drv.sync_person(subject), 12)
                if r.get("ok") and subject.get("photo"):
                    await asyncio.wait_for(drv.sync_face(subject["id"], subject["photo"]), 12)
            ok = bool(r.get("ok"))
            results.append({"controller_id": c["id"], "name": c.get("name"), "status": "ok" if ok else "erro",
                            "error": "" if ok else str(r.get("error") or "falha")})
        except Exception as e:  # noqa: BLE001
            results.append({"controller_id": c["id"], "name": c.get("name"), "status": "erro",
                            "error": str(e)[:120] or "timeout"})
    success = sum(1 for r in results if r["status"] == "ok")
    job = {"id": new_id(), "controller_id": None, "device_id": None,
           "device_name": f"{label}: {subject.get('name')}", "person_id": subject["id"],
           "started_at": now_iso(), "finished_at": now_iso(),
           "status": "concluido" if success == len(results) else "erro",
           "totals": {"people": 1, "devices": len(results)}, "total": len(results), "success": success,
           "errors": [r for r in results if r["status"] == "erro"], "devices": results}
    await db.sync_jobs.insert_one(dict(job))
    return results

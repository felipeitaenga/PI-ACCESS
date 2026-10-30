"""Liberação manual pelo operador (portaria).

Dois jeitos, sempre com motivo obrigatório e registro de quem liberou:
  1) a partir de um evento NEGADO (botão "Liberar" no feed): abre o ponto daquele evento e gera um evento
     "Liberação manual" com a pessoa/foto do evento original + operador; o original fica marcado como liberado.
  2) direto num ponto de acesso (tela Liberação manual): opcionalmente informando quem está passando.
Regras: evento negado só pode ser liberado até OVERRIDE_MAX_MIN depois; lista negra e categoria impeditiva
só o Administrador libera.
"""
from datetime import datetime, timezone

from fastapi import HTTPException

from database import db
from drivers.factory import get_driver
from models import new_id, now_iso
from realtime import manager
from scope import stamp_event
from util import log_audit

OVERRIDE_MAX_MIN = 10
ADMIN_ONLY_REASONS = ("Categoria impeditiva", "Lista negra", "lista negra")


def _clean_reason(reason):
    r = (reason or "").strip()
    if len(r) < 3:
        raise HTTPException(status_code=422, detail="Informe o motivo da liberação (mínimo 3 caracteres)")
    return r[:300]


async def _subject(kind, sid):
    if not sid:
        return None
    if kind == "visitor":
        v = await db.visitors.find_one({"id": sid, "deleted": {"$ne": True}}, {"_id": 0})
        if v:
            from visits_core import visitor_person
            p = await visitor_person(sid) or {}
            return {**p, "id": v["id"], "name": v["name"], "person_type": "visitante", "photo": v.get("photo_thumb") or v.get("photo", ""),
                    "company_name": v.get("origin_company", ""), "blacklist": bool(v.get("blacklist"))}
        return None
    p = await db.people.find_one({"id": sid, "deleted": {"$ne": True}}, {"_id": 0})
    return {**p, "photo": p.get("photo_thumb") or p.get("photo", "")} if p else None


async def _open(ap):
    ctrl = await db.controllers.find_one({"id": ap.get("controller_id")}, {"_id": 0})
    await db.access_points.update_one({"id": ap["id"]}, {"$set": {"last_remote_open": now_iso()}})
    try:
        r = await get_driver(ctrl or {"brand": "simulado"}).open_door(ap["id"], int(ap.get("relay_time") or 5)) or {}
    except Exception as e:  # noqa: BLE001
        r = {"ok": False, "detail": str(e)[:120]}
    return bool(r.get("ok", True)), r.get("detail") or r.get("error") or ""


async def _count_passage(person, ap, event):
    """Pessoa identificada: conta a entrada (ou deixa pendente se o ponto confirma pelo giro)."""
    import passage
    if not person or not person.get("id"):
        return
    dest = await db.areas.find_one({"id": ap.get("dest_area_id")}, {"_id": 0}) or {}
    origin = await db.areas.find_one({"id": ap.get("origin_area_id")}, {"_id": 0}) or {}
    if passage.is_confirm(ap):
        event["passage"] = "pendente"
        await db.access_events.update_one({"id": event["id"]}, {"$set": {"passage": "pendente"}})
        await passage.create_pending(event, person, ap, dest, origin)
    else:
        await passage.apply_entry(person, dest, origin)


async def release(user, ap_id, reason, ip="", event_id=None, subject_kind=None, subject_id=None):
    reason = _clean_reason(reason)
    original = None
    if event_id:
        original = await db.access_events.find_one({"id": event_id}, {"_id": 0})
        if not original:
            raise HTTPException(status_code=404, detail="Evento não encontrado")
        if original.get("access_result") != "denied":
            raise HTTPException(status_code=409, detail="Só eventos negados podem ser liberados manualmente")
        if original.get("released_by_event"):
            raise HTTPException(status_code=409, detail=f"Já liberado por {original.get('released_by_name') or 'outro operador'}")
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(original["timestamp"])).total_seconds() / 60
        if age > OVERRIDE_MAX_MIN:
            raise HTTPException(status_code=409, detail=f"Evento com mais de {OVERRIDE_MAX_MIN} min: use a Liberação manual do ponto")
        ap_id = original.get("access_point_id") or original.get("door_id")
    ap = await db.access_points.find_one({"id": ap_id, "deleted": {"$ne": True}}, {"_id": 0})
    if not ap:
        raise HTTPException(status_code=404, detail="Ponto de acesso não encontrado")

    if original and original.get("person_id"):
        kind = "visitor" if original.get("person_type") == "visitante" else "person"
        person = await _subject(kind, original["person_id"])
    else:
        person = await _subject(subject_kind, subject_id) if subject_id else None
    blocked = (person or {}).get("blacklist") or (person or {}).get("status") == "bloqueado" or \
        any(x in (original or {}).get("reason", "") for x in ADMIN_ONLY_REASONS)
    if blocked and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Pessoa em lista negra/bloqueada ou categoria impeditiva: só o Administrador pode liberar")

    ok, detail = await _open(ap)
    dest = await db.areas.find_one({"id": ap.get("dest_area_id")}, {"_id": 0}) or {}
    op = user.get("name") or user.get("email") or "operador"
    who = (person or {}).get("name") or (original or {}).get("person_name") or "Não identificado"
    event = {
        "id": new_id(), "timestamp": now_iso(), "site_id": ap.get("site_id"), "site_name": ap.get("site_name", ""),
        "area_id": dest.get("id"), "area_name": dest.get("description", ""), "door_id": ap["id"], "door_name": ap.get("description"),
        "access_point_id": ap["id"], "controller_id": ap.get("controller_id"), "device_id": ap.get("controller_id"),
        "person_id": (person or {}).get("id") or (original or {}).get("person_id"), "person_name": who,
        "person_type": (person or {}).get("person_type") or (original or {}).get("person_type", ""),
        "company_name": (person or {}).get("company_name") or (original or {}).get("company_name", ""),
        "person_photo": (person or {}).get("photo") or (original or {}).get("person_photo", ""),
        "captured_photo": (original or {}).get("captured_photo", ""),
        "credential_type": "manual", "direction": ap.get("direction", "entrada"), "access_result": "granted",
        "reason": f"Liberação manual por {op}: {reason}", "match_score": (original or {}).get("match_score", 0),
        "manual": True, "operator_id": user.get("id"), "operator_name": op, "manual_reason": reason,
        "override_of": event_id, "original_reason": (original or {}).get("reason"), "device_ok": ok, "device_detail": detail,
    }
    await db.access_events.insert_one(dict(await stamp_event(event)))
    event.pop("_id", None)
    await _count_passage(person, ap, event)
    await manager.broadcast({"type": "access_event", "data": event})
    if original:
        upd = {"released_by_event": event["id"], "released_by_name": op, "released_at": event["timestamp"]}
        await db.access_events.update_one({"id": event_id}, {"$set": upd})
        await manager.broadcast({"type": "access_event_update", "data": {"id": event_id, **upd}})
    await log_audit(user, "liberacao_manual", "access_points", ap["id"],
                    f"{ap.get('description')} · {who} · {reason}" + (f" · negado antes: {original.get('reason')}" if original else "")
                    + ("" if ok else f" · FALHA NO EQUIPAMENTO: {detail}"), ip)
    return {"ok": ok, "event": event, "device_detail": detail}

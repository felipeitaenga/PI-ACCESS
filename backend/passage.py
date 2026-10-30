"""Confirmação de passagem (giro da catraca / sensor de porta).

Ponto de acesso com passage_mode="confirmacao": o acesso liberado fica PENDENTE e só conta
(área atual da pessoa, ocupação, anti-dupla) quando o sensor do facial confirmar o giro.
- giro em até passage_timeout s → "confirmada"
- sem giro                      → "nao_passou" (não conta; a pessoa pode tentar de novo)
- giro sem liberação pendente   → alarme "Passagem não autorizada" (se habilitado)
O sinal do sensor chega do driver (Intelbras: evento DoorStatus Open).
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from database import db
from models import new_id, now_iso
from realtime import manager

logger = logging.getLogger("passage")
DEFAULT_TIMEOUT = 10
DEBOUNCE_S = 2.0  # catraca manda abre/fecha no mesmo giro


def _now():
    return datetime.now(timezone.utc)


def is_confirm(ap):
    return (ap or {}).get("passage_mode") == "confirmacao"


async def apply_entry(person, dest, origin):
    """Efeitos de uma passagem efetiva: ocupação das áreas e área atual da pessoa/visita."""
    if dest and not dest.get("is_exterior"):
        await db.areas.update_one({"id": dest["id"]}, {"$inc": {"current_occupancy": 1}})
    if origin and not origin.get("is_exterior") and person.get("current_area_id") == origin.get("id"):
        await db.areas.update_one({"id": origin["id"]}, {"$inc": {"current_occupancy": -1}})
    if person.get("person_type") == "visitante":
        q = {"id": person["visit_id"]} if person.get("visit_id") else {"visitor_id": person["id"], "status": "presente"}
        await db.visits.update_many(q, {"$set": {"current_area_id": dest.get("id")}})
    else:
        await db.people.update_one({"id": person["id"]}, {"$set": {"current_area_id": dest.get("id")}})


async def create_pending(event, person, ap, dest, origin):
    timeout = int(ap.get("passage_timeout") or DEFAULT_TIMEOUT)
    await db.passages.insert_one({
        "id": new_id(), "event_id": event["id"], "access_point_id": ap["id"], "controller_id": ap.get("controller_id"),
        "status": "pendente", "created_at": now_iso(), "expires_at": (_now() + timedelta(seconds=timeout)).isoformat(),
        "person": {k: person.get(k) for k in ("id", "name", "person_type", "visit_id", "current_area_id")},
        "dest": {k: dest.get(k) for k in ("id", "is_exterior")} if dest else None,
        "origin": {k: origin.get(k) for k in ("id", "is_exterior")} if origin else None})


async def _update_event(event_id, passage, reason_suffix=""):
    ev = await db.access_events.find_one({"id": event_id}, {"_id": 0})
    if not ev:
        return
    upd = {"passage": passage, "passage_at": now_iso()}
    if reason_suffix:
        upd["reason"] = ((ev.get("reason") or "").rstrip() + reason_suffix).strip(" ·")
    await db.access_events.update_one({"id": event_id}, {"$set": upd})
    await manager.broadcast({"type": "access_event_update", "data": {"id": event_id, **upd}})


async def on_sensor(ctrl, ap=None):
    """Sinal de giro/porta aberta vindo do facial."""
    from beward_ingest import access_point_of, raise_alarm
    ap = ap or await access_point_of(ctrl)
    if not ap or not is_confirm(ap):
        return None
    ro = ap.get("last_remote_open")
    if ro and (_now() - datetime.fromisoformat(ro)).total_seconds() < 15:
        return "remoto"  # abertura remota pelo SCARVEL ou botão de saída: não é giro sem liberação
    last = ap.get("last_passage_signal")
    if last and (_now() - datetime.fromisoformat(last)).total_seconds() < DEBOUNCE_S:
        return "debounce"
    await db.access_points.update_one({"id": ap["id"]}, {"$set": {"last_passage_signal": now_iso()}})
    p = await db.passages.find_one_and_update(
        {"access_point_id": ap["id"], "status": "pendente", "expires_at": {"$gte": _now().isoformat()}},
        {"$set": {"status": "confirmada", "confirmed_at": now_iso()}}, sort=[("created_at", 1)])
    if p:
        await apply_entry(p["person"], p.get("dest") or {}, p.get("origin") or {})
        await _update_event(p["event_id"], "confirmada")
        return "confirmada"
    if ap.get("unauthorized_alarm", True):
        await raise_alarm(ctrl, "passagem_nao_autorizada",
                          f"Passagem não autorizada em '{ap.get('description')}': giro sem liberação (carona ou passagem forçada)",
                          ap.get("unauthorized_priority") or "alta", ap)
    return "nao_autorizada"


async def expire_once():
    from beward_ingest import raise_alarm
    now = _now().isoformat()
    async for p in db.passages.find({"status": "pendente", "expires_at": {"$lt": now}}, {"_id": 0}):
        r = await db.passages.update_one({"id": p["id"], "status": "pendente"}, {"$set": {"status": "nao_passou"}})
        if not r.modified_count:
            continue
        await _update_event(p["event_id"], "nao_passou", " · liberado, não passou")
        ap = await db.access_points.find_one({"id": p["access_point_id"]}, {"_id": 0}) or {}
        if ap.get("notify_not_passed"):
            ctrl = await db.controllers.find_one({"id": ap.get("controller_id")}, {"_id": 0}) or {"id": ap.get("controller_id")}
            await raise_alarm(ctrl, "liberado_nao_passou",
                              f"{p['person'].get('name') or 'Pessoa'} foi liberada em '{ap.get('description')}' e não passou",
                              "baixa", ap)


async def loop():
    while True:
        try:
            await expire_once()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"passage loop: {e}")
        await asyncio.sleep(2)

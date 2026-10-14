"""Visitas (portaria): configurações, validação de documento, cálculo de fim e expiração."""
import re
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
import os

from database import db
from models import new_id, now_iso
from registry_common import ND, only_digits, valid_cpf, fmt_cpf, sync_to_devices

logger = logging.getLogger("visits")
TZ = ZoneInfo(os.environ.get("TZ") or "America/Sao_Paulo")
DOC_TYPES = ("cpf", "rg", "passaporte", "outro")
ID_TYPES = ("facial", "cartao", "qrcode")
DEFAULT_SETTINGS = {"id": "visitors", "validate_cpf": True, "validate_rg": False, "default_hours": 8}
ACTIVE = ("agendado", "presente")


async def get_settings():
    s = await db.settings.find_one({"id": "visitors"}, {"_id": 0}) or {}
    return {**DEFAULT_SETTINGS, **s}


def validate_doc(doc_type, number, settings):
    """Retorna (numero_normalizado, erro|None) conforme as configurações."""
    n = (number or "").strip()
    if doc_type not in DOC_TYPES:
        return n, "Tipo de documento inválido"
    if not n:
        return n, "Informe o número do documento"
    if doc_type == "cpf":
        if settings.get("validate_cpf", True):
            return fmt_cpf(n), None if valid_cpf(n) else "CPF inválido"
        return n, None
    if doc_type == "rg":
        if settings.get("validate_rg"):
            v = re.sub(r"[\s.\-/]", "", n).upper()
            return v, None if re.fullmatch(r"[0-9X]{5,14}", v) else "RG inválido: somente números/X, 5 a 14 caracteres"
        return n, None
    if doc_type == "passaporte":
        return n.upper(), None
    return n, None


def doc_key(doc_type, number):
    """Chave de busca do visitante (mesmo tipo + número)."""
    n = (number or "").strip().upper()
    return only_digits(n) if doc_type == "cpf" else re.sub(r"[\s.\-/]", "", n)


def parse_dt(s):
    dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=TZ)


def compute_end(start, hours):
    """Fim da visita = início + duração (horas, aceita decimais)."""
    return parse_dt(start) + timedelta(hours=float(hours))


def type_hours(vtype, settings):
    h = (vtype or {}).get("default_hours")
    return float(h) if h not in (None, "", 0) else float(settings.get("default_hours") or 8)


def device_dt(iso):
    """'YYYY-MM-DD hh:mm:ss' no fuso local, formato do facial."""
    return parse_dt(iso).astimezone(TZ).strftime("%Y-%m-%d %H:%M:%S")


def card_decimal(value):
    """Número do cartão em decimal (aceita hexa: 0x..., ou com letras A-F)."""
    v = (value or "").strip().replace(" ", "")
    if not v:
        return ""
    if v.lower().startswith("0x"):
        return str(int(v[2:], 16))
    if re.fullmatch(r"\d+", v):
        return v
    if re.fullmatch(r"[0-9A-Fa-f]+", v):
        return str(int(v, 16))
    raise ValueError("Número do cartão inválido (use decimal ou hexadecimal)")


PLATE_RE = re.compile(r"^[A-Z]{3}-?\d[A-Z0-9]\d{2}$")


def norm_plate(p):
    v = (p or "").strip().upper().replace(" ", "")
    if not v:
        return "", None
    if not PLATE_RE.match(v):
        return v, "Placa inválida (AAA0A00 ou AAA-0000)"
    if re.fullmatch(r"[A-Z]{3}-?\d{4}", v):
        v = v.replace("-", "")
        v = f"{v[:3]}-{v[3:]}"
    return v, None


def visit_subject(visitor, visit):
    """Sujeito enviado aos equipamentos / avaliado pelo motor."""
    ident = visit.get("identifier") or {}
    s = {"id": visitor["id"], "name": visitor["name"], "photo": visitor.get("photo", ""),
         "person_type": "visitante", "document": visit.get("doc_number", ""),
         "origin_company": visitor.get("origin_company", ""),
         "status": "ativo" if visit.get("status") in ACTIVE else "inativo",
         "category_ids": visit.get("category_ids") or [],
         "valid_from": visit.get("start_at"), "valid_until": visit.get("end_at"),
         "temp_valid": True, "card_valid_begin": device_dt(visit["start_at"]),
         "card_valid_end": device_dt(visit["end_at"])}
    if ident.get("type") == "cartao" and ident.get("value"):
        s["card_number"] = ident["value"]
    return s


async def visitor_person(ref):
    """Visitante com visita ativa, no formato de pessoa para o motor de decisão."""
    v = await db.visitors.find_one({"id": ref}, {"_id": 0})
    if not v:
        return None
    visit = await db.visits.find_one({**ND, "visitor_id": ref, "status": {"$in": list(ACTIVE)}, "start_at": {"$exists": True}},
                                     {"_id": 0}, sort=[("start_at", -1)])
    if not visit:
        return {**v, "person_type": "visitante", "status": "inativo", "category_ids": []}
    return {**visit_subject(v, visit), "photo": v.get("photo_thumb", "")}


async def release_visitor(visitor_id, name, label):
    """Remove do facial; se o visitante ainda tiver outra visita ativa, reenvia com a validade dela."""
    visitor = await db.visitors.find_one({"id": visitor_id}, {"_id": 0}) or {"id": visitor_id, "name": name}
    other = await db.visits.find_one({**ND, "visitor_id": visitor_id, "status": {"$in": list(ACTIVE)}},
                                     {"_id": 0}, sort=[("end_at", -1)])
    if other and visitor.get("photo") and not visitor.get("blacklist"):
        return await sync_to_devices(visit_subject(visitor, other), f"{label} (mantido: outra visita ativa)")
    return await sync_to_devices(visitor, label, remove=True)


async def _release_and_log(visit, status, reason, user_label, now):
    try:
        sync = await release_visitor(visit["visitor_id"], visit.get("visitor_name", ""), "Fim da visita")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"remover do facial (visita {visit['id']}): {e}")
        sync = [{"status": "erro", "error": str(e)[:160]}]
    await db.visit_history.insert_one({"id": new_id(), "visit_id": visit["id"], "visitor_id": visit["visitor_id"],
                                       "visitor_name": visit.get("visitor_name"), "action": status, "reason": reason,
                                       "by": user_label, "at": now, "sync": sync})
    return sync


async def end_visit(visit, status, reason, user_label="sistema", wait=True, from_status=None):
    """Encerra a visita (atômico), remove do facial e registra no histórico. wait=False: facial em segundo plano.
    Retorna None se a visita já tinha sido encerrada por outra requisição."""
    now = now_iso()
    res = await db.visits.update_one({"id": visit["id"], "status": {"$in": list(from_status or ACTIVE)}},
                                     {"$set": {"status": status, "ended_at": now, "end_reason": reason,
                                               **({"checkout_at": now} if status == "finalizado" else {})}})
    if not res.modified_count:
        return None
    if not wait:
        _BG.add(t := asyncio.create_task(_release_and_log(visit, status, reason, user_label, now)))
        t.add_done_callback(_BG.discard)
        return []
    return await _release_and_log(visit, status, reason, user_label, now)


_BG = set()


async def visits_tick(now=None):
    """Job de 1 min: agendado→presente no início; expira vencidas e remove do facial."""
    now = (now or datetime.now(timezone.utc)).isoformat()
    await db.visits.update_many({**ND, "status": "agendado", "start_at": {"$lte": now}, "end_at": {"$gt": now}},
                                {"$set": {"status": "presente", "checkin_at": now}})
    expired = await db.visits.find({**ND, "status": {"$in": list(ACTIVE)}, "end_at": {"$lte": now}}, {"_id": 0}).to_list(500)
    for v in expired:
        try:
            await end_visit(v, "expirada", "Fim do horário da visita")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"expirar visita {v['id']}: {e}")
    return len(expired)

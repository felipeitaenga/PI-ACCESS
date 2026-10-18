"""Autocadastro de visitantes: configurações, tokens, e-mail, limites de uso e retenção (LGPD)."""
import asyncio
import hashlib
import hmac
import logging
import os
import re
import secrets
from datetime import datetime, timezone, timedelta
from email.message import EmailMessage
from html import escape

import app_config as cfg
from database import db
from models import new_id, now_iso
from registry_common import ND

logger = logging.getLogger("selfreg")

LGPD_TEXT = (
    "Para liberar sua entrada, coletamos nome, documento, e-mail, telefone, placa (opcional) e uma foto do rosto. "
    "Os dados são usados somente para controle de acesso e segurança deste local. A foto é enviada ao leitor facial "
    "apenas durante a visita e apagada após o prazo de retenção, salvo se você optar por manter o cadastro para "
    "próximas visitas (nesse caso, ela é apagada após 12 meses sem visitas). O histórico de acessos é mantido "
    "pelo prazo legal. Você pode pedir a exclusão dos seus dados à recepção a qualquer momento."
)
DEFAULTS = {"id": "selfreg", "enabled": True, "require_otp": True, "invite_hours": 72, "approval_hours": 24,
            "visitor_retention_days": 30, "recurring_months": 12, "max_days_ahead": 30, "lgpd_text": LGPD_TEXT}
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[A-Za-z]{2,24}$")
FINAL = ("aprovado", "recusado", "expirado", "cancelado")


def utcnow():
    return datetime.now(timezone.utc)


async def get_settings():
    s = await db.settings.find_one({"id": "selfreg"}, {"_id": 0}) or {}
    out = {**DEFAULTS, **s}
    out["otp_active"] = bool(out["require_otp"] and cfg.EMAIL_ENABLED)
    return out


def otp_active(settings):
    return bool(settings.get("require_otp", True) and cfg.EMAIL_ENABLED)


# ---------------- tokens ----------------
def new_token(nbytes=24):
    return secrets.token_urlsafe(nbytes)


def token_hash(token):
    return hashlib.sha256((token or "").encode()).hexdigest()


def new_code(length=8):
    """Código curto do link público (sem caracteres ambíguos)."""
    alpha = "abcdefghjkmnpqrstuvwxyz23456789"
    return "".join(secrets.choice(alpha) for _ in range(length))


def new_otp():
    return f"{secrets.randbelow(10 ** 6):06d}"


def same(a, b):
    return hmac.compare_digest(str(a or ""), str(b or ""))


def valid_email(e):
    return bool(EMAIL_RE.match((e or "").strip()))


def link(path):
    return f"{cfg.PUBLIC_URL}{path}" if cfg.PUBLIC_URL else path


def mask_doc(n):
    n = str(n or "")
    return (n[:3] + "•" * max(0, len(n) - 5) + n[-2:]) if len(n) > 5 else "•" * len(n)


def mask_email(e):
    user, _, dom = (e or "").partition("@")
    return (user[:2] + "•••@" + dom) if dom else ""


# ---------------- limite de uso ----------------
async def hit(key: str, limit: int, window_s: int) -> bool:
    """Registra uma tentativa; False se o limite da janela foi excedido."""
    now = utcnow()
    n = await db.rate_hits.count_documents({"key": key, "at": {"$gt": now - timedelta(seconds=window_s)}})
    if n >= limit:
        return False
    await db.rate_hits.insert_one({"key": key, "at": now})
    return True


# ---------------- captcha (Cloudflare Turnstile, opcional) ----------------
TURNSTILE_SITE_KEY = os.environ.get("TURNSTILE_SITE_KEY") or ""
TURNSTILE_SECRET = os.environ.get("TURNSTILE_SECRET") or ""


async def captcha_ok(token: str, ip: str) -> bool:
    if not TURNSTILE_SECRET:
        return True
    if not token:
        return False
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post("https://challenges.cloudflare.com/turnstile/v0/siteverify",
                             data={"secret": TURNSTILE_SECRET, "response": token, "remoteip": ip})
            return bool(r.json().get("success"))
    except Exception as e:  # noqa: BLE001
        logger.warning(f"turnstile: {e}")
        return False


# ---------------- e-mail ----------------
def brand():
    return f"PI-ACCESS · {cfg.CLIENTE_NOME}" if cfg.CLIENTE_NOME else "PI-ACCESS"


def _html(paragraphs, button=None):
    body = "".join(f"<p style='margin:0 0 12px'>{p}</p>" for p in paragraphs)
    if button:
        body += (f"<p style='margin:20px 0'><a href='{escape(button[1])}' style='background:#0f172a;color:#fff;"
                 f"padding:12px 20px;border-radius:6px;text-decoration:none;display:inline-block'>{escape(button[0])}</a></p>")
    return (f"<table role='presentation' width='100%'><tr><td style='padding:24px;font-family:Arial,sans-serif;"
            f"font-size:15px;color:#0f172a'>{body}<p style='font-size:12px;color:#64748b;margin-top:24px'>"
            f"Mensagem automática de {escape(brand())}. Não responda este e-mail.</p></td></tr></table>")


async def send_email(to: str, subject: str, paragraphs: list, button=None, kind="", ref="") -> bool:
    """Envia e registra em notifications. paragraphs já devem vir escapados (HTML)."""
    rec = {"id": new_id(), "channel": "email", "to": to, "subject": subject, "kind": kind, "ref": ref,
           "at": now_iso(), "ok": False, "error": ""}
    if not cfg.EMAIL_ENABLED:
        rec["error"] = "SMTP não configurado"
        await db.notifications.insert_one(rec)
        return False
    from routers.auth import _smtp_send
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{brand()} <{cfg.SMTP_FROM}>"
    msg["To"] = to
    text = "\n\n".join(re.sub(r"<[^>]+>", "", p) for p in paragraphs)
    if button:
        text += f"\n\n{button[0]}: {button[1]}"
    msg.set_content(text)
    msg.add_alternative(_html(paragraphs, button), subtype="html")
    try:
        await asyncio.to_thread(_smtp_send, msg)
        rec["ok"] = True
    except Exception as e:  # noqa: BLE001
        rec["error"] = str(e)[:200]
        logger.error(f"e-mail {kind} para {to}: {e}")
    await db.notifications.insert_one(rec)
    return rec["ok"]


# ---------------- notificação no celular (Web Push) ----------------
def push_enabled():
    return bool(cfg.VAPID_PUBLIC_KEY and cfg.VAPID_PRIVATE_KEY)


def _webpush(sub, payload):
    import json
    from pywebpush import webpush
    webpush(subscription_info=sub, data=json.dumps(payload), vapid_private_key=cfg.VAPID_PRIVATE_KEY,
            vapid_claims={"sub": cfg.VAPID_SUBJECT}, ttl=86400)


async def send_push(reg, title, body, url):
    """Notifica o visitante no celular (se ele autorizou). Registra em notifications."""
    sub = reg.get("push_sub")
    if not sub or not push_enabled():
        return False
    rec = {"id": new_id(), "channel": "push", "to": "", "subject": title, "kind": "push", "ref": reg["id"],
           "at": now_iso(), "ok": False, "error": ""}
    try:
        await asyncio.to_thread(_webpush, sub, {"title": title, "body": body, "url": url, "tag": reg["id"]})
        rec["ok"] = True
    except Exception as e:  # noqa: BLE001
        rec["error"] = str(e)[:200]
        if "410" in rec["error"] or "404" in rec["error"]:
            await db.self_registrations.update_one({"id": reg["id"]}, {"$unset": {"push_sub": ""}})
    await db.notifications.insert_one(rec)
    return rec["ok"]



# ---------------- retenção (LGPD) ----------------
async def _last_visit_end(visitor_id):
    v = await db.visits.find_one({"visitor_id": visitor_id}, {"_id": 0, "end_at": 1, "ended_at": 1, "status": 1},
                                 sort=[("end_at", -1)])
    if not v:
        return None, False
    active = v.get("status") in ("agendado", "presente")
    return (v.get("ended_at") or v.get("end_at")), active


async def retention_tick(now=None):
    """Expira solicitações pendentes, apaga selfies antigas e faces de visitantes após o prazo."""
    from visits_core import parse_dt
    now = now or utcnow()
    s = await get_settings()
    out = {"expired": 0, "selfreg_purged": 0, "faces_purged": 0}

    # 0) aprovação interrompida (queda do serviço no meio do processo) volta para a fila
    await db.self_registrations.update_many({"status": "processando", "locked_at": {"$lte": now - timedelta(minutes=10)}},
                                            {"$set": {"status": "pendente"}})

    # 1) solicitações pendentes vencidas
    async for r in db.self_registrations.find({"status": "pendente", "expires_at": {"$lte": now}}, {"_id": 0}):
        res = await db.self_registrations.update_one({"id": r["id"], "status": "pendente"},
                                                     {"$set": {"status": "expirado", "decided_at": now_iso(),
                                                               "decided_by": "sistema"}})
        if res.modified_count:
            out["expired"] += 1
            if r.get("email"):
                await send_email(r["email"], "Sua solicitação de visita expirou",
                                 [f"Olá, {escape(r.get('name', ''))}.",
                                  f"Sua solicitação de visita a {escape(r.get('host_company_name', ''))} não foi "
                                  f"aprovada a tempo e expirou. Procure a recepção ou faça uma nova solicitação."],
                                 kind="expirado", ref=r["id"])

    # 2) selfies de solicitações decididas há mais de 7 dias (o cadastro do visitante fica em visitors)
    r = await db.self_registrations.update_many(
        {"status": {"$in": list(FINAL)}, "photo": {"$nin": ["", None]}, "decided_at": {"$lte": (now - timedelta(days=7)).isoformat()}},
        {"$set": {"photo": "", "photo_thumb": "", "photo_purged_at": now_iso()}})
    out["selfreg_purged"] = r.modified_count

    # 3) faces de visitantes: comum após N dias do fim da última visita; recorrente após M meses sem visitas
    days = int(s.get("visitor_retention_days") or 0)
    months = int(s.get("recurring_months") or 12)
    if days > 0:
        async for v in db.visitors.find({**ND, "photo": {"$nin": ["", None]}, "blacklist": {"$ne": True}},
                                        {"_id": 0, "id": 1, "remember": 1, "created_at": 1}):
            last, active = await _last_visit_end(v["id"])
            if active:
                continue
            ref = last or v.get("created_at")
            try:
                ref_dt = parse_dt(ref)
            except (TypeError, ValueError):
                continue
            limit = timedelta(days=months * 30) if v.get("remember") else timedelta(days=days)
            if now - ref_dt >= limit:
                await db.visitors.update_one({"id": v["id"]}, {"$set": {"photo": "", "photo_thumb": "", "remember": False,
                                                                       "photo_purged_at": now_iso()}})
                out["faces_purged"] += 1
    if any(out.values()):
        logger.info(f"retenção: {out}")
    return out


async def retention_loop():
    await asyncio.sleep(30)
    while True:
        try:
            await retention_tick()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"retention_loop: {e}")
        await asyncio.sleep(3600)

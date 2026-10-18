"""Autocadastro de visitantes.

Rotas públicas (sem login, com limite de uso):  /api/public/selfreg/...
Rotas internas (portaria, gestor, admin):        /api/selfreg/...
Nada é liberado no equipamento sem aprovação humana (anfitrião, portaria ou quem enviou o convite).
"""
import re
from datetime import datetime, timedelta, timezone
from html import escape

from fastapi import APIRouter, Depends, HTTPException, Request

import app_config as cfg
from database import db
from models import new_id, now_iso
from photo_quality import check_photo, make_thumb
from registry_common import ND
from scope import scope_filter, find_scoped
from security import get_current_user, require_role
from util import log_audit, client_ip
from visits_core import (get_settings as visit_settings, validate_doc, doc_key, parse_dt, compute_end, type_hours,
                         norm_plate, TZ)
from routers.visits import register_visit
from selfreg_core import (get_settings, otp_active, new_token, token_hash, new_code, new_otp, same, valid_email, link,
                          mask_doc, mask_email, hit, captcha_ok, send_email, send_push, push_enabled, utcnow,
                          TURNSTILE_SITE_KEY, DEFAULTS)

public = APIRouter(prefix="/public/selfreg", tags=["selfreg-public"])
router = APIRouter(prefix="/selfreg", tags=["selfreg"])
WRITE = ("admin", "operator", "reception", "company_manager")
SELF_DOCS = ("cpf",)
MAX_PHOTO = 3_000_000
GENERIC_LIMIT = "Muitas tentativas. Aguarde alguns minutos e tente novamente."


def _s(v, n=200):
    """Só texto (bloqueia objetos/operadores Mongo vindos do corpo da requisição)."""
    return v[:n] if isinstance(v, str) else ""


def _err(fields, msg="Verifique os campos destacados"):
    raise HTTPException(status_code=422, detail={"msg": msg, "fields": fields})


def _iso(dt):
    if isinstance(dt, datetime):
        return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).isoformat()
    return dt or ""


def _fmt(iso):
    try:
        return parse_dt(iso).astimezone(TZ).strftime("%d/%m/%Y %H:%M")
    except (TypeError, ValueError):
        return ""


async def _limit(key, n, window):
    if not await hit(key, n, window):
        raise HTTPException(status_code=429, detail=GENERIC_LIMIT)


# ======================================================================
# Contexto (link público da empresa ou convite individual)
# ======================================================================
async def _enabled_company(query):
    comp = await db.companies.find_one({**ND, **query, "selfreg_enabled": True, "enabled": {"$ne": False}}, {"_id": 0})
    if not comp:
        return None, None
    vt = await db.visit_types.find_one({**ND, "id": comp.get("selfreg_visit_type_id"), "active": True}, {"_id": 0})
    return (comp, vt) if vt else (None, None)


async def site_companies():
    """Empresas com autocadastro ativo e tipo de visita válido (lista do QR único do local)."""
    out, vs = [], await visit_settings()
    async for c in db.companies.find({**ND, "selfreg_enabled": True, "enabled": {"$ne": False}},
                                     {"_id": 0, "id": 1, "name": 1, "selfreg_visit_type_id": 1}).sort("name", 1):
        vt = await db.visit_types.find_one({**ND, "id": c.get("selfreg_visit_type_id"), "active": True}, {"_id": 0})
        if vt:
            out.append({"id": c["id"], "name": c["name"], "duration_hours": type_hours(vt, vs)})
    return out


async def _company_ctx(code, company_id=""):
    s = await get_settings()
    if not s.get("enabled") or not code or not re.fullmatch(r"[a-z0-9]{4,16}", code):
        return None
    # QR único do local: o visitante escolhe a empresa durante o cadastro
    if s.get("site_enabled") and s.get("site_code") and same(code, s["site_code"]):
        comp, vt = (await _enabled_company({"id": company_id})) if company_id else (None, None)
        return {"settings": s, "company": comp, "vtype": vt, "invite": None, "site": True}
    comp, vt = await _enabled_company({"selfreg_code": code})
    if not comp:
        return None
    return {"settings": s, "company": comp, "vtype": vt, "invite": None, "site": False}


async def _invite_ctx(token):
    s = await get_settings()
    if not s.get("enabled") or not token or len(token) > 100:
        return None
    inv = await db.selfreg_invites.find_one({"token_hash": token_hash(token), "status": "ativo",
                                             "expires_at": {"$gt": utcnow()}}, {"_id": 0})
    if not inv:
        return None
    comp = await db.companies.find_one({**ND, "id": inv["host_company_id"]}, {"_id": 0})
    vt = await db.visit_types.find_one({**ND, "id": inv["visit_type_id"]}, {"_id": 0})
    if not comp or not vt:
        return None
    return {"settings": s, "company": comp, "vtype": vt, "invite": inv}


async def _ctx(body_or_q):
    ctx = None
    if _s(body_or_q.get("invite")):
        ctx = await _invite_ctx(_s(body_or_q["invite"]))
    elif _s(body_or_q.get("code")):
        ctx = await _company_ctx(_s(body_or_q["code"]).lower(), _s(body_or_q.get("company_id")))
    if not ctx:
        raise HTTPException(status_code=404, detail="Link inválido, expirado ou desativado. Procure a recepção.")
    return ctx


def _need_company(ctx):
    if not ctx["company"]:
        _err({"company_id": "Escolha a empresa que você vai visitar"})


def _ctx_key(ctx):
    if ctx["invite"]:
        return f"inv:{ctx['invite']['id']}"
    return "site" if ctx.get("site") else f"co:{ctx['company']['id']}"


# ======================================================================
# Rotas públicas
# ======================================================================
@public.get("/info")
async def info(request: Request, code: str = "", invite: str = ""):
    await _limit(f"info:{client_ip(request)}", 60, 600)
    ctx = await _ctx({"code": code, "invite": invite})
    s, inv = ctx["settings"], ctx["invite"]
    out = {"site": cfg.CLIENTE_NOME, "lgpd_text": s["lgpd_text"], "otp": otp_active(s), "captcha_site_key": TURNSTILE_SITE_KEY,
           "max_days_ahead": s["max_days_ahead"], "doc_types": list(SELF_DOCS), "invite": None, "companies": None,
           "company": "", "visit_type": "", "duration_hours": 0}
    if ctx.get("site"):
        out["companies"] = await site_companies()
        if not out["companies"]:
            raise HTTPException(status_code=404, detail="Autocadastro indisponível no momento. Procure a recepção.")
    else:
        out.update({"company": ctx["company"]["name"], "visit_type": ctx["vtype"]["name"],
                    "duration_hours": type_hours(ctx["vtype"], await visit_settings())})
    if inv:
        out["invite"] = {"host_name": inv["host_name"], "start_at": inv["start_at"], "end_at": inv["end_at"],
                         "guest_name": inv.get("guest_name", ""), "guest_email": inv.get("guest_email", "")}
    return out


@public.post("/lookup")
async def lookup(body: dict, request: Request):
    """CPF já cadastrado? Responde só se encontrou e o início do primeiro nome mascarado — nenhum outro dado."""
    await _limit(f"lookup:{client_ip(request)}", 15, 600)
    await _ctx(body)
    num, err = validate_doc("cpf", _s(body.get("doc_number"), 20), await visit_settings())
    if err:
        _err({"doc_number": err}, err)
    v = await db.visitors.find_one({**ND, "doc_type": "cpf", "doc_key": doc_key("cpf", num)}, {"_id": 0, "name": 1})
    if not v or not v.get("name"):
        return {"found": False}
    first = v["name"].split(" ")[0]
    return {"found": True, "greeting": f"{first[:3]}{'*' * max(len(first) - 3, 2)}"}


@public.post("/hosts")
async def hosts(body: dict, request: Request):
    """Busca do anfitrião pelo nome: no máx. 3 resultados, nunca lista aberta."""
    await _limit(f"hosts:{client_ip(request)}", 40, 600)
    ctx = await _ctx(body)
    if ctx["invite"]:
        return []
    _need_company(ctx)
    q = _s(body.get("q"), 60).strip()
    if len(q) < 3:
        return []
    rx = {"$regex": re.escape(q), "$options": "i"}
    items = await db.people.find({**ND, "company_id": ctx["company"]["id"], "status": "ativo",
                                  "can_authorize_visits": {"$ne": False}, "name": rx},
                                 {"_id": 0, "id": 1, "name": 1}).sort("name", 1).limit(3).to_list(3)
    return items


@public.post("/otp")
async def send_otp(body: dict, request: Request):
    ip = client_ip(request)
    ctx = await _ctx(body)
    if not otp_active(ctx["settings"]):
        raise HTTPException(status_code=400, detail="Confirmação por código não está ativa")
    email = _s(body.get("email")).strip().lower()
    if not valid_email(email):
        _err({"email": "Informe um e-mail válido"})
    if not await captcha_ok(_s(body.get("captcha"), 4000), ip):
        raise HTTPException(status_code=400, detail="Confirme que você não é um robô")
    await _limit(f"otp-ip:{ip}", 8, 900)
    await _limit(f"otp-mail:{email}", 4, 900)
    code = new_otp()
    oid = new_id()
    await db.selfreg_otps.insert_one({"id": oid, "email": email, "code_hash": token_hash(f"{oid}:{code}"),
                                      "attempts": 0, "ctx": _ctx_key(ctx), "ip": ip,
                                      "expires_at": utcnow() + timedelta(minutes=10), "created_at": now_iso()})
    ok = await send_email(email, f"Código de confirmação: {code}",
                          [f"Seu código para o cadastro de visitante em <b>{escape(cfg.CLIENTE_NOME)}</b> é:",
                           f"<span style='font-size:28px;letter-spacing:6px;font-weight:bold'>{code}</span>",
                           "Ele vale por 10 minutos. Se você não pediu, ignore este e-mail."],
                          kind="otp", ref=oid)
    if not ok:
        raise HTTPException(status_code=503, detail="Não foi possível enviar o e-mail agora. Tente novamente ou procure a recepção.")
    return {"otp_id": oid, "email": mask_email(email)}


@public.post("/verify")
async def verify_otp(body: dict, request: Request):
    await _limit(f"verify:{client_ip(request)}", 20, 900)
    ctx = await _ctx(body)
    otp = await db.selfreg_otps.find_one({"id": _s(body.get("otp_id")), "ctx": _ctx_key(ctx),
                                          "expires_at": {"$gt": utcnow()}}, {"_id": 0})
    if not otp or otp.get("attempts", 0) >= 5 or otp.get("verified"):
        raise HTTPException(status_code=400, detail="Código expirado. Peça um novo código.")
    code = re.sub(r"\D", "", _s(body.get("otp")))
    if not same(token_hash(f"{otp['id']}:{code}"), otp["code_hash"]):
        await db.selfreg_otps.update_one({"id": otp["id"]}, {"$inc": {"attempts": 1}})
        _err({"otp": "Código incorreto"})
    await db.selfreg_otps.update_one({"id": otp["id"]}, {"$set": {"verified": True}})
    vtoken = new_token()
    await db.selfreg_verifications.insert_one({"token_hash": token_hash(vtoken), "email": otp["email"],
                                               "ctx": otp["ctx"], "used": False,
                                               "expires_at": utcnow() + timedelta(minutes=30)})
    out = {"verify_token": vtoken, "recurring": None}
    v = await db.visitors.find_one({**ND, "email": otp["email"], "remember": True, "photo": {"$nin": ["", None]},
                                    "blacklist": {"$ne": True}},
                                   {"_id": 0, "name": 1, "doc_type": 1, "doc_number": 1, "origin_company": 1, "plate": 1,
                                    "phone": 1, "photo_thumb": 1})
    if v:
        out["recurring"] = {"name": v.get("name", ""), "doc_type": v.get("doc_type", ""),
                            "doc_number": mask_doc(v.get("doc_number")), "visitor_company": v.get("origin_company", ""),
                            "plate": v.get("plate", ""), "phone": v.get("phone", ""), "photo_thumb": v.get("photo_thumb", "")}
    return out


@public.post("/submit")
async def submit(body: dict, request: Request):
    ip = client_ip(request)
    photo_in = body.get("photo") if isinstance(body.get("photo"), str) else ""
    body = {k: (v if isinstance(v, bool) else _s(v, 4000)) for k, v in body.items() if k != "photo"}
    ctx = await _ctx(body)
    _need_company(ctx)
    s, comp, vt, inv = ctx["settings"], ctx["company"], ctx["vtype"], ctx["invite"]
    await _limit(f"submit:{ip}", 10, 3600)
    errs = {}
    if body.get("consent") is not True:
        errs["consent"] = "É preciso aceitar o termo de uso dos dados"

    # identidade do e-mail
    email = (body.get("email") or "").strip().lower()
    verification = None
    if otp_active(s):
        verification = await db.selfreg_verifications.find_one(
            {"token_hash": token_hash(body.get("verify_token") or "-"), "ctx": _ctx_key(ctx), "used": False,
             "expires_at": {"$gt": utcnow()}}, {"_id": 0})
        if not verification:
            raise HTTPException(status_code=400, detail="Confirmação do e-mail expirada. Recomece o cadastro.")
        email = verification["email"]
    else:
        if not await captcha_ok(body.get("captcha", ""), ip):
            raise HTTPException(status_code=400, detail="Confirme que você não é um robô")
        if email and not valid_email(email):
            errs["email"] = "E-mail inválido"
    if email:
        await _limit(f"submit-mail:{email}", 6, 86400)

    # visitante recorrente (só com e-mail confirmado)
    saved = None
    if body.get("use_saved") and verification:
        saved = await db.visitors.find_one({**ND, "email": email, "remember": True, "photo": {"$nin": ["", None]},
                                            "blacklist": {"$ne": True}}, {"_id": 0})
    if saved:
        name, doc_type, doc_number = saved["name"], saved.get("doc_type"), saved.get("doc_number")
        vcomp = (body.get("visitor_company") or saved.get("origin_company") or "").strip()[:120]
    else:
        doc_type = body.get("doc_type") or "cpf"
        doc_number = ""
        if doc_type not in SELF_DOCS:
            errs["doc_type"] = "Informe o CPF"
        else:
            doc_number, derr = validate_doc(doc_type, body.get("doc_number"), await visit_settings())
            if derr:
                errs["doc_number"] = derr
        known = None if not doc_number else await db.visitors.find_one(
            {**ND, "doc_type": doc_type, "doc_key": doc_key(doc_type, doc_number)},
            {"_id": 0, "name": 1, "origin_company": 1, "phone": 1, "plate": 1})
        name = re.sub(r"\s+", " ", _s(body.get("name"), 120)).strip() or (known or {}).get("name", "")
        if len(name) < 5 or " " not in name:
            errs["name"] = "Informe o nome completo"
        vcomp = _s(body.get("visitor_company"), 120).strip() or (known or {}).get("origin_company", "")
        if known:
            body = {**body, "phone": _s(body.get("phone"), 30) or known.get("phone", ""),
                    "plate": _s(body.get("plate"), 10) or known.get("plate", "")}
    visit_reason = _s(body.get("visit_reason"), 200).strip()
    phone = re.sub(r"[^\d+() -]", "", body.get("phone") or "")[:20]
    plate, perr = norm_plate(body.get("plate"))
    if perr:
        errs["plate"] = perr

    # anfitrião e horário
    if inv:
        host = await db.people.find_one({**ND, "id": inv["host_person_id"]}, {"_id": 0, "id": 1, "name": 1, "email": 1})
        start_iso, end_iso = inv["start_at"], inv["end_at"]
    else:
        host = await db.people.find_one({**ND, "id": body.get("host_person_id"), "company_id": comp["id"], "status": "ativo",
                                         "can_authorize_visits": {"$ne": False}}, {"_id": 0, "id": 1, "name": 1, "email": 1})
        if not host:
            errs["host_person_id"] = "Escolha quem você vai visitar"
        now = datetime.now(timezone.utc)
        start = now  # a solicitação vale a partir do envio; o anfitrião decide quando aprovar
        start_iso = start.astimezone(timezone.utc).isoformat()
        end_iso = compute_end(start_iso, type_hours(vt, await visit_settings())).astimezone(timezone.utc).isoformat()

    # selfie
    photo = "" if saved else photo_in
    pcheck = None
    if not saved:
        if not photo.startswith("data:image/") or len(photo) > MAX_PHOTO:
            errs["photo"] = "Tire a foto do rosto"
        else:
            pcheck = check_photo(photo)
            if not pcheck.get("ok"):
                errs["photo"] = "; ".join(pcheck.get("issues") or ["Foto fora do padrão"])
    if errs:
        _err(errs)

    key = doc_key(doc_type, doc_number)
    existing = await db.visitors.find_one({**ND, "doc_type": doc_type, "doc_key": key}, {"_id": 0, "id": 1, "blacklist": 1})
    dup = await db.self_registrations.find_one({"status": "pendente", "doc_key": key, "doc_type": doc_type,
                                                "host_company_id": comp["id"]}, {"_id": 0, "id": 1})
    if dup:
        raise HTTPException(status_code=409, detail="Você já tem uma solicitação aguardando aprovação para esta empresa.")

    status_token, decision_token = new_token(), new_token()
    reg = {"id": new_id(), "status": "pendente", "source": "convite" if inv else "link",
           "invite_id": inv["id"] if inv else None, "status_token_hash": token_hash(status_token),
           "decision_token_hash": token_hash(decision_token),
           "host_company_id": comp["id"], "host_company_name": comp["name"],
           "host_person_id": host["id"], "host_name": host["name"], "host_email": (host.get("email") or "").strip().lower(),
           "visit_type_id": vt["id"], "visit_type_name": vt["name"], "start_at": start_iso, "end_at": end_iso,
           "name": name, "doc_type": doc_type, "doc_number": doc_number, "doc_key": key, "visitor_company": vcomp,
           "email": email, "email_verified": bool(verification), "phone": phone, "plate": plate, "visit_reason": visit_reason,
           "photo": photo, "photo_thumb": make_thumb(photo) if photo else (saved or {}).get("photo_thumb", ""),
           "photo_metrics": (pcheck or {}).get("metrics", {}), "saved_visitor_id": (saved or {}).get("id"),
           "remember": bool(body.get("remember")) and bool(verification),
           "blacklist": bool((existing or {}).get("blacklist")), "visitor_id": (existing or {}).get("id"),
           "consent_at": now_iso(), "lgpd_text": s["lgpd_text"], "ip": ip,
           "created_at": now_iso(), "expires_at": utcnow() + timedelta(hours=int(s["approval_hours"]))}
    if inv:
        claimed = await db.selfreg_invites.update_one({"id": inv["id"], "status": "ativo"},
                                                      {"$set": {"status": "usado", "used_at": now_iso(), "selfreg_id": reg["id"]}})
        if not claimed.modified_count:
            raise HTTPException(status_code=409, detail="Este convite já foi utilizado.")
    if verification:
        claimed = await db.selfreg_verifications.update_one({"token_hash": verification["token_hash"], "used": False},
                                                            {"$set": {"used": True}})
        if not claimed.modified_count:
            raise HTTPException(status_code=400, detail="Confirmação do e-mail já utilizada. Recomece o cadastro.")
    await db.self_registrations.insert_one(dict(reg))
    await log_audit(None, "autocadastro", "self_registration", reg["id"],
                    f"{name} → {host['name']} ({comp['name']}) via {reg['source']}", ip)

    # convite com liberação automática (quem convidou já autorizou) — nunca para lista negra
    if inv and inv.get("auto_approve") and not reg["blacklist"]:
        actor = {"email": inv.get("created_by", ""), "name": inv.get("created_by_name") or "Convite", "role": "convite"}
        try:
            await _approve(reg, actor, "convite", {}, ip)
        except HTTPException:
            await _notify_pending(reg, decision_token, s["approval_hours"])
    else:
        await _notify_pending(reg, decision_token, s["approval_hours"])
    cur = await db.self_registrations.find_one({"id": reg["id"]}, {"_id": 0, "status": 1})
    return {"status_token": status_token, "status": cur["status"]}


@public.get("/status/{token}")
async def status(token: str, request: Request):
    await _limit(f"status:{client_ip(request)}:{token_hash(token)[:12]}", 240, 600)
    r = await db.self_registrations.find_one({"status_token_hash": token_hash(token)}, {"_id": 0})
    if not r:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada")
    return {"status": "pendente" if r["status"] == "processando" else r["status"], "name": r["name"].split(" ")[0],
            "company": r["host_company_name"], "host_name": r["host_name"], "start_at": r["start_at"], "end_at": r["end_at"]}


@public.get("/push-key")
async def push_key():
    return {"enabled": push_enabled(), "key": cfg.VAPID_PUBLIC_KEY if push_enabled() else ""}


@public.post("/push/{token}")
async def push_subscribe(token: str, body: dict, request: Request):
    """Visitante autoriza notificação no celular. Só texto: endpoint https + chaves."""
    await _limit(f"push:{client_ip(request)}", 20, 600)
    if not push_enabled():
        raise HTTPException(status_code=400, detail="Notificações desativadas")
    keys = body.get("keys") if isinstance(body.get("keys"), dict) else {}
    sub = {"endpoint": _s(body.get("endpoint"), 1000), "keys": {"p256dh": _s(keys.get("p256dh"), 200), "auth": _s(keys.get("auth"), 100)}}
    if not sub["endpoint"].startswith("https://") or not sub["keys"]["p256dh"] or not sub["keys"]["auth"]:
        raise HTTPException(status_code=400, detail="Inscrição inválida")
    res = await db.self_registrations.update_one({"status_token_hash": token_hash(token)}, {"$set": {"push_sub": sub}})
    if not res.matched_count:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada")
    return {"ok": True}


@public.get("/decision/{token}")
async def decision_view(token: str, request: Request):
    await _limit(f"decision:{client_ip(request)}", 60, 600)
    r = await db.self_registrations.find_one({"decision_token_hash": token_hash(token)}, {"_id": 0})
    if not r:
        raise HTTPException(status_code=404, detail="Link inválido")
    base = {"status": r["status"], "name": r["name"], "company": r["host_company_name"], "host_name": r["host_name"],
            "start_at": r["start_at"], "end_at": r["end_at"], "decided_via": r.get("decided_via", ""),
            "decided_by_name": r.get("decided_by_name", "")}
    if r["status"] != "pendente":
        return base
    return {**base, "visitor_company": r.get("visitor_company", ""), "doc_type": r.get("doc_type"), "visit_reason": r.get("visit_reason", ""),
            "doc_number": mask_doc(r.get("doc_number")), "plate": r.get("plate", ""), "visit_type": r["visit_type_name"],
            "photo": r.get("photo") or r.get("photo_thumb", ""), "blacklist": r.get("blacklist", False)}


@public.post("/decision/{token}")
async def decision_act(token: str, body: dict, request: Request):
    ip = client_ip(request)
    await _limit(f"decision:{ip}", 60, 600)
    r = await db.self_registrations.find_one({"decision_token_hash": token_hash(token)}, {"_id": 0})
    if not r:
        raise HTTPException(status_code=404, detail="Link inválido")
    if r["status"] != "pendente":
        raise HTTPException(status_code=409, detail="Esta solicitação já foi respondida.")
    actor = {"email": f"anfitriao:{r.get('host_email') or r['host_person_id']}", "name": r["host_name"], "role": "anfitriao"}
    if body.get("action") == "approve":
        if r.get("blacklist"):
            raise HTTPException(status_code=409, detail="Esta solicitação precisa ser analisada pela portaria.")
        await _approve(r, actor, "anfitriao", {}, ip)
    elif body.get("action") == "reject":
        await _reject(r, actor, "anfitriao", _s(body.get("reason"), 300), ip)
    else:
        raise HTTPException(status_code=400, detail="Ação inválida")
    return await decision_view(token, request)


# ======================================================================
# Aprovação / recusa (usadas pelo anfitrião, portaria e convite)
# ======================================================================
async def _notify_pending(reg, decision_token, hours=24):
    if reg.get("host_email") and valid_email(reg["host_email"]):
        await send_email(reg["host_email"], f"Visita aguardando sua aprovação: {reg['name']}",
                         [f"Olá, {escape(reg['host_name'])}.",
                          f"<b>{escape(reg['name'])}</b>{' (' + escape(reg['visitor_company']) + ')' if reg.get('visitor_company') else ''} "
                          f"solicitou uma visita a você em {escape(reg['host_company_name'])}.",
                          f"Horário: {_fmt(reg['start_at'])} até {_fmt(reg['end_at'])}.",
                          f"Abra o link para ver a foto e aprovar ou recusar. Ele vale por {hours} horas e só pode ser usado uma vez. "
                          "A portaria também pode responder; vale a primeira resposta."],
                         button=("Ver e responder", link(f"/aprovar/{decision_token}")), kind="aguardando", ref=reg["id"])


async def _lock(reg_id):
    r = await db.self_registrations.find_one_and_update({"id": reg_id, "status": "pendente"},
                                                        {"$set": {"status": "processando", "locked_at": utcnow()}})
    if not r:
        raise HTTPException(status_code=409, detail="Esta solicitação já foi respondida.")
    return r


async def _approve(reg, actor, via, adj, ip):
    await _lock(reg["id"])
    start_at, end_at = reg["start_at"], adj.get("end_at") or reg["end_at"]
    now = datetime.now(timezone.utc)
    if reg["source"] != "convite" and parse_dt(start_at) < now:
        # link público: a visita começa na aprovação e mantém a duração do tipo
        if not adj.get("end_at"):
            end_at = (now + (parse_dt(reg["end_at"]) - parse_dt(start_at))).astimezone(timezone.utc).isoformat()
        start_at = now.isoformat()
    body = {"visit_type_id": adj.get("visit_type_id") or reg["visit_type_id"], "start_at": start_at, "end_at": end_at,
            "end_at_manual": bool(adj.get("end_at")), "host_company_id": reg["host_company_id"],
            "host_person_id": reg["host_person_id"], "name": reg["name"], "doc_type": reg["doc_type"],
            "doc_number": reg["doc_number"], "visitor_company": reg.get("visitor_company", ""), "plate": reg.get("plate", ""),
            "identifier": {"type": "facial"}, "photo": reg.get("photo", ""), "visit_reason": reg.get("visit_reason", ""),
            "notes": f"Autocadastro ({reg['source']}) aprovado por {via}",
            "blacklist_justification": adj.get("blacklist_justification", "")}
    try:
        res = await register_visit(body, actor, ip, origin=f"autocadastro:{reg['source']}")
    except Exception:
        await db.self_registrations.update_one({"id": reg["id"], "status": "processando"}, {"$set": {"status": "pendente"}})
        raise
    visit, visitor = res["visit"], res["visitor"]
    vset = {"consent_at": reg["consent_at"], "selfreg_last": reg["id"]}
    if reg.get("email"):
        vset["email"] = reg["email"]
    if reg.get("phone"):
        vset["phone"] = reg["phone"]
    if reg.get("remember"):
        vset["remember"] = True
    await db.visitors.update_one({"id": visitor["id"]}, {"$set": vset})
    await db.self_registrations.update_one({"id": reg["id"]}, {"$set": {
        "status": "aprovado", "visit_id": visit["id"], "visitor_id": visitor["id"], "decided_at": now_iso(),
        "decided_via": via, "decided_by": actor.get("email"), "decided_by_name": actor.get("name", ""),
        "start_at": visit["start_at"], "end_at": visit["end_at"], "photo": "", "sync_ok": sum(1 for x in res["sync"] if x["status"] == "ok"),
        "sync_total": len(res["sync"])}})
    await log_audit(actor, "autocadastro:aprovar", "self_registration", reg["id"], f"{reg['name']} via {via}", ip)
    if reg.get("email"):
        await send_email(reg["email"], f"Visita aprovada — {reg['host_company_name']}",
                         [f"Olá, {escape(reg['name'].split(' ')[0])}.",
                          f"Sua visita a <b>{escape(reg['host_name'])}</b> ({escape(reg['host_company_name'])}) foi aprovada.",
                          f"Válida de {_fmt(visit['start_at'])} até {_fmt(visit['end_at'])}. "
                          "Na chegada, olhe para o leitor facial. Se não liberar, procure a recepção."],
                         kind="aprovado", ref=reg["id"])
    await send_push(reg, "Visita aprovada", f"{reg['host_company_name']}: válida de {_fmt(visit['start_at'])} até {_fmt(visit['end_at'])}. "
                    "Na chegada, olhe para o leitor facial.", "/")
    if via != "anfitriao" and reg.get("host_email") and valid_email(reg["host_email"]):
        await send_email(reg["host_email"], f"Visita de {reg['name']} aprovada",
                         [f"A visita de <b>{escape(reg['name'])}</b> foi aprovada por {escape(actor.get('name') or via)}.",
                          f"Horário: {_fmt(visit['start_at'])} até {_fmt(visit['end_at'])}."],
                         kind="aviso-anfitriao", ref=reg["id"])
    return res


async def _reject(reg, actor, via, reason, ip):
    await _lock(reg["id"])
    reason = (reason or "").strip()[:300]
    await db.self_registrations.update_one({"id": reg["id"]}, {"$set": {
        "status": "recusado", "decided_at": now_iso(), "decided_via": via, "decided_by": actor.get("email"),
        "decided_by_name": actor.get("name", ""), "reason": reason}})
    await log_audit(actor, "autocadastro:recusar", "self_registration", reg["id"], f"{reg['name']} via {via}: {reason}", ip)
    if reg.get("email"):
        await send_email(reg["email"], f"Visita não aprovada — {reg['host_company_name']}",
                         [f"Olá, {escape(reg['name'].split(' ')[0])}.",
                          f"Sua solicitação de visita a {escape(reg['host_company_name'])} não foi aprovada."
                          + (f" Motivo: {escape(reason)}" if reason else ""),
                          "Em caso de dúvida, procure a recepção."], kind="recusado", ref=reg["id"])
    await send_push(reg, "Visita não aprovada", f"{reg['host_company_name']}" + (f": {reason}" if reason else ". Procure a recepção."),
                    "/")
    if via != "anfitriao" and reg.get("host_email") and valid_email(reg["host_email"]):
        await send_email(reg["host_email"], f"Visita de {reg['name']} recusada",
                         [f"A visita de <b>{escape(reg['name'])}</b> foi recusada por {escape(actor.get('name') or via)}."
                          + (f" Motivo: {escape(reason)}" if reason else "")], kind="aviso-anfitriao", ref=reg["id"])


# ======================================================================
# Rotas internas
# ======================================================================
LIST_FIELDS = {"_id": 0, "photo": 0, "status_token_hash": 0, "decision_token_hash": 0, "lgpd_text": 0, "ip": 0}


@router.get("/requests")
async def list_requests(status: str = "pendente", user: dict = Depends(require_role(*WRITE))):
    q = {**(await scope_filter(user, "visits"))}
    if status == "pendente":
        q["status"] = {"$in": ["pendente", "processando"]}
    elif status in ("aprovado", "recusado", "expirado"):
        q["status"] = status
    items = await db.self_registrations.find(q, LIST_FIELDS).sort("created_at", -1).limit(300).to_list(300)
    for r in items:
        r["expires_at"] = _iso(r.get("expires_at"))
    return items


@router.get("/summary")
async def summary(user: dict = Depends(require_role(*WRITE))):
    q = {**(await scope_filter(user, "visits")), "status": "pendente"}
    return {"pending": await db.self_registrations.count_documents(q)}


async def _scoped_reg(user, rid):
    r = await db.self_registrations.find_one({"$and": [{"id": rid}, await scope_filter(user, "visits")]},
                                             {"_id": 0, "status_token_hash": 0, "decision_token_hash": 0, "ip": 0})
    if not r:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada")
    r["expires_at"] = _iso(r.get("expires_at"))
    return r


@router.get("/requests/{rid}")
async def get_request(rid: str, user: dict = Depends(require_role(*WRITE))):
    return await _scoped_reg(user, rid)


@router.put("/requests/{rid}")
async def edit_request(rid: str, body: dict, request: Request, user: dict = Depends(require_role(*WRITE))):
    """Portaria corrige os dados antes de liberar (só pendentes). Lista negra nunca é removida aqui."""
    r = await _scoped_reg(user, rid)
    if r["status"] != "pendente":
        raise HTTPException(status_code=409, detail="Esta solicitação já foi respondida.")
    upd, errs = {}, {}
    for k, n in (("name", 120), ("visitor_company", 120), ("plate", 10), ("phone", 30), ("email", 160), ("visit_reason", 200)):
        if k in body:
            upd[k] = _s(body.get(k), n).strip()
    if "name" in upd and len(upd["name"].split()) < 2:
        errs["name"] = "Informe nome e sobrenome"
    if upd.get("email"):
        upd["email"] = upd["email"].lower()
        if not valid_email(upd["email"]):
            errs["email"] = "E-mail inválido"
    if "plate" in upd:
        upd["plate"] = re.sub(r"[^A-Z0-9]", "", upd["plate"].upper())[:8]
    if "doc_type" in body or "doc_number" in body:
        dt = _s(body.get("doc_type") or r["doc_type"], 20)
        num, e = validate_doc(dt, _s(body.get("doc_number") or r["doc_number"], 40), await visit_settings())
        if dt not in SELF_DOCS or e:
            errs["doc_number"] = e or "Tipo de documento inválido"
        else:
            bl = await db.visitors.find_one({**ND, "doc_type": dt, "doc_key": doc_key(dt, num), "blacklist": True}, {"_id": 1})
            upd.update(doc_type=dt, doc_number=num, blacklist=bool(r.get("blacklist") or bl))
    if _s(body.get("visit_type_id")) and body.get("visit_type_id") != r.get("visit_type_id"):
        vt = await db.visit_types.find_one({"$and": [{**ND, "id": _s(body.get("visit_type_id")), "active": True},
                                                     await scope_filter(user, "visit_types")]}, {"_id": 0, "id": 1, "name": 1})
        if not vt:
            errs["visit_type_id"] = "Tipo de visita inválido"
        else:
            upd.update(visit_type_id=vt["id"], visit_type_name=vt["name"])
    if _s(body.get("end_at"), 40):
        try:
            end = parse_dt(_s(body.get("end_at"), 40))
            if end <= parse_dt(r["start_at"]):
                errs["end_at"] = "O fim deve ser depois do início"
            else:
                upd["end_at"] = end.astimezone(timezone.utc).isoformat()
        except ValueError:
            errs["end_at"] = "Data/hora inválida"
    if errs:
        raise HTTPException(status_code=422, detail={"message": "Verifique os campos", "errors": errs})
    if upd:
        res = await db.self_registrations.update_one({"id": rid, "status": "pendente"}, {"$set": upd})
        if not res.matched_count:
            raise HTTPException(status_code=409, detail="Esta solicitação já foi respondida.")
        await log_audit(user, "autocadastro:editar", "self_registration", rid, ", ".join(sorted(upd)), client_ip(request))
    return await _scoped_reg(user, rid)


@router.post("/requests/{rid}/approve")
async def approve(rid: str, body: dict, request: Request, user: dict = Depends(require_role(*WRITE))):
    r = await _scoped_reg(user, rid)
    if r["status"] != "pendente":
        raise HTTPException(status_code=409, detail="Esta solicitação já foi respondida.")
    res = await _approve(r, user, "portaria", {"end_at": _s(body.get("end_at"), 40), "visit_type_id": _s(body.get("visit_type_id")),
                                               "blacklist_justification": _s(body.get("blacklist_justification"), 300)},
                         client_ip(request))
    return {"ok": True, "visit_id": res["visit"]["id"], "sync": res["sync"]}


@router.post("/requests/{rid}/reject")
async def reject(rid: str, body: dict, request: Request, user: dict = Depends(require_role(*WRITE))):
    r = await _scoped_reg(user, rid)
    if r["status"] != "pendente":
        raise HTTPException(status_code=409, detail="Esta solicitação já foi respondida.")
    await _reject(r, user, "portaria", _s(body.get("reason"), 300), client_ip(request))
    return {"ok": True}


# ---------------- convites ----------------
@router.post("/invites")
async def create_invite(body: dict, request: Request, user: dict = Depends(require_role(*WRITE))):
    s = await get_settings()
    body = {k: (v if isinstance(v, bool) else _s(v, 300)) for k, v in body.items()}
    errs = {}
    comp = await db.companies.find_one({"$and": [{**ND, "id": body.get("host_company_id")}, await scope_filter(user, "companies")]},
                                       {"_id": 0, "id": 1, "name": 1})
    if not comp:
        errs["host_company_id"] = "Selecione a empresa visitada"
    host = await db.people.find_one({**ND, "id": body.get("host_person_id"), "status": "ativo",
                                     "can_authorize_visits": {"$ne": False}}, {"_id": 0, "id": 1, "name": 1, "company_id": 1})
    if not host or (comp and host.get("company_id") != comp["id"]):
        errs["host_person_id"] = "Selecione o anfitrião"
    vt = await db.visit_types.find_one({"$and": [{**ND, "id": body.get("visit_type_id"), "active": True},
                                                 await scope_filter(user, "visit_types")]}, {"_id": 0})
    if not vt:
        errs["visit_type_id"] = "Selecione o tipo da visita"
    now = datetime.now(timezone.utc)
    try:
        start = parse_dt(body["start_at"]) if body.get("start_at") else now
        if start < now - timedelta(hours=1) or start > now + timedelta(days=int(s["max_days_ahead"])):
            errs["start_at"] = f"Início entre agora e {s['max_days_ahead']} dias"
        end = parse_dt(body["end_at"]) if body.get("end_at") else compute_end(start.isoformat(), type_hours(vt, await visit_settings()))
        if end <= start:
            errs["end_at"] = "O fim deve ser depois do início"
    except ValueError:
        errs["start_at"] = "Data/hora inválida"
        start = end = now
    gemail = (body.get("guest_email") or "").strip().lower()
    if gemail and not valid_email(gemail):
        errs["guest_email"] = "E-mail inválido"
    if errs:
        _err(errs)
    token = new_token()
    exp = min(now + timedelta(hours=int(s["invite_hours"])), end)
    inv = {"id": new_id(), "token_hash": token_hash(token), "status": "ativo",
           "host_company_id": comp["id"], "host_company_name": comp["name"], "host_person_id": host["id"],
           "host_name": host["name"], "visit_type_id": vt["id"], "visit_type_name": vt["name"],
           "start_at": start.astimezone(timezone.utc).isoformat(), "end_at": end.astimezone(timezone.utc).isoformat(),
           "guest_name": (body.get("guest_name") or "").strip()[:120], "guest_email": gemail,
           "notes": (body.get("notes") or "").strip()[:300], "auto_approve": bool(body.get("auto_approve", True)),
           "created_by": user.get("email"), "created_by_name": user.get("name", ""), "created_at": now_iso(),
           "expires_at": exp}
    await db.selfreg_invites.insert_one(dict(inv))
    url = link(f"/convite/{token}")
    message = _invite_message(inv, comp, host, url)
    sent = False
    if gemail:
        sent = await send_email(gemail, f"Convite de visita — {comp['name']}",
                                [f"Olá{', ' + escape(inv['guest_name'].split(' ')[0]) if inv['guest_name'] else ''}.",
                                 f"<b>{escape(host['name'])}</b> ({escape(comp['name'])}) convidou você para uma visita em "
                                 f"{_fmt(inv['start_at'])} até {_fmt(inv['end_at'])} ({escape(vt['name'])}).",
                                 *([f"Observações: {escape(inv['notes'])}"] if inv["notes"] else []),
                                 "Faça seu cadastro pelo link abaixo (leva 1 minuto, com uma selfie). "
                                 "Assim você entra direto pelo leitor facial, sem fila na recepção."],
                                button=("Fazer meu cadastro", url), kind="convite", ref=inv["id"])
    await log_audit(user, "convite", "selfreg_invite", inv["id"], f"{inv['guest_name'] or gemail} → {host['name']}",
                    client_ip(request))
    inv.pop("_id", None)
    inv.pop("token_hash")
    inv["expires_at"] = _iso(exp)
    return {"invite": inv, "link": url, "email_sent": sent, "message": message}


def _invite_message(inv, comp, host, url):
    first = inv["guest_name"].split(" ")[0] if inv["guest_name"] else ""
    lines = [f"Olá{', ' + first if first else ''}! Você foi convidado(a) para uma visita.", "",
             f"Empresa: {comp['name']}", f"Anfitrião: {host['name']}",
             f"Data/hora: {_fmt(inv['start_at'])} até {_fmt(inv['end_at'])}",
             f"Tipo de visita: {inv['visit_type_name']}"]
    if inv["notes"]:
        lines.append(f"Observações: {inv['notes']}")
    lines += ["", "Faça seu cadastro antes de chegar (leva 1 minuto, com uma selfie) e entre direto pelo leitor facial:",
              url, "", f"O link é pessoal, vale uma única vez e expira em {_fmt(_iso(inv['expires_at']))}."]
    return "\n".join(lines)


@router.get("/invites")
async def list_invites(user: dict = Depends(require_role(*WRITE))):
    q = {**(await scope_filter(user, "visits"))}
    items = await db.selfreg_invites.find(q, {"_id": 0, "token_hash": 0}).sort("created_at", -1).limit(200).to_list(200)
    now = utcnow()
    for i in items:
        exp = i.get("expires_at")
        if isinstance(exp, datetime) and i["status"] == "ativo":
            if (exp if exp.tzinfo else exp.replace(tzinfo=timezone.utc)) <= now:
                i["status"] = "expirado"
        i["expires_at"] = _iso(exp)
    return items


@router.delete("/invites/{iid}")
async def revoke_invite(iid: str, request: Request, user: dict = Depends(require_role(*WRITE))):
    r = await db.selfreg_invites.update_one({"$and": [{"id": iid, "status": "ativo"}, await scope_filter(user, "visits")]},
                                            {"$set": {"status": "revogado", "revoked_at": now_iso()}})
    if not r.matched_count:
        raise HTTPException(status_code=404, detail="Convite não encontrado ou já utilizado")
    await log_audit(user, "convite:revogar", "selfreg_invite", iid, "", client_ip(request))
    return {"ok": True}


# ---------------- links públicos por empresa ----------------
@router.get("/companies")
async def list_companies(user: dict = Depends(require_role(*WRITE))):
    items = await db.companies.find({**ND, **(await scope_filter(user, "companies"))},
                                    {"_id": 0, "id": 1, "name": 1, "selfreg_enabled": 1, "selfreg_code": 1,
                                     "selfreg_visit_type_id": 1, "allowed_visit_type_ids": 1}).sort("name", 1).to_list(1000)
    for c in items:
        c["link"] = link(f"/v/{c['selfreg_code']}") if c.get("selfreg_code") else ""
    return items


@router.put("/companies/{cid}")
async def set_company(cid: str, body: dict, request: Request, user: dict = Depends(require_role("admin", "company_manager"))):
    comp = await find_scoped(user, "companies", cid, msg="Empresa não encontrada")
    upd = {"selfreg_enabled": bool(body.get("enabled"))}
    vtid = _s(body.get("visit_type_id")) or comp.get("selfreg_visit_type_id")
    if upd["selfreg_enabled"]:
        vt = await db.visit_types.find_one({"$and": [{**ND, "id": vtid, "active": True}, await scope_filter(user, "visit_types")]},
                                           {"_id": 0, "id": 1})
        if not vt:
            _err({"visit_type_id": "Escolha o tipo de visita usado no link"})
    if vtid:
        upd["selfreg_visit_type_id"] = vtid
    if body.get("regenerate") or not comp.get("selfreg_code"):
        for _ in range(10):
            code = new_code()
            if not await db.companies.find_one({"selfreg_code": code}, {"_id": 1}) and \
                    not await db.settings.find_one({"id": "selfreg", "site_code": code}, {"_id": 1}):
                upd["selfreg_code"] = code
                break
    await db.companies.update_one({"id": cid}, {"$set": upd})
    await log_audit(user, "autocadastro:link", "company", cid, str(upd), client_ip(request))
    c = await db.companies.find_one({"id": cid}, {"_id": 0, "id": 1, "name": 1, "selfreg_enabled": 1, "selfreg_code": 1,
                                                  "selfreg_visit_type_id": 1})
    c["link"] = link(f"/v/{c['selfreg_code']}") if c.get("selfreg_code") else ""
    return c


# ---------------- QR único do local ----------------
@router.get("/site-link")
async def get_site_link(user: dict = Depends(require_role("admin"))):
    s = await get_settings()
    return {"enabled": bool(s.get("site_enabled")), "code": s.get("site_code", ""),
            "link": link(f"/v/{s['site_code']}") if s.get("site_code") else "", "companies": await site_companies()}


@router.put("/site-link")
async def set_site_link(body: dict, request: Request, user: dict = Depends(require_role("admin"))):
    s = await get_settings()
    upd = {"site_enabled": bool(body.get("enabled"))}
    if body.get("regenerate") or not s.get("site_code"):
        for _ in range(10):
            code = new_code()
            if not await db.companies.find_one({"selfreg_code": code}, {"_id": 1}):
                upd["site_code"] = code
                break
    await db.settings.update_one({"id": "selfreg"}, {"$set": upd}, upsert=True)
    await log_audit(user, "autocadastro:qr-unico", "settings", "selfreg", str(upd), client_ip(request))
    return await get_site_link(user)


# ---------------- configurações ----------------
@router.get("/settings")
async def read_settings(user: dict = Depends(require_role(*WRITE))):
    s = await get_settings()
    return {**s, "email_enabled": cfg.EMAIL_ENABLED, "public_url": cfg.PUBLIC_URL, "captcha": bool(TURNSTILE_SITE_KEY)}


@router.put("/settings")
async def write_settings(body: dict, request: Request, user: dict = Depends(require_role("admin"))):
    def num(k, lo, hi):
        try:
            v = int(body.get(k, DEFAULTS[k]))
            assert lo <= v <= hi
            return v
        except (TypeError, ValueError, AssertionError):
            _err({k: f"Valor entre {lo} e {hi}"})
    s = {"enabled": bool(body.get("enabled", True)), "require_otp": bool(body.get("require_otp", True)),
         "invite_hours": num("invite_hours", 1, 720), "approval_hours": num("approval_hours", 1, 168),
         "visitor_retention_days": num("visitor_retention_days", 0, 3650), "recurring_months": num("recurring_months", 1, 60),
         "max_days_ahead": num("max_days_ahead", 1, 180),
         "lgpd_text": (_s(body.get("lgpd_text"), 4000) or DEFAULTS["lgpd_text"]).strip(), "updated_at": now_iso()}
    await db.settings.update_one({"id": "selfreg"}, {"$set": s}, upsert=True)
    await log_audit(user, "editar", "settings", "selfreg", "", client_ip(request))
    return await read_settings(user)

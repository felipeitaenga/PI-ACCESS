import os
import logging
import asyncio
import hashlib
import smtplib
import secrets as pysecrets
from email.message import EmailMessage
from html import escape
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Request, Response, HTTPException, Depends, BackgroundTasks
from bson import ObjectId

from database import db
from models import (RegisterInput, LoginInput, ForgotPasswordInput, ResetPasswordInput,
                    UserCreateInput, UserUpdateInput)
from security import (hash_password, verify_password, create_access_token,
                      create_refresh_token, set_auth_cookies, get_current_user,
                      require_role, get_jwt_secret, ROLE_LABELS)
import jwt as pyjwt
import app_config as cfg

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

EMAIL_FROM_NAME = cfg.CLIENTE_NOME and f"PI-ACCESS · {cfg.CLIENTE_NOME}" or "PI-ACCESS"

MAX_ATTEMPTS = 5
LOCK_MINUTES = 15


def _public_user(user: dict) -> dict:
    return {
        "id": str(user["_id"]) if "_id" in user else user.get("id"),
        "email": user["email"],
        "name": user.get("name", ""),
        "role": user.get("role", "viewer"),
        "role_label": ROLE_LABELS.get(user.get("role", "viewer"), ""),
        "site_ids": user.get("site_ids", []),
        "active": user.get("active", True),
    }


def _smtp_send(msg: EmailMessage):
    if cfg.SMTP_PORT == 465:
        s = smtplib.SMTP_SSL(cfg.SMTP_HOST, cfg.SMTP_PORT, timeout=30)
    else:
        s = smtplib.SMTP(cfg.SMTP_HOST, cfg.SMTP_PORT, timeout=30)
        s.ehlo()
        if s.has_extn("starttls"):
            s.starttls()
            s.ehlo()
    with s:
        if cfg.SMTP_USER:
            s.login(cfg.SMTP_USER, cfg.SMTP_PASSWORD)
        s.send_message(msg)


async def send_password_reset_email(to_email: str, token: str) -> bool:
    link = f"{cfg.PUBLIC_URL}/reset-password?token={token}"
    if not cfg.EMAIL_ENABLED or not cfg.PUBLIC_URL:
        logger.error("E-mail de redefinição não configurado (SMTP_HOST / PUBLIC_URL)")
        return False
    brand = escape(EMAIL_FROM_NAME)
    html = (
        f'<table role="presentation" width="100%"><tr><td style="padding:24px;font-family:Arial,sans-serif">'
        f'<p>Recebemos uma solicitação para redefinir sua senha no {brand}.</p>'
        f'<p><a href="{escape(link)}">Redefinir minha senha</a></p>'
        f'<p>Este link expira em 1 hora e pode ser usado uma única vez. Se você não solicitou, '
        f'ignore este e-mail — sua senha permanece inalterada.</p>'
        f'<p style="font-size:12px;color:#888">Enviado por {brand}. Nunca pedimos sua senha por e-mail.</p>'
        f'</td></tr></table>'
    )
    msg = EmailMessage()
    msg["Subject"] = f"Redefinição de senha {EMAIL_FROM_NAME}"
    msg["From"] = f"{EMAIL_FROM_NAME} <{cfg.SMTP_FROM}>"
    msg["To"] = to_email
    msg.set_content(f"Para redefinir sua senha acesse: {link}\nO link expira em 1 hora.")
    msg.add_alternative(html, subtype="html")
    try:
        await asyncio.to_thread(_smtp_send, msg)
        return True
    except Exception as e:
        logger.error(f"Falha no e-mail de redefinição: {e}")
        return False


async def _check_lockout(ip: str, email: str):
    ident = f"{ip}:{email}"
    window = datetime.now(timezone.utc) - timedelta(minutes=LOCK_MINUTES)
    count = await db.login_attempts.count_documents({
        "identifier": ident,
        "ts": {"$gte": window.isoformat()},
    })
    if count >= MAX_ATTEMPTS:
        raise HTTPException(status_code=429, detail="Muitas tentativas. Tente novamente em 15 minutos.")


async def _record_fail(ip: str, email: str):
    await db.login_attempts.insert_one({
        "identifier": f"{ip}:{email}", "email": email,
        "ip": ip, "ts": datetime.now(timezone.utc).isoformat(),
    })


@router.post("/register")
async def register(payload: RegisterInput, response: Response):
    email = payload.email.lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="E-mail já cadastrado")
    doc = {
        "email": email, "password_hash": hash_password(payload.password),
        "name": payload.name, "role": payload.role, "site_ids": [],
        "active": True, "token_version": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    res = await db.users.insert_one(doc)
    uid = str(res.inserted_id)
    at, rt = create_access_token(uid, email, 0), create_refresh_token(uid, 0)
    set_auth_cookies(response, at, rt)
    doc["_id"] = res.inserted_id
    return {**_public_user(doc), "access_token": at, "refresh_token": rt}


@router.post("/login")
async def login(payload: LoginInput, request: Request, response: Response):
    email = payload.email.lower()
    ip = request.client.host if request.client else "unknown"
    await _check_lockout(ip, email)
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(payload.password, user["password_hash"]):
        await _record_fail(ip, email)
        raise HTTPException(status_code=401, detail="Credenciais inválidas")
    if not user.get("active", True):
        raise HTTPException(status_code=403, detail="Usuário desativado")
    await db.login_attempts.delete_many({"identifier": f"{ip}:{email}"})
    uid = str(user["_id"])
    ver = user.get("token_version", 0)
    at, rt = create_access_token(uid, email, ver), create_refresh_token(uid, ver)
    set_auth_cookies(response, at, rt)
    return {**_public_user(user), "access_token": at, "refresh_token": rt}


@router.post("/logout")
async def logout(response: Response, user: dict = Depends(get_current_user)):
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    return {"ok": True}


@router.get("/me")
async def me(user: dict = Depends(get_current_user)):
    return _public_user(user)


@router.post("/refresh")
async def refresh(request: Request, response: Response):
    token = request.cookies.get("refresh_token")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    if not token:
        try:
            body = await request.json()
            token = body.get("refresh_token")
        except Exception:
            token = None
    if not token:
        raise HTTPException(status_code=401, detail="Sem token de atualização")
    try:
        payload = pyjwt.decode(token, get_jwt_secret(), algorithms=["HS256"])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Tipo inválido")
        user = await db.users.find_one({"_id": ObjectId(payload["sub"])})
        if not user or payload.get("ver", 0) != user.get("token_version", 0):
            raise HTTPException(status_code=401, detail="Sessão expirada")
        uid = str(user["_id"])
        ver = user.get("token_version", 0)
        at, rt = create_access_token(uid, user["email"], ver), create_refresh_token(uid, ver)
        set_auth_cookies(response, at, rt)
        return {**_public_user(user), "access_token": at, "refresh_token": rt}
    except pyjwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token inválido")


@router.post("/forgot-password")
async def forgot_password(payload: ForgotPasswordInput, background_tasks: BackgroundTasks):
    email = payload.email.lower()
    if not cfg.EMAIL_ENABLED:
        raise HTTPException(status_code=400, detail="Recuperação por e-mail desativada. Peça ao administrador para redefinir sua senha.")
    generic = {"message": "Se o e-mail estiver cadastrado, um link de redefinição foi enviado."}
    await db.password_reset_requests.insert_one({"email": email, "created_at": datetime.now(timezone.utc)})
    window = datetime.now(timezone.utc) - timedelta(minutes=15)
    recent = await db.password_reset_requests.count_documents({"email": email, "created_at": {"$gte": window}})
    if recent > MAX_ATTEMPTS:
        return generic
    user = await db.users.find_one({"email": email})
    if not user:
        return generic
    token = pysecrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    await db.password_reset_tokens.insert_one({
        "token_hash": token_hash, "user_id": str(user["_id"]), "email": user["email"],
        "expires_at": datetime.now(timezone.utc) + timedelta(hours=1), "used": False,
    })
    background_tasks.add_task(send_password_reset_email, user["email"], token)
    return generic


@router.post("/reset-password")
async def reset_password(payload: ResetPasswordInput):
    h = hashlib.sha256(payload.token.encode()).hexdigest()
    now = datetime.now(timezone.utc)
    doc = await db.password_reset_tokens.find_one_and_update(
        {"token_hash": h, "used": False, "expires_at": {"$gt": now}},
        {"$set": {"used": True}},
    )
    if not doc:
        raise HTTPException(status_code=400, detail="Token inválido ou expirado")
    await db.users.update_one(
        {"_id": ObjectId(doc["user_id"])},
        {"$set": {"password_hash": hash_password(payload.password)}, "$inc": {"token_version": 1}},
    )
    await db.password_reset_tokens.delete_many({"user_id": doc["user_id"], "used": False})
    await db.login_attempts.delete_many({"email": doc["email"]})
    return {"ok": True, "message": "Senha redefinida com sucesso"}


# ---------- Gestão de usuários (admin) ----------
@router.get("/users")
async def list_users(user: dict = Depends(require_role("admin"))):
    users = await db.users.find({}).to_list(500)
    return [_public_user(u) for u in users]


@router.post("/users")
async def create_user(payload: UserCreateInput, user: dict = Depends(require_role("admin"))):
    email = payload.email.lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="E-mail já cadastrado")
    doc = {
        "email": email, "password_hash": hash_password(payload.password),
        "name": payload.name, "role": payload.role, "site_ids": payload.site_ids,
        "active": True, "token_version": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    res = await db.users.insert_one(doc)
    doc["_id"] = res.inserted_id
    return _public_user(doc)


@router.put("/users/{user_id}")
async def update_user(user_id: str, payload: UserUpdateInput, user: dict = Depends(require_role("admin"))):
    updates = {}
    if payload.name is not None:
        updates["name"] = payload.name
    if payload.role is not None:
        updates["role"] = payload.role
    if payload.site_ids is not None:
        updates["site_ids"] = payload.site_ids
    if payload.active is not None:
        updates["active"] = payload.active
    inc = {}
    if payload.password:
        updates["password_hash"] = hash_password(payload.password)
        inc["token_version"] = 1
    if not updates and not inc:
        raise HTTPException(status_code=400, detail="Nada para atualizar")
    op = {}
    if updates:
        op["$set"] = updates
    if inc:
        op["$inc"] = inc
    await db.users.update_one({"_id": ObjectId(user_id)}, op)
    u = await db.users.find_one({"_id": ObjectId(user_id)})
    return _public_user(u)


@router.delete("/users/{user_id}")
async def delete_user(user_id: str, user: dict = Depends(require_role("admin"))):
    if str(user["_id"]) == user_id:
        raise HTTPException(status_code=400, detail="Não é possível excluir o próprio usuário")
    await db.users.delete_one({"_id": ObjectId(user_id)})
    return {"ok": True}

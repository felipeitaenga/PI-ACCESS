import os
import base64
import hashlib
import jwt
import bcrypt
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException, Request, Depends
from bson import ObjectId
from cryptography.fernet import Fernet

from database import db

JWT_ALGORITHM = "HS256"

ROLE_LABELS = {
    "admin": "Administrador",
    "operator": "Operador",
    "reception": "Recepção",
    "viewer": "Somente leitura",
}

def _fernet_key(raw: str) -> bytes:
    try:
        Fernet(raw.encode())
        return raw.encode()
    except Exception:
        return base64.urlsafe_b64encode(hashlib.sha256(raw.encode()).digest())


_fernet = Fernet(_fernet_key(os.environ["ENCRYPTION_KEY"]))


def encrypt_secret(value: str) -> str:
    if value is None:
        return ""
    return _fernet.encrypt(value.encode()).decode()


def decrypt_secret(token: str) -> str:
    if not token:
        return ""
    try:
        return _fernet.decrypt(token.encode()).decode()
    except Exception:
        return ""


def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def get_jwt_secret() -> str:
    return os.environ["JWT_SECRET"]


def create_access_token(user_id: str, email: str, token_version: int = 0) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "ver": token_version,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
        "type": "access",
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)


def create_refresh_token(user_id: str, token_version: int = 0) -> str:
    payload = {
        "sub": user_id,
        "ver": token_version,
        "exp": datetime.now(timezone.utc) + timedelta(days=7),
        "type": "refresh",
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)


def set_auth_cookies(response, access_token: str, refresh_token: str):
    response.set_cookie("access_token", access_token, httponly=True, secure=True,
                        samesite="none", max_age=900, path="/")
    response.set_cookie("refresh_token", refresh_token, httponly=True, secure=True,
                        samesite="none", max_age=604800, path="/")


def _token_from_request(request: Request):
    token = request.cookies.get("access_token")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    return token


async def resolve_user_from_token(token: str):
    if not token:
        return None
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "access":
            return None
        user = await db.users.find_one({"_id": ObjectId(payload["sub"])})
        if not user:
            return None
        if payload.get("ver", 0) != user.get("token_version", 0):
            return None
        user["_id"] = str(user["_id"])
        user.pop("password_hash", None)
        return user
    except Exception:
        return None


async def get_current_user(request: Request) -> dict:
    token = _token_from_request(request)
    if not token:
        raise HTTPException(status_code=401, detail="Não autenticado")
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Tipo de token inválido")
        user = await db.users.find_one({"_id": ObjectId(payload["sub"])})
        if not user:
            raise HTTPException(status_code=401, detail="Usuário não encontrado")
        if payload.get("ver", 0) != user.get("token_version", 0):
            raise HTTPException(status_code=401, detail="Sessão expirada")
        user["_id"] = str(user["_id"])
        user.pop("password_hash", None)
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expirado")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token inválido")


def require_role(*roles):
    async def checker(user: dict = Depends(get_current_user)):
        if roles and user.get("role") not in roles:
            raise HTTPException(status_code=403, detail="Permissão insuficiente")
        return user
    return checker

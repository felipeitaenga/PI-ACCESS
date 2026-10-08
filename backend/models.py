import uuid
from datetime import datetime, timezone
from typing import Optional, List
from pydantic import BaseModel, Field, EmailStr


def new_id() -> str:
    return str(uuid.uuid4())


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------- Auth ----------
class RegisterInput(BaseModel):
    email: EmailStr
    password: str
    name: str = "Usuário"
    role: str = "viewer"


class LoginInput(BaseModel):
    email: EmailStr
    password: str


class ForgotPasswordInput(BaseModel):
    email: EmailStr


class ResetPasswordInput(BaseModel):
    token: str
    password: str


class UserCreateInput(BaseModel):
    email: EmailStr
    password: str
    name: str
    role: str = "operator"
    site_ids: List[str] = []


class UserUpdateInput(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    site_ids: Optional[List[str]] = None
    active: Optional[bool] = None
    password: Optional[str] = None


# ---------- Structure ----------
class SiteInput(BaseModel):
    name: str
    address: str = ""
    timezone: str = "America/Sao_Paulo"


class AreaInput(BaseModel):
    site_id: str
    name: str
    max_occupancy: int = 0
    anti_passback: str = "none"  # none | hard | soft


class DoorInput(BaseModel):
    site_id: str
    area_id: str
    name: str
    description: str = ""


# ---------- Devices ----------
class DeviceInput(BaseModel):
    site_id: str
    area_id: Optional[str] = None
    door_id: Optional[str] = None
    name: str
    brand: str = "simulado"  # simulado | controlid | hikvision | intelbras | zkteco
    model: str = ""
    ip: str = ""
    port: int = 80
    username: str = ""
    password: str = ""
    connection_mode: str = "direct"  # direct | agent
    reader_type: str = "entrada"  # entrada | saida


# ---------- People ----------
class PersonInput(BaseModel):
    name: str
    matricula: str = ""
    document: str = ""
    company: str = ""
    department: str = ""
    role_title: str = ""
    photo: str = ""
    person_type: str = "colaborador"  # colaborador | terceiro
    valid_until: Optional[str] = None
    status: str = "ativo"  # ativo | inativo | bloqueado
    consent: bool = False


class DoorActionInput(BaseModel):
    seconds: int = 5
    reason: str = ""


class DoorModeInput(BaseModel):
    mode: str  # normal | liberada | bloqueada

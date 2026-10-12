"""Backup do banco (somente Administrador)."""
import os
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from database import db, create_indexes
from security import require_role
from util import log_audit, client_ip
import backup_service as bs

router = APIRouter(prefix="/backups", tags=["backups"])
ADMIN = require_role("admin")
CHUNK_MAX = 8 * 1024 * 1024


def _p(name):
    try:
        p = bs.path_of(name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return p


@router.get("")
async def list_all(user: dict = Depends(ADMIN)):
    return {"items": bs.list_backups(), "settings": await bs.get_settings()}


@router.post("")
async def create(request: Request, user: dict = Depends(ADMIN)):
    b = await bs.create_backup("manual", user.get("email"))
    await log_audit(user, "backup", "backup", b["name"], f"{b['documents']} documentos", client_ip(request))
    return b


@router.put("/settings")
async def save_settings(body: dict, request: Request, user: dict = Depends(ADMIN)):
    t = str(body.get("time") or "03:00")
    if not (len(t) == 5 and t[2] == ":" and t[:2].isdigit() and t[3:].isdigit() and int(t[:2]) < 24 and int(t[3:]) < 60):
        raise HTTPException(status_code=422, detail="Horário inválido (HH:MM)")
    keep = int(body.get("keep") or 7)
    if not 1 <= keep <= 90:
        raise HTTPException(status_code=422, detail="Quantidade de cópias deve ser entre 1 e 90")
    s = {"enabled": bool(body.get("enabled")), "time": t, "keep": keep}
    await db.settings.update_one({"id": "backup"}, {"$set": s}, upsert=True)
    await log_audit(user, "editar", "settings", "backup", str(s), client_ip(request))
    return await bs.get_settings()


@router.get("/{name}/download")
async def download(name: str, user: dict = Depends(ADMIN)):
    p = _p(name)
    if not os.path.exists(p):
        raise HTTPException(status_code=404, detail="Backup não encontrado")
    return FileResponse(p, media_type="application/gzip", filename=name)


@router.delete("/{name}")
async def remove(name: str, request: Request, user: dict = Depends(ADMIN)):
    if not os.path.exists(_p(name)):
        raise HTTPException(status_code=404, detail="Backup não encontrado")
    bs.delete_backup(name)
    await log_audit(user, "excluir", "backup", name, "", client_ip(request))
    return {"ok": True}


@router.put("/upload")
async def upload_chunk(request: Request, upload_id: str, offset: int = 0, done: int = 0, user: dict = Depends(ADMIN)):
    """Envio em partes (evita limite do proxy). Ao final vira um backup 'enviado' validado."""
    if not upload_id.isalnum() or len(upload_id) > 40:
        raise HTTPException(status_code=400, detail="upload_id inválido")
    os.makedirs(bs.BACKUP_DIR, exist_ok=True)
    part = os.path.join(bs.BACKUP_DIR, f"upload_{upload_id}.part")
    data = await request.body()
    if len(data) > CHUNK_MAX:
        raise HTTPException(status_code=413, detail="Parte muito grande")
    size = os.path.getsize(part) if os.path.exists(part) else 0
    if offset != size:
        raise HTTPException(status_code=409, detail=f"Offset esperado {size}")
    with open(part, "ab") as f:
        f.write(data)
    if not done:
        return {"received": size + len(data)}
    try:
        bs.validate_file(part)
    except Exception as e:  # noqa: BLE001
        os.remove(part)
        raise HTTPException(status_code=422, detail=f"Arquivo inválido: {e}")
    name = bs.new_name("enviado")
    os.replace(part, bs.path_of(name))
    await log_audit(user, "upload", "backup", name, "", client_ip(request))
    return {"name": name}


@router.post("/{name}/restore")
async def restore(name: str, body: dict, request: Request, user: dict = Depends(ADMIN)):
    if (body.get("confirm") or "").strip() != "RESTAURAR":
        raise HTTPException(status_code=400, detail='Digite RESTAURAR para confirmar')
    p = _p(name)
    if not os.path.exists(p):
        raise HTTPException(status_code=404, detail="Backup não encontrado")
    try:
        head = bs.validate_file(p)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"Arquivo inválido: {e}")
    origem = head.get("cliente")
    if origem and origem != bs.cfg.CLIENTE:
        raise HTTPException(status_code=422,
                            detail=f"Este backup é do cliente '{origem}' e não pode ser restaurado em '{bs.cfg.CLIENTE}'")
    safety = await bs.create_backup("seguranca", user.get("email"))
    counts = await bs.restore_backup(name)
    await create_indexes()
    from migrations import run_migrations
    await run_migrations()
    await log_audit(user, "restaurar", "backup", name, f"seguran\u00e7a={safety['name']} cole\u00e7\u00f5es={len(counts)}", client_ip(request))
    return {"ok": True, "safety_backup": safety["name"], "collections": counts}

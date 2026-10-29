"""Intelbras Bio-T — rotas chamadas PELO FACIAL (Modo Online) e configuração pelo admin.

O facial se identifica pelo token secreto no caminho (/api/intelbras/<token>/...),
gerado por controladora (o facial não manda usuário/senha nessas chamadas).
"""
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from database import db
from security import require_role
from util import log_audit, client_ip
from drivers.factory import get_driver
from intelbras_ingest import handle_notification, heartbeat

router = APIRouter(tags=["intelbras"])


async def _ctrl_by_token(token: str):
    if not token or len(token) < 16:
        return None
    return await db.controllers.find_one({"intelbras_token": token, "deleted": {"$ne": True}, "brand": "intelbras"},
                                         {"_id": 0})


@router.api_route("/intelbras/{token}/keepalive", methods=["GET", "POST"])
async def keepalive(token: str, request: Request):
    ctrl = await _ctrl_by_token(token)
    if not ctrl:
        return PlainTextResponse("Not Found", status_code=404)
    await heartbeat(ctrl, request.client.host if request.client else None)
    return PlainTextResponse("OK")


@router.post("/intelbras/{token}/notification")
async def notification(token: str, request: Request):
    ctrl = await _ctrl_by_token(token)
    if not ctrl:
        return PlainTextResponse("Not Found", status_code=404)
    body = await request.body()
    reply = await handle_notification(ctrl, body, request.headers.get("content-type", ""))
    return JSONResponse(reply)


@router.post("/equipment/controllers/{cid}/intelbras/online-mode")
async def setup_online_mode(cid: str, body: dict, request: Request, user: dict = Depends(require_role("admin"))):
    """Configura no facial o envio de eventos + Modo Online apontando para o SCARVEL.
    host/port: endereço que O FACIAL usa para chegar ao SCARVEL (ex.: IP do roteador da VPN no local)."""
    ctrl = await db.controllers.find_one({"id": cid, "deleted": {"$ne": True}}, {"_id": 0})
    if not ctrl or ctrl.get("brand") != "intelbras":
        raise HTTPException(status_code=404, detail="Facial Intelbras não encontrado")
    host = str(body.get("host") or "").strip()
    try:
        port = int(body.get("port") or 80)
    except (TypeError, ValueError):
        port = 0
    if not host or not 0 < port < 65536:
        raise HTTPException(status_code=422, detail="Informe o endereço e a porta que o facial usa para chegar ao SCARVEL")
    token = ctrl.get("intelbras_token") or secrets.token_urlsafe(24)
    await db.controllers.update_one({"id": cid}, {"$set": {"intelbras_token": token, "intelbras_push": {"host": host, "port": port}}})
    r = await get_driver(ctrl).configure_online(host, port, token)
    if r.get("ok"):
        await db.controllers.update_one({"id": cid}, {"$set": {"online_mode": True}})
        await get_driver(ctrl).set_datetime()
    await log_audit(user, "intelbras_modo_online", "controllers", cid,
                    f"{host}:{port} → {'ok' if r.get('ok') else r.get('detail')}", client_ip(request))
    if not r.get("ok"):
        raise HTTPException(status_code=502, detail=f"Facial recusou ({r.get('step')}): {r.get('detail')}")
    return {"ok": True, "paths": {"notification": f"/api/intelbras/{token[:4]}…/notification",
                                  "keepalive": f"/api/intelbras/{token[:4]}…/keepalive"}}

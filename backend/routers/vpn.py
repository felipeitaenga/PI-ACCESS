"""Configurações › Rede / VPN — o MikroTik do cliente (um por cliente)."""
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse

import app_config as cfg
import vpn
from database import db
from security import require_role, encrypt_secret, decrypt_secret
from util import log_audit, client_ip

router = APIRouter(tags=["vpn"])
LINK_MINUTES = 15


def _public(st, req):
    ready = vpn.ready(st, req)
    return {"configured": bool(st.get("n")), "ready": ready, "pending": bool(req.get("pubkey")) and not ready,
            "online": ready and vpn.online(st), "n": st.get("n"), "vpn_ip": f"10.66.0.{st['n']}" if st.get("n") else None,
            "facial_net": f"10.67.{st['n']}.0/24" if st.get("n") else None, "identity": vpn.identity(st) if st.get("n") else None,
            "app_port": st.get("app_port"), "latest_handshake": st.get("latest_handshake"),
            "rx_bytes": st.get("rx"), "tx_bytes": st.get("tx"), "updated_at": st.get("updated_at"),
            "requested_at": req.get("requested_at"), "push": vpn.push_target(), "lan": "192.168.88.0/24"}


@router.get("/vpn")
async def vpn_status(user: dict = Depends(require_role("admin"))):
    return _public(vpn.status(), vpn.request())


@router.post("/vpn/mikrotik")
async def new_mikrotik(request: Request, user: dict = Depends(require_role("admin"))):
    """Gera (ou troca) as chaves do MikroTik deste cliente e pede a liberação ao servidor."""
    priv, pub = vpn.keypair()
    await db.vpn_keys.update_one({"id": "mikrotik"}, {"$set": {"id": "mikrotik", "priv_enc": encrypt_secret(priv), "pubkey": pub,
                                                               "created_at": datetime.now(timezone.utc).isoformat()}}, upsert=True)
    vpn.save_request(pub)
    await log_audit(user, "vpn_gerar_mikrotik", "vpn", "mikrotik", "novas chaves do MikroTik", client_ip(request))
    return _public(vpn.status(), vpn.request())


async def _script():
    st, req = vpn.status(), vpn.request()
    if not vpn.ready(st, req):
        raise HTTPException(status_code=409, detail="Aguardando o servidor liberar a VPN (até 30 s). Tente de novo.")
    k = await db.vpn_keys.find_one({"id": "mikrotik"}, {"_id": 0})
    if not k or k.get("pubkey") != req.get("pubkey"):
        raise HTTPException(status_code=409, detail="Chave do MikroTik não encontrada: gere de novo.")
    return vpn.mikrotik_script(decrypt_secret(k["priv_enc"]), st)


@router.get("/vpn/mikrotik/script")
async def mikrotik_script(user: dict = Depends(require_role("admin"))):
    return PlainTextResponse(await _script())


@router.post("/vpn/mikrotik/link")
async def mikrotik_link(request: Request, user: dict = Depends(require_role("admin"))):
    """Link de uso único (15 min) para o MikroTik baixar o script com /tool fetch."""
    await _script()
    token = secrets.token_urlsafe(24)
    await db.vpn_links.insert_one({"token": token, "used": False,
                                   "expires": (datetime.now(timezone.utc) + timedelta(minutes=LINK_MINUTES)).isoformat()})
    await log_audit(user, "vpn_link_mikrotik", "vpn", "mikrotik", "link de 15 min", client_ip(request))
    url = f"{cfg.PUBLIC_URL}/api/public/vpn/{token}.rsc"
    return {"url": url, "minutes": LINK_MINUTES,
            "commands": [f'/tool fetch url="{url}" dst-path=scarvel.rsc', "/import scarvel.rsc"]}


@router.get("/public/vpn/{token}.rsc")
async def public_script(token: str):
    link = await db.vpn_links.find_one_and_update({"token": token, "used": False}, {"$set": {"used": True}})
    if not link or link["expires"] < datetime.now(timezone.utc).isoformat():
        return PlainTextResponse("# link expirado ou já usado: gere outro no SCARVEL\n", status_code=404)
    return PlainTextResponse(await _script())

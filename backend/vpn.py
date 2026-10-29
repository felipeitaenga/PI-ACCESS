"""VPN do cliente (um MikroTik por cliente) — lado do app.

O app NÃO mexe na VPN do servidor. Ele conversa com o script do servidor (scarvel-vpn sync) por arquivos
no volume de dados do cliente:
  <DATA_DIR>/vpn/request.json  ← app: chave pública do MikroTik que quer usar
  <DATA_DIR>/vpn/status.json   → servidor: nº do cliente, chave do servidor, porta do app, último contato

Padrão de rede (igual em todo cliente):
  MikroTik: 192.168.88.1 (rede só do controle de acesso) · faciais 192.168.88.101 … .199
  VPN: servidor 10.66.0.1 · MikroTik 10.66.0.N · faciais vistos pelo servidor como 10.67.N.x (netmap)
"""
import base64
import ipaddress
import json
import os
import secrets
from datetime import datetime, timezone

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

import app_config as cfg

LAN = ipaddress.ip_network("192.168.88.0/24")
SERVER_VPN_IP = "10.66.0.1"
ONLINE_HANDSHAKE_S = 180


def _dir():
    d = os.path.join(cfg.DATA_DIR, "vpn")
    os.makedirs(d, exist_ok=True)
    return d


def _read(name):
    try:
        with open(os.path.join(_dir(), name)) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _write(name, data):
    p = os.path.join(_dir(), name)
    tmp = p + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f)
    os.replace(tmp, p)


def keypair():
    k = X25519PrivateKey.generate()
    priv = k.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
    pub = k.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return base64.b64encode(priv).decode(), base64.b64encode(pub).decode()


def status():
    return _read("status.json")


def request():
    return _read("request.json")


def save_request(pubkey):
    _write("request.json", {"pubkey": pubkey, "cliente": cfg.CLIENTE,
                            "requested_at": datetime.now(timezone.utc).isoformat(), "nonce": secrets.token_hex(4)})


def ready(st=None, req=None):
    """Servidor já liberou a chave pedida pelo app?"""
    st = st if st is not None else status()
    req = req if req is not None else request()
    return bool(st.get("n") and req.get("pubkey") and st.get("peer_pubkey") == req.get("pubkey"))


def online(st=None):
    st = st if st is not None else status()
    hs = st.get("latest_handshake") or 0
    upd = st.get("updated_at") or 0
    return bool(hs) and (max(upd, hs) - hs) < ONLINE_HANDSHAKE_S and (datetime.now(timezone.utc).timestamp() - upd) < 300


def identity(st=None):
    st = st if st is not None else status()
    return f"SCARVEL-{cfg.CLIENTE}-{st.get('n', '')}"


def device_addr(ip, port=80):
    """Endereço que o SERVIDOR usa para chegar ao facial: 192.168.88.x → 10.67.N.x (porta original).
    IP fora da rede padrão é usado como está (instalações antigas / IP manual)."""
    try:
        a = ipaddress.ip_address(str(ip).strip())
    except ValueError:
        return ip, port
    st = status()
    if a in LAN and st.get("n"):
        return f"10.67.{int(st['n'])}.{int(str(a).split('.')[-1])}", port
    return ip, port


def push_target():
    """Para onde o FACIAL manda o Modo Online (rota pelo MikroTik até o servidor)."""
    st = status()
    if st.get("app_port"):
        return {"host": SERVER_VPN_IP, "port": int(st["app_port"])}
    return None


def mikrotik_script(priv_key: str, st: dict) -> str:
    n = int(st["n"])
    ident = identity(st)
    return f"""# ===== SCARVEL — MikroTik do cliente {cfg.CLIENTE} (nº {n}) =====
# Padrão: porta 1 = internet do cliente · portas 2-5 = rede do controle de acesso 192.168.88.0/24
# Faciais com IP fixo 192.168.88.101 a .199 e gateway 192.168.88.1
/system identity set name="{ident}"
# remove configuração SCARVEL anterior (pode rodar de novo sem problema)
/ip firewall filter remove [find comment~"^scarvel"]
/ip firewall nat remove [find comment~"^scarvel"]
/ip address remove [find comment~"^scarvel"]
/interface wireguard peers remove [find comment~"^scarvel"]
/interface wireguard remove [find comment~"^scarvel"]
# VPN até o servidor SCARVEL
/interface wireguard add name=wg-scarvel listen-port=13231 private-key="{priv_key}" comment=scarvel
/interface wireguard peers add interface=wg-scarvel public-key="{st['server_pubkey']}" endpoint-address={st['endpoint']} endpoint-port={st.get('endpoint_port', 51820)} allowed-address={SERVER_VPN_IP}/32 persistent-keepalive=25s comment=scarvel
/ip address add address=10.66.0.{n}/24 interface=wg-scarvel comment=scarvel
# servidor -> faciais: 10.67.{n}.x = 192.168.88.x
/ip firewall nat add chain=dstnat in-interface=wg-scarvel dst-address=10.67.{n}.0/24 action=netmap to-addresses=192.168.88.0/24 comment=scarvel
/ip firewall nat add chain=srcnat out-interface=wg-scarvel action=masquerade comment=scarvel
/ip firewall filter add chain=forward in-interface=wg-scarvel dst-address=192.168.88.0/24 action=accept place-before=0 comment=scarvel
# servidor pode administrar este MikroTik pela VPN (WinBox/web/API)
/ip firewall filter add chain=input in-interface=wg-scarvel src-address={SERVER_VPN_IP} action=accept place-before=0 comment=scarvel
# DHCP só de .10 a .99 (faixa .101-.199 reservada para os faciais)
:do {{ /ip pool set [find name=default-dhcp] ranges=192.168.88.10-192.168.88.99 }} on-error={{}}
:put "OK: {ident} configurado. Aguarde 30 s e veja o status no SCARVEL (Configurações > Rede / VPN)."
# ===== fim =====
"""

"""Rede / VPN: app pede a liberação do MikroTik por arquivo; o servidor (scarvel-vpn-sync) responde no status.json."""
import json
import os

import mongomock_motor
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app_config as cfg
import vpn
from routers import vpn as rvpn
from security import get_current_user


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(cfg, "CLIENTE", "pilares")
    monkeypatch.setattr(cfg, "PUBLIC_URL", "https://pilares.scarvel.com.br")
    db = mongomock_motor.AsyncMongoMockClient()["t_vpn"]
    monkeypatch.setattr(rvpn, "db", db)

    async def _noop(*a, **k):
        return None
    monkeypatch.setattr(rvpn, "log_audit", _noop)
    app = FastAPI()
    app.include_router(rvpn.router, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: {"id": "a", "role": "admin", "name": "Admin"}
    return TestClient(app), tmp_path


def _server_answers(tmp_path, n=2, port=8101, handshake=0):
    """Simula o scarvel-vpn-sync liberando a chave pedida."""
    req = json.load(open(tmp_path / "vpn" / "request.json"))
    st = {"n": n, "server_pubkey": "S" * 43 + "=", "endpoint": "156.67.82.199", "endpoint_port": 51820,
          "app_port": port, "peer_pubkey": req["pubkey"], "updated_at": 1_900_000_000, "latest_handshake": handshake}
    json.dump(st, open(tmp_path / "vpn" / "status.json", "w"))


def test_keypair_is_wireguard_format():
    priv, pub = vpn.keypair()
    assert len(priv) == 44 and len(pub) == 44 and priv != pub


def test_full_flow_generate_wait_script_link(env):
    c, tmp = env
    assert c.get("/api/vpn").json()["configured"] is False
    r = c.post("/api/vpn/mikrotik").json()
    assert r["pending"] is True and r["ready"] is False
    assert c.get("/api/vpn/mikrotik/script").status_code == 409  # servidor ainda não liberou
    _server_answers(tmp)
    st = c.get("/api/vpn").json()
    assert st["ready"] and st["n"] == 2 and st["identity"] == "SCARVEL-pilares-2" and st["push"] == {"host": "10.66.0.1", "port": 8101}
    script = c.get("/api/vpn/mikrotik/script").text
    pub = json.load(open(tmp / "vpn" / "request.json"))["pubkey"]
    assert 'name="SCARVEL-pilares-2"' in script and "10.66.0.2/24" in script and "10.67.2.0/24" in script
    assert "endpoint-address=156.67.82.199" in script and 'private-key="' in script and pub not in script
    link = c.post("/api/vpn/mikrotik/link").json()
    token_path = link["url"].split("/api")[1]
    assert link["url"].startswith("https://pilares.scarvel.com.br/api/public/vpn/")
    assert c.get("/api" + token_path).text == script
    assert c.get("/api" + token_path).status_code == 404  # uso único


def test_regenerate_waits_for_new_key(env):
    c, tmp = env
    c.post("/api/vpn/mikrotik")
    _server_answers(tmp)
    c.post("/api/vpn/mikrotik")  # trocar o MikroTik: chave nova ainda não liberada
    assert c.get("/api/vpn").json()["pending"] is True
    assert c.get("/api/vpn/mikrotik/script").status_code == 409


def test_device_addr_maps_standard_lan(env):
    c, tmp = env
    os.makedirs(tmp / "vpn", exist_ok=True)
    json.dump({"n": 7}, open(tmp / "vpn" / "status.json", "w"))
    assert vpn.device_addr("192.168.88.101", 80) == ("10.67.7.101", 80)
    assert vpn.device_addr("10.66.0.2", 8002) == ("10.66.0.2", 8002)  # instalação manual continua igual


def test_driver_uses_vpn_address(env):
    c, tmp = env
    os.makedirs(tmp / "vpn", exist_ok=True)
    json.dump({"n": 3}, open(tmp / "vpn" / "status.json", "w"))
    from drivers.intelbras import IntelbrasDriver
    assert IntelbrasDriver({"ip": "192.168.88.105", "port": 80})._base() == "http://10.67.3.105:80"

"""Backend tests for new NX-ACCESS equipment/controllers refactor (iteration 6)."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://nx-access-demo.preview.emergentagent.com").rstrip("/")
ADMIN = {"email": "felipejferreira@gmail.com", "password": "NxAccess@2026"}


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=ADMIN, timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    tok = r.json().get("access_token") or r.json().get("token")
    if tok:
        s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


@pytest.fixture(scope="module")
def site_id(client):
    r = client.get(f"{BASE_URL}/api/structure/sites", timeout=10)
    assert r.status_code == 200
    arr = r.json()
    return arr[0]["id"] if arr else None


# ---------- /model-types ----------
def test_model_types(client):
    r = client.get(f"{BASE_URL}/api/equipment/model-types", timeout=10)
    assert r.status_code == 200
    data = r.json()
    for k in ("simulado", "beward_facial", "hikvision_facial", "controlid_facial", "ct300_2l"):
        assert k in data, f"missing model_type {k}"
    assert data["beward_facial"]["max"] == 1
    assert data["hikvision_facial"]["max"] == 1
    assert data["controlid_facial"]["max"] == 1
    assert data["ct300_2l"]["max"] == 2
    assert data["simulado"]["max"] == 8


# ---------- Simulado controller create + verify points ----------
def test_create_simulado_2pts_and_verify(client, site_id):
    body = {
        "name": "TEST_SIM_2", "model_type": "simulado", "ip": "10.0.0.11", "port": 80,
        "username": "admin", "password": "x", "site_id": site_id, "num_access_points": 2,
        "access_points": [{"description": "P1", "direction": "entrada"}, {"description": "P2", "direction": "saida"}],
    }
    r = client.post(f"{BASE_URL}/api/equipment/controllers", json=body, timeout=15)
    assert r.status_code in (200, 201), r.text
    cid = r.json()["id"]
    pts = client.get(f"{BASE_URL}/api/equipment/controllers/{cid}/access-points", timeout=10).json()
    assert len(pts) == 2
    assert {p["reader"] for p in pts} == {1, 2}
    assert pts[0]["controller_id"] == cid

    # Reduce to 1 -> second point soft-deleted
    body2 = {**body, "num_access_points": 1, "access_points": [{"description": "P1", "direction": "entrada"}]}
    r = client.put(f"{BASE_URL}/api/equipment/controllers/{cid}", json=body2, timeout=15)
    assert r.status_code == 200
    pts = client.get(f"{BASE_URL}/api/equipment/controllers/{cid}/access-points", timeout=10).json()
    assert len(pts) == 1
    # cleanup
    client.delete(f"{BASE_URL}/api/equipment/controllers/{cid}", timeout=10)
    # verify deletion cascades
    allp = client.get(f"{BASE_URL}/api/equipment/access-points/all", timeout=10).json()
    assert not any(p.get("controller_id") == cid for p in allp)


# ---------- CT300-2L pending driver test ----------
def test_ct300_pending_driver(client, site_id):
    body = {
        "name": "TEST_CT300", "model_type": "ct300_2l", "ip": "10.0.0.22", "port": 80,
        "username": "admin", "password": "x", "site_id": site_id, "num_access_points": 2,
    }
    r = client.post(f"{BASE_URL}/api/equipment/controllers", json=body, timeout=15)
    assert r.status_code in (200, 201), r.text
    doc = r.json()
    cid = doc["id"]
    assert doc["brand"] == "ct300"
    assert doc["num_access_points"] == 2
    assert doc["model"] == "CT300-2L"
    # Test endpoint should return ok=False with pending error message
    r = client.post(f"{BASE_URL}/api/equipment/controllers/{cid}/test", timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is False
    err = (data.get("status") or {}).get("error") or (data.get("info") or {}).get("error") or ""
    assert "ainda não implementado" in err.lower() or "ainda nao implementado" in err.lower() or "CT300" in err
    client.delete(f"{BASE_URL}/api/equipment/controllers/{cid}", timeout=10)


# ---------- Hikvision facial creates with 1 point fixed ----------
def test_hikvision_facial_1pt(client, site_id):
    body = {
        "name": "TEST_HIK", "model_type": "hikvision_facial", "ip": "10.0.0.33", "port": 80,
        "username": "admin", "password": "x", "site_id": site_id, "num_access_points": 5,  # should be clamped to 1
    }
    r = client.post(f"{BASE_URL}/api/equipment/controllers", json=body, timeout=15)
    assert r.status_code in (200, 201)
    doc = r.json()
    cid = doc["id"]
    assert doc["num_access_points"] == 1
    assert doc["brand"] == "hikvision"
    client.delete(f"{BASE_URL}/api/equipment/controllers/{cid}", timeout=10)


def test_cleanup_leftovers(client):
    r = client.get(f"{BASE_URL}/api/equipment/controllers?limit=200", timeout=10)
    for d in r.json().get("items", []):
        if d.get("name", "").startswith("TEST_"):
            client.delete(f"{BASE_URL}/api/equipment/controllers/{d['id']}", timeout=10)

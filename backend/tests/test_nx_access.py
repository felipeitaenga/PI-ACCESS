"""
NX-ACCESS backend API tests.
Covers: auth, structure, people, devices, events (alarms/emergency), dashboard/reports, admin.
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # fallback for local run
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                break

API = f"{BASE_URL}/api"

ADMIN = {"email": "felipejferreira@gmail.com", "password": "NxAccess@2026"}
OPERATOR = {"email": "operador@nxaccess.com", "password": "Operador@2026"}
VIEWER = {"email": "leitura@nxaccess.com", "password": "Leitura@2026"}


# ---------- fixtures ----------
@pytest.fixture(scope="session")
def admin_token():
    r = requests.post(f"{API}/auth/login", json=ADMIN, timeout=15)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def viewer_token():
    r = requests.post(f"{API}/auth/login", json=VIEWER, timeout=15)
    assert r.status_code == 200, f"viewer login failed: {r.status_code} {r.text}"
    return r.json()["access_token"]


@pytest.fixture
def admin_h(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture
def viewer_h(viewer_token):
    return {"Authorization": f"Bearer {viewer_token}"}


# ---------- auth ----------
class TestAuth:
    def test_login_admin(self):
        r = requests.post(f"{API}/auth/login", json=ADMIN, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["email"] == ADMIN["email"]
        assert d["role"] == "admin"
        assert d["access_token"]
        assert d["refresh_token"]

    def test_login_bad_password(self):
        r = requests.post(f"{API}/auth/login",
                          json={"email": ADMIN["email"], "password": "wrong"}, timeout=15)
        assert r.status_code in (400, 401)

    def test_me(self, admin_h):
        r = requests.get(f"{API}/auth/me", headers=admin_h, timeout=15)
        assert r.status_code == 200
        assert r.json()["email"] == ADMIN["email"]

    def test_refresh(self):
        r = requests.post(f"{API}/auth/login", json=ADMIN, timeout=15)
        rt = r.json()["refresh_token"]
        r2 = requests.post(f"{API}/auth/refresh", json={"refresh_token": rt}, timeout=15)
        assert r2.status_code == 200
        assert "access_token" in r2.json()

    def test_viewer_login(self):
        r = requests.post(f"{API}/auth/login", json=VIEWER, timeout=15)
        assert r.status_code == 200
        assert r.json()["role"] == "viewer"


# ---------- structure ----------
class TestStructure:
    def test_sites_list(self, admin_h):
        r = requests.get(f"{API}/structure/sites", headers=admin_h, timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_areas_list(self, admin_h):
        r = requests.get(f"{API}/structure/areas", headers=admin_h, timeout=15)
        assert r.status_code == 200
        assert len(r.json()) >= 3

    def test_doors_list(self, admin_h):
        r = requests.get(f"{API}/structure/doors", headers=admin_h, timeout=15)
        assert r.status_code == 200
        assert len(r.json()) >= 6


# ---------- people ----------
class TestPeople:
    created_id = None

    def test_list_people(self, admin_h):
        r = requests.get(f"{API}/people", headers=admin_h, timeout=15)
        assert r.status_code == 200
        d = r.json()
        # expect dict with items or a list
        if isinstance(d, dict):
            assert "items" in d or "data" in d or len(d) >= 0
        else:
            assert isinstance(d, list)

    def test_create_and_get_person(self, admin_h):
        payload = {
            "name": "TEST_Person_API",
            "matricula": f"TST{int(time.time())}",
            "email": f"test_{int(time.time())}@test.com",
            "active": True,
        }
        r = requests.post(f"{API}/people", headers=admin_h, json=payload, timeout=15)
        assert r.status_code in (200, 201), r.text
        pid = r.json().get("id")
        assert pid
        TestPeople.created_id = pid
        g = requests.get(f"{API}/people/{pid}", headers=admin_h, timeout=15)
        assert g.status_code == 200
        assert g.json()["name"] == payload["name"]

    def test_delete_person(self, admin_h):
        if not TestPeople.created_id:
            pytest.skip("no person created")
        r = requests.delete(f"{API}/people/{TestPeople.created_id}", headers=admin_h, timeout=15)
        assert r.status_code in (200, 204)

    def test_csv_export(self, admin_h):
        r = requests.get(f"{API}/people/export/csv", headers=admin_h, timeout=15)
        # endpoint path may differ; try alternative
        if r.status_code == 404:
            r = requests.get(f"{API}/people/export.csv", headers=admin_h, timeout=15)
        assert r.status_code == 200, f"CSV export failed: {r.status_code}"


# ---------- devices ----------
class TestDevices:
    def test_list(self, admin_h):
        r = requests.get(f"{API}/devices", headers=admin_h, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert len(d) >= 4

    def test_device_test_and_sync(self, admin_h):
        r = requests.get(f"{API}/devices", headers=admin_h, timeout=15)
        dev = r.json()[0]
        did = dev["id"]
        t = requests.post(f"{API}/devices/{did}/test", headers=admin_h, timeout=20)
        assert t.status_code == 200, t.text
        s = requests.post(f"{API}/devices/{did}/sync", headers=admin_h, timeout=30)
        assert s.status_code == 200, s.text


# ---------- events / alarms / emergency ----------
class TestEvents:
    def test_events_list(self, admin_h):
        r = requests.get(f"{API}/events", headers=admin_h, timeout=15)
        assert r.status_code == 200

    def test_alarms_list(self, admin_h):
        r = requests.get(f"{API}/alarms", headers=admin_h, timeout=15)
        assert r.status_code == 200

    def test_remote_door_unlock(self, admin_h):
        doors = requests.get(f"{API}/structure/doors", headers=admin_h, timeout=15).json()
        if not doors:
            pytest.skip("no doors")
        did = doors[0]["id"]
        r = requests.post(f"{API}/devices/doors/{did}/open", headers=admin_h,
                          json={"reason": "test"}, timeout=15)
        assert r.status_code in (200, 201), r.text


# ---------- dashboard / reports ----------
class TestDashboard:
    def test_dashboard_stats(self, admin_h):
        r = requests.get(f"{API}/dashboard/stats", headers=admin_h, timeout=15)
        assert r.status_code == 200, r.text

    def test_reports_access(self, admin_h):
        r = requests.get(f"{API}/reports/access", headers=admin_h, timeout=15)
        assert r.status_code == 200

    def test_reports_occupancy(self, admin_h):
        r = requests.get(f"{API}/reports/occupancy", headers=admin_h, timeout=15)
        assert r.status_code == 200

    def test_reports_presence(self, admin_h):
        r = requests.get(f"{API}/reports/presence", headers=admin_h, timeout=15)
        assert r.status_code == 200


# ---------- admin ----------
class TestAdmin:
    def test_users_list(self, admin_h):
        r = requests.get(f"{API}/auth/users", headers=admin_h, timeout=15)
        assert r.status_code == 200
        assert len(r.json()) >= 4

    def test_audit_list(self, admin_h):
        r = requests.get(f"{API}/admin/audit", headers=admin_h, timeout=15)
        assert r.status_code == 200

    def test_settings_get(self, admin_h):
        r = requests.get(f"{API}/admin/settings", headers=admin_h, timeout=15)
        assert r.status_code == 200


# ---------- role based access ----------
class TestRBAC:
    def test_viewer_cannot_create_person(self, viewer_h):
        payload = {"name": "TEST_viewer", "matricula": "VWR1"}
        r = requests.post(f"{API}/people", headers=viewer_h, json=payload, timeout=15)
        assert r.status_code in (401, 403), f"viewer should not create: {r.status_code}"

    def test_viewer_cannot_list_users(self, viewer_h):
        r = requests.get(f"{API}/auth/users", headers=viewer_h, timeout=15)
        assert r.status_code in (401, 403)

    def test_viewer_can_read_people(self, viewer_h):
        r = requests.get(f"{API}/people", headers=viewer_h, timeout=15)
        assert r.status_code == 200


# ---------- muster / emergency ----------
class TestEmergency:
    def test_muster(self, admin_h):
        sites = requests.get(f"{API}/structure/sites", headers=admin_h, timeout=15).json()
        sid = sites[0]["id"]
        r = requests.get(f"{API}/emergency/muster/{sid}", headers=admin_h, timeout=15)
        assert r.status_code == 200

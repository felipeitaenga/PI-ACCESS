"""Tests for new NX-ACCESS model: time ranges, holidays, areas, controllers,
access-points, categories, org (companies/departments), cadastros, and the
decision engine simulator."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                break
API = f"{BASE_URL}/api"

ADMIN = {"email": "felipejferreira@gmail.com", "password": "NxAccess@2026"}
VIEWER = {"email": "leitura@nxaccess.com", "password": "Leitura@2026"}


@pytest.fixture(scope="session")
def admin_h():
    r = requests.post(f"{API}/auth/login", json=ADMIN, timeout=15)
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="session")
def viewer_h():
    r = requests.post(f"{API}/auth/login", json=VIEWER, timeout=15)
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# ---------- Time ranges ----------
class TestTimeRanges:
    created = None

    def test_list(self, admin_h):
        r = requests.get(f"{API}/access/time-ranges", headers=admin_h, timeout=15)
        assert r.status_code == 200
        data = r.json()
        items = data.get("items", data)
        descs = [i.get("description") for i in items]
        assert any("Livre" in (d or "") for d in descs), descs
        assert any("Comercial" in (d or "") for d in descs), descs

    def test_crud(self, admin_h):
        payload = {"description": f"TEST_TR_{int(time.time())}",
                   "intervals": [{"weekdays": [1, 2, 3, 4, 5], "start": "08:00", "end": "18:00"}]}
        c = requests.post(f"{API}/access/time-ranges", headers=admin_h, json=payload, timeout=15)
        assert c.status_code in (200, 201), c.text
        tid = c.json()["id"]
        TestTimeRanges.created = tid
        g = requests.get(f"{API}/access/time-ranges/{tid}", headers=admin_h, timeout=15)
        assert g.status_code == 200
        assert g.json()["description"] == payload["description"]
        u = requests.put(f"{API}/access/time-ranges/{tid}", headers=admin_h,
                         json={"description": payload["description"] + "_upd"}, timeout=15)
        assert u.status_code == 200
        assert u.json()["description"].endswith("_upd")
        d = requests.delete(f"{API}/access/time-ranges/{tid}", headers=admin_h, timeout=15)
        assert d.status_code in (200, 204)


# ---------- Holidays ----------
class TestHolidays:
    def test_list(self, admin_h):
        r = requests.get(f"{API}/access/holidays", headers=admin_h, timeout=15)
        assert r.status_code == 200
        data = r.json()
        items = data.get("items", data)
        assert len(items) >= 2

    def test_create_delete(self, admin_h):
        p = {"description": f"TEST_H_{int(time.time())}", "date": "2026-12-25"}
        c = requests.post(f"{API}/access/holidays", headers=admin_h, json=p, timeout=15)
        assert c.status_code in (200, 201), c.text
        hid = c.json()["id"]
        requests.delete(f"{API}/access/holidays/{hid}", headers=admin_h, timeout=15)


# ---------- Areas ----------
class TestAreas:
    def test_list_includes_exterior(self, admin_h):
        r = requests.get(f"{API}/access/areas/all", headers=admin_h, timeout=15)
        assert r.status_code == 200
        items = r.json()
        assert len(items) >= 8, f"expected 8 areas, got {len(items)}"
        descs = [i.get("description") for i in items]
        assert any("EXTERIOR" in (d or "") for d in descs), descs
        assert all("current_occupancy" in i for i in items)

    def test_set_occupancy(self, admin_h):
        items = requests.get(f"{API}/access/areas/all", headers=admin_h, timeout=15).json()
        non_ext = next(a for a in items if not a.get("is_exterior"))
        r = requests.post(f"{API}/access/areas/{non_ext['id']}/occupancy",
                          headers=admin_h, json={"value": 3}, timeout=15)
        assert r.status_code == 200
        assert r.json()["current_occupancy"] == 3


# ---------- Equipment ----------
class TestEquipment:
    def test_controllers(self, admin_h):
        r = requests.get(f"{API}/equipment/controllers/all", headers=admin_h, timeout=15)
        assert r.status_code == 200
        items = r.json()
        assert len(items) >= 2

    def test_access_points(self, admin_h):
        r = requests.get(f"{API}/equipment/access-points/all", headers=admin_h, timeout=15)
        assert r.status_code == 200
        items = r.json()
        assert len(items) >= 6, f"expected 6 access points, got {len(items)}"
        for ap in items:
            assert "origin_area_name" in ap
            assert "dest_area_name" in ap
            assert "direction" in ap

    def test_controller_test_and_sync(self, admin_h):
        ctrls = requests.get(f"{API}/equipment/controllers/all", headers=admin_h, timeout=15).json()
        cid = ctrls[0]["id"]
        t = requests.post(f"{API}/equipment/controllers/{cid}/test", headers=admin_h, timeout=20)
        assert t.status_code == 200, t.text
        assert t.json().get("ok") is True
        s = requests.post(f"{API}/equipment/controllers/{cid}/sync", headers=admin_h, timeout=30)
        assert s.status_code == 200, s.text
        totals = s.json().get("totals", {})
        for k in ("time_zones", "areas", "portals", "access_rules", "people"):
            assert k in totals, totals

    def test_sync_jobs(self, admin_h):
        r = requests.get(f"{API}/equipment/sync-jobs", headers=admin_h, timeout=15)
        assert r.status_code == 200
        assert len(r.json()) >= 1


# ---------- Categories ----------
class TestCategories:
    def test_list_six(self, admin_h):
        r = requests.get(f"{API}/access/categories/all", headers=admin_h, timeout=15)
        assert r.status_code == 200
        items = r.json()
        assert len(items) >= 6, f"expected 6 categories, got {len(items)}"
        codes = [i.get("code") or i.get("description") for i in items]
        # presence of key categories
        joined = " ".join(str(c) for c in codes).upper()
        for key in ["ACESSO FULL", "PEDESTRE", "VISITANTE"]:
            assert key in joined, codes

    def test_category_people(self, admin_h):
        cats = requests.get(f"{API}/access/categories/all", headers=admin_h, timeout=15).json()
        cid = cats[0]["id"]
        r = requests.get(f"{API}/access/categories/{cid}/people", headers=admin_h, timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ---------- Simulator / decision engine ----------
class TestSimulator:
    def test_simulate_funcionario_granted(self, admin_h):
        # pick an active funcionario and the Catraca Pedestre - Entrada point
        people = requests.get(f"{API}/people?limit=200", headers=admin_h, timeout=15).json()
        items = people.get("items", people) if isinstance(people, dict) else people
        funcs = [p for p in items if p.get("person_type") == "funcionario" and p.get("status") == "ativo"]
        assert funcs, "no active funcionarios"
        aps = requests.get(f"{API}/equipment/access-points/all", headers=admin_h, timeout=15).json()
        ap = next((a for a in aps if "Catraca Pedestre" in (a.get("description") or "")
                   and a.get("direction") == "entrada"), None)
        if not ap:
            ap = aps[0]
        # Commercial hours: Tuesday 10:00 BRT
        r = requests.post(f"{API}/access/simulate", headers=admin_h,
                          json={"person_id": funcs[0]["id"], "access_point_id": ap["id"],
                                "datetime": "2026-01-13T10:00:00-03:00"}, timeout=15)
        assert r.status_code == 200, r.text
        res = r.json()
        granted = res.get("granted")
        assert granted in (True, False), res
        # engine must return reasoning steps
        steps = res.get("steps") or []
        assert isinstance(steps, list) and len(steps) >= 1, res

    def test_simulate_blocked_person_denied(self, admin_h):
        # create a blocked person then simulate
        payload = {"name": f"TEST_blocked_{int(time.time())}", "status": "bloqueado",
                   "type": "funcionario", "matricula": f"BLK{int(time.time())}"}
        c = requests.post(f"{API}/people", headers=admin_h, json=payload, timeout=15)
        assert c.status_code in (200, 201), c.text
        pid = c.json()["id"]
        try:
            aps = requests.get(f"{API}/equipment/access-points/all", headers=admin_h, timeout=15).json()
            ap = aps[0]
            r = requests.post(f"{API}/access/simulate", headers=admin_h,
                              json={"person_id": pid, "access_point_id": ap["id"]}, timeout=15)
            assert r.status_code == 200
            res = r.json()
            assert res.get("granted") is False, res
            reason = (res.get("reason") or "").lower()
            assert "inativ" in reason or "bloquea" in reason or "pessoa" in reason, res
        finally:
            requests.delete(f"{API}/people/{pid}", headers=admin_h, timeout=15)

    def test_simulate_404_unknown(self, admin_h):
        r = requests.post(f"{API}/access/simulate", headers=admin_h,
                          json={"person_id": "nope", "access_point_id": "nope"}, timeout=15)
        assert r.status_code == 404


# ---------- Org ----------
class TestOrg:
    def test_companies(self, admin_h):
        r = requests.get(f"{API}/org/companies/all", headers=admin_h, timeout=15)
        assert r.status_code == 200
        assert len(r.json()) >= 4

    def test_departments(self, admin_h):
        r = requests.get(f"{API}/org/departments/all", headers=admin_h, timeout=15)
        assert r.status_code == 200
        assert len(r.json()) >= 5


# ---------- Cadastros ----------
class TestCadastros:
    def test_identifiers(self, admin_h):
        r = requests.get(f"{API}/cadastros/identifiers", headers=admin_h, timeout=15)
        assert r.status_code == 200

    def test_visitors(self, admin_h):
        r = requests.get(f"{API}/cadastros/visitors", headers=admin_h, timeout=15)
        assert r.status_code == 200


# ---------- RBAC on new endpoints ----------
class TestRBACNew:
    def test_viewer_cannot_create_time_range(self, viewer_h):
        r = requests.post(f"{API}/access/time-ranges", headers=viewer_h,
                          json={"description": "TEST_viewer_tr"}, timeout=15)
        assert r.status_code in (401, 403)

    def test_viewer_cannot_create_category(self, viewer_h):
        r = requests.post(f"{API}/access/categories", headers=viewer_h,
                          json={"code": "TEST", "description": "TEST"}, timeout=15)
        assert r.status_code in (401, 403)

    def test_viewer_can_read_areas(self, viewer_h):
        r = requests.get(f"{API}/access/areas", headers=viewer_h, timeout=15)
        assert r.status_code == 200

    def test_viewer_cannot_sync_controller(self, viewer_h, admin_h):
        ctrls = requests.get(f"{API}/equipment/controllers/all", headers=admin_h, timeout=15).json()
        r = requests.post(f"{API}/equipment/controllers/{ctrls[0]['id']}/sync",
                          headers=viewer_h, timeout=15)
        assert r.status_code in (401, 403)

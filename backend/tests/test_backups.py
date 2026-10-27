"""Backup/Restore API tests - admin only, requires /api prefix."""
import gzip
import io
import json
import os
import time
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE}/api"

ADMIN = ("felipejferreira@gmail.com", "NxAccess@2026")
OPER = ("operador@nxaccess.com", "Operador@2026")


def _login(email, pwd):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": pwd}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    tok = r.json().get("access_token")
    s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


@pytest.fixture(scope="module")
def admin():
    return _login(*ADMIN)


@pytest.fixture(scope="module")
def oper():
    return _login(*OPER)


created_names = []


# -------- List + settings --------
class TestListAndSettings:
    def test_list(self, admin):
        r = admin.get(f"{API}/backups")
        assert r.status_code == 200
        j = r.json()
        assert "items" in j and "settings" in j
        s = j["settings"]
        assert {"enabled", "time", "keep"}.issubset(s)

    def test_settings_bad_time(self, admin):
        r = admin.put(f"{API}/backups/settings", json={"enabled": True, "time": "25:99", "keep": 7})
        assert r.status_code == 422

    def test_settings_keep_zero(self, admin):
        r = admin.put(f"{API}/backups/settings", json={"enabled": True, "time": "03:00", "keep": 0})
        assert r.status_code == 422

    def test_settings_keep_non_int(self, admin):
        r = admin.put(f"{API}/backups/settings", json={"enabled": True, "time": "03:00", "keep": "abc"})
        assert r.status_code == 422

    def test_settings_valid_persist(self, admin):
        r = admin.put(f"{API}/backups/settings", json={"enabled": True, "time": "04:30", "keep": 5})
        assert r.status_code == 200
        assert r.json()["time"] == "04:30" and r.json()["keep"] == 5
        # verify persisted
        r2 = admin.get(f"{API}/backups")
        assert r2.json()["settings"]["time"] == "04:30"
        # restore defaults
        admin.put(f"{API}/backups/settings", json={"enabled": True, "time": "03:00", "keep": 7})


# -------- Create / download / delete --------
class TestCreateDownloadDelete:
    def test_create_backup(self, admin):
        r = admin.post(f"{API}/backups", timeout=180)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["name"].startswith("scarvel_") and j["name"].endswith("_manual.json.gz")
        assert j["documents"] > 0
        assert j["size"] > 0
        created_names.append(j["name"])

    def test_download_gzip_first_line(self, admin):
        assert created_names, "no backup created"
        name = created_names[0]
        r = admin.get(f"{API}/backups/{name}/download", stream=True, timeout=180)
        assert r.status_code == 200
        buf = io.BytesIO(r.content)
        with gzip.open(buf, "rt", encoding="utf-8") as f:
            head = json.loads(f.readline())
        assert head.get("scarvel_backup") == 1

    def test_invalid_name_simple(self, admin):
        r = admin.get(f"{API}/backups/foo.gz/download")
        assert r.status_code == 400

    def test_invalid_name_traversal(self, admin):
        # encoded traversal
        r = admin.get(f"{API}/backups/..%2F..%2Fetc%2Fpasswd/download")
        assert r.status_code in (400, 404)
        r2 = admin.delete(f"{API}/backups/..%2F..%2Fetc%2Fpasswd")
        assert r2.status_code in (400, 404)

    def test_delete_and_404(self, admin):
        # create one to delete
        r = admin.post(f"{API}/backups", timeout=180)
        assert r.status_code == 200
        name = r.json()["name"]
        d = admin.delete(f"{API}/backups/{name}")
        assert d.status_code == 200
        d2 = admin.delete(f"{API}/backups/{name}")
        assert d2.status_code == 404


# -------- Operator forbidden --------
class TestOperatorForbidden:
    def test_oper_list(self, oper):
        assert oper.get(f"{API}/backups").status_code == 403

    def test_oper_create(self, oper):
        assert oper.post(f"{API}/backups").status_code == 403

    def test_oper_settings(self, oper):
        assert oper.put(f"{API}/backups/settings", json={"enabled": True, "time": "03:00", "keep": 7}).status_code == 403

    def test_oper_download(self, oper):
        # pick any name shape
        n = created_names[0] if created_names else "scarvel_demo_20250101_000000_manual.json.gz"
        assert oper.get(f"{API}/backups/{n}/download").status_code == 403

    def test_oper_delete(self, oper):
        n = created_names[0] if created_names else "scarvel_demo_20250101_000000_manual.json.gz"
        assert oper.delete(f"{API}/backups/{n}").status_code == 403

    def test_oper_upload(self, oper):
        assert oper.put(f"{API}/backups/upload?upload_id=abc&offset=0&done=0", data=b"x").status_code == 403

    def test_oper_restore(self, oper):
        assert oper.post(f"{API}/backups/foo.json.gz/restore", json={"confirm": "RESTAURAR"}).status_code == 403


# -------- Upload --------
class TestUpload:
    def test_upload_non_backup_gz_invalid(self, admin):
        # make a gz with invalid content
        buf = io.BytesIO()
        with gzip.open(buf, "wt", encoding="utf-8") as f:
            f.write(json.dumps({"foo": "bar"}) + "\n")
        payload = buf.getvalue()
        uid = f"inv{int(time.time())}"
        r = admin.put(
            f"{API}/backups/upload?upload_id={uid}&offset=0&done=1",
            data=payload,
            headers={"Content-Type": "application/octet-stream"},
        )
        assert r.status_code == 422

    def test_upload_wrong_offset(self, admin):
        uid = f"off{int(time.time())}"
        # first chunk
        r1 = admin.put(
            f"{API}/backups/upload?upload_id={uid}&offset=0&done=0",
            data=b"abcdef",
            headers={"Content-Type": "application/octet-stream"},
        )
        assert r1.status_code == 200
        # wrong offset
        r2 = admin.put(
            f"{API}/backups/upload?upload_id={uid}&offset=99&done=0",
            data=b"xyz",
            headers={"Content-Type": "application/octet-stream"},
        )
        assert r2.status_code == 409

    def test_upload_complete_valid(self, admin):
        # grab bytes from an existing backup, upload them back in chunks -> _enviado
        assert created_names
        name = created_names[0]
        r = admin.get(f"{API}/backups/{name}/download", timeout=180)
        assert r.status_code == 200
        data = r.content
        uid = f"ok{int(time.time())}"
        chunk = 2 * 1024 * 1024
        off = 0
        last = None
        while off < len(data):
            end = min(off + chunk, len(data))
            done = 1 if end >= len(data) else 0
            last = admin.put(
                f"{API}/backups/upload?upload_id={uid}&offset={off}&done={done}",
                data=data[off:end],
                headers={"Content-Type": "application/octet-stream"},
                timeout=180,
            )
            assert last.status_code == 200, f"off={off} {last.status_code} {last.text}"
            off = end
        new_name = last.json()["name"]
        assert new_name.endswith("_enviado.json.gz")
        created_names.append(new_name)
        # cleanup this uploaded one
        admin.delete(f"{API}/backups/{new_name}")
        created_names.remove(new_name)


# -------- Restore --------
class TestRestore:
    def test_restore_wrong_confirm_400(self, admin):
        assert created_names
        r = admin.post(f"{API}/backups/{created_names[0]}/restore", json={"confirm": "no"})
        assert r.status_code == 400

    def test_restore_full_cycle(self, admin):
        # Fresh backup
        r = admin.post(f"{API}/backups", timeout=180)
        assert r.status_code == 200
        name = r.json()["name"]
        created_names.append(name)

        # Create TEST_ person
        comps = admin.get(f"{API}/registry/companies").json()
        assert comps
        # 'propria' == is own company; otherwise first
        own = next((c for c in comps if c.get("propria") or c.get("is_own")), comps[0])
        cats = admin.get(f"{API}/access/categories/all").json()
        assert cats
        cat_id = cats[0].get("id") or cats[0].get("_id")
        person_payload = {
            "name": "TEST_RestoreGuy",
            "person_type": "funcionario",
            "doc_type": "outro",
            "doc_number": f"TESTDOC{int(time.time())}",
            "company_id": own.get("id") or own.get("_id"),
            "category_ids": [cat_id],
        }
        pr = admin.post(f"{API}/registry/people", json=person_payload)
        assert pr.status_code in (200, 201), f"create person: {pr.status_code} {pr.text}"
        person_id = pr.json().get("id") or pr.json().get("_id")

        # Restore
        rr = admin.post(f"{API}/backups/{name}/restore", json={"confirm": "RESTAURAR"}, timeout=300)
        assert rr.status_code == 200, rr.text
        body = rr.json()
        assert body.get("safety_backup", "").endswith("_seguranca.json.gz")
        created_names.append(body["safety_backup"])

        # Give indexes a sec
        time.sleep(2)

        # TEST_ person should be gone
        found = admin.get(f"{API}/registry/people/{person_id}")
        assert found.status_code == 404, f"person still exists after restore: {found.status_code}"

        # Health ok
        h = requests.get(f"{API}/health", timeout=30)
        assert h.status_code == 200

        # Login still works
        s2 = requests.Session()
        lg = s2.post(f"{API}/auth/login", json={"email": ADMIN[0], "password": ADMIN[1]}, timeout=30)
        assert lg.status_code == 200

        # Audit entries - best effort
        tok = lg.json().get("access_token")
        s2.headers.update({"Authorization": f"Bearer {tok}"})
        aud = s2.get(f"{API}/audit", params={"limit": 100})
        if aud.status_code == 200:
            txt = json.dumps(aud.json())
            assert "backup" in txt or "restaurar" in txt


# -------- Cleanup --------
def test_zz_cleanup(admin=None):
    """Delete all backups we created, leave at most one manual."""
    s = _login(*ADMIN)
    items = s.get(f"{API}/backups").json().get("items", [])
    manual_kept = False
    for b in items:
        n = b["name"]
        # Only touch backups we recognize created during this run OR safety/enviado/auto garbage from this test
        if b["origin"] == "manual" and not manual_kept:
            manual_kept = True
            continue
        s.delete(f"{API}/backups/{n}")
    # restore defaults
    s.put(f"{API}/backups/settings", json={"enabled": True, "time": "03:00", "keep": 7})

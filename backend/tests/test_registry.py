"""Registry & Visitors refactor backend tests (iteration_3)."""
import os
import base64
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://nx-access-demo.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


# ----------------- Fixtures -----------------
@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": "felipejferreira@gmail.com", "password": "NxAccess@2026"})
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    token = r.json().get("access_token")
    assert token
    s.headers.update({"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def companies(session):
    r = session.get(f"{API}/registry/companies")
    assert r.status_code == 200
    return r.json()


# ----------------- Companies -----------------
class TestCompanies:
    def test_six_companies_with_stats_and_alerts(self, companies):
        assert len(companies) >= 6, f"expected 6 companies, got {len(companies)}"
        for c in companies:
            assert "stats" in c and {"total", "active", "blocked", "present"}.issubset(c["stats"])
            assert "alerts" in c

    def test_alfa_has_blocked_vencido(self, companies):
        alfa = next((c for c in companies if "Alfa" in c["name"]), None)
        assert alfa is not None
        assert alfa["stats"]["blocked"] >= 1, f"Prestadora Alfa should have >=1 blocked (vencido): {alfa['stats']}"

    def test_gama_contract_alert(self, companies):
        gama = next((c for c in companies if "Gama" in c["name"]), None)
        assert gama is not None
        assert any("7 dias" in a or "vencido" in a.lower() for a in gama["alerts"]), f"Gama alerts: {gama['alerts']}"


class TestVisitorCompanies:
    def test_four_origin_companies_three_present(self, session):
        r = session.get(f"{API}/registry/visitor-companies")
        assert r.status_code == 200
        d = r.json()
        assert len(d["companies"]) >= 4, d
        assert d["present"] == 3, f"expected 3 present, got {d['present']}"


# ----------------- People listing + filters -----------------
class TestPeopleListing:
    def test_list_by_company_with_stats(self, session, companies):
        own = next(c for c in companies if c["type"] == "propria")
        r = session.get(f"{API}/registry/people", params={"company_id": own["id"], "limit": 50})
        assert r.status_code == 200
        d = r.json()
        assert d["stats"] is not None
        assert d["total"] >= 30
        assert isinstance(d["items"], list)
        assert "departments" in d
        for p in d["items"][:3]:
            assert "cred_types" in p
            assert "present" in p

    def test_filter_status_present(self, session, companies):
        own = next(c for c in companies if c["type"] == "propria")
        r = session.get(f"{API}/registry/people", params={"company_id": own["id"], "present": "true"})
        assert r.status_code == 200
        for p in r.json()["items"]:
            assert p["present"] is True
            assert p["status"] == "ativo"

    def test_pagination(self, session):
        r1 = session.get(f"{API}/registry/people", params={"limit": 5, "skip": 0})
        r2 = session.get(f"{API}/registry/people", params={"limit": 5, "skip": 5})
        assert r1.status_code == r2.status_code == 200
        a = {x["id"] for x in r1.json()["items"]}
        b = {x["id"] for x in r2.json()["items"]}
        assert not (a & b), "pages should be disjoint"


# ----------------- Global search -----------------
class TestSearch:
    def test_search_by_matricula(self, session):
        r = session.get(f"{API}/registry/search", params={"q": "F1001"})
        assert r.status_code == 200
        res = r.json()
        assert any("F1001" in (x.get("document") or "") or x.get("match") for x in res), res

    def test_search_by_name(self, session, session_people):
        p = session_people[0]
        first = p["name"].split()[0]
        r = session.get(f"{API}/registry/search", params={"q": first})
        assert r.status_code == 200
        assert len(r.json()) >= 1

    def test_search_by_cpf_digits(self, session, session_people):
        p = session_people[0]
        dig = "".join(ch for ch in p["cpf"] if ch.isdigit())[:6]
        r = session.get(f"{API}/registry/search", params={"q": dig})
        assert r.status_code == 200
        assert any(x["id"] == p["id"] for x in r.json()), f"CPF search didn't find person {p['id']}"

    def test_search_too_short(self, session):
        r = session.get(f"{API}/registry/search", params={"q": "a"})
        assert r.json() == []


@pytest.fixture(scope="module")
def session_people(session):
    r = session.get(f"{API}/registry/people", params={"limit": 50})
    return r.json()["items"]


# ----------------- Create/Update/Delete -----------------
class TestPersonCRUD:
    created_ids = []

    def test_create_invalid_cpf_422(self, session, companies):
        own = next(c for c in companies if c["type"] == "propria")
        cats = session.get(f"{API}/access/categories/all").json()
        cat_id = cats[0]["id"] if cats else None
        body = {"person_type": "funcionario", "name": "TEST_Invalid", "cpf": "11111111111",
                "company_id": own["id"], "category_ids": [cat_id], "matricula": "T9000"}
        r = session.post(f"{API}/registry/people", json=body)
        assert r.status_code == 422
        assert "fields" in r.json()["detail"]
        assert "cpf" in r.json()["detail"]["fields"]

    def test_create_missing_matricula_422(self, session, companies):
        own = next(c for c in companies if c["type"] == "propria")
        cats = session.get(f"{API}/access/categories/all").json()
        body = {"person_type": "funcionario", "name": "TEST_NoMat", "cpf": _gen_cpf(),
                "company_id": own["id"], "category_ids": [cats[0]["id"]]}
        r = session.post(f"{API}/registry/people", json=body)
        assert r.status_code == 422
        assert "matricula" in r.json()["detail"]["fields"]

    def test_create_terceiro_missing_valid_dates(self, session, companies):
        alfa = next(c for c in companies if "Alfa" in c["name"])
        cats = session.get(f"{API}/access/categories/all").json()
        body = {"person_type": "terceiro", "name": "TEST_T", "cpf": _gen_cpf(),
                "company_id": alfa["id"], "category_ids": [cats[0]["id"]]}
        r = session.post(f"{API}/registry/people", json=body)
        assert r.status_code == 422
        f = r.json()["detail"]["fields"]
        assert "valid_from" in f and "valid_until" in f

    def test_create_success_and_sync(self, session, companies):
        own = next(c for c in companies if c["type"] == "propria")
        cats = session.get(f"{API}/access/categories/all").json()
        body = {"person_type": "funcionario", "name": "TEST_Alice Silva", "cpf": _gen_cpf(),
                "company_id": own["id"], "category_ids": [cats[0]["id"]], "matricula": "T9001",
                "department": "TI", "email": "alice@test.com"}
        r = session.post(f"{API}/registry/people", json=body)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["person"]["name"].startswith("TEST_")
        assert d["person"]["cpf"].count(".") == 2
        assert isinstance(d["sync"], list) and len(d["sync"]) >= 1
        assert all(s["status"] == "ok" for s in d["sync"]), d["sync"]
        TestPersonCRUD.created_ids.append(d["person"]["id"])

    def test_duplicate_cpf(self, session, companies):
        pid = TestPersonCRUD.created_ids[0]
        p = session.get(f"{API}/registry/people/{pid}").json()
        own = next(c for c in companies if c["type"] == "propria")
        cats = session.get(f"{API}/access/categories/all").json()
        body = {"person_type": "funcionario", "name": "TEST_Dup", "cpf": p["cpf"],
                "company_id": own["id"], "category_ids": [cats[0]["id"]], "matricula": "T9099"}
        r = session.post(f"{API}/registry/people", json=body)
        assert r.status_code == 422
        assert "cpf" in r.json()["detail"]["fields"]

    def test_update_person(self, session):
        pid = TestPersonCRUD.created_ids[0]
        p = session.get(f"{API}/registry/people/{pid}").json()
        body = {**p, "notes": "TEST_updated", "identifiers": [], "vehicles": [], "documents": []}
        for k in ("history", "current_area_name", "present"):
            body.pop(k, None)
        r = session.put(f"{API}/registry/people/{pid}", json=body)
        assert r.status_code == 200, r.text
        g = session.get(f"{API}/registry/people/{pid}").json()
        assert g["notes"] == "TEST_updated"

    def test_identifiers_vehicles_documents_saved(self, session, companies):
        own = next(c for c in companies if c["type"] == "propria")
        cats = session.get(f"{API}/access/categories/all").json()
        card_val = str(int(time.time() * 1000))[-9:]
        body = {"person_type": "funcionario", "name": "TEST_WithCreds", "cpf": _gen_cpf(),
                "company_id": own["id"], "category_ids": [cats[0]["id"]], "matricula": "T9002",
                "identifiers": [{"type": "cartao", "value": card_val, "format": "Wiegand 26"},
                                {"type": "pin", "value": "4321"}],
                "vehicles": [{"plate": "abc1d23", "model": "Fiat", "color": "Azul"}],
                "documents": [{"type": "ASO", "valid_until": "2026-12-31"}]}
        r = session.post(f"{API}/registry/people", json=body)
        assert r.status_code == 200, r.text
        pid = r.json()["person"]["id"]
        TestPersonCRUD.created_ids.append(pid)
        g = session.get(f"{API}/registry/people/{pid}").json()
        cart = [i for i in g["identifiers"] if i["type"] == "cartao"][0]
        assert cart["value"] == card_val
        assert cart["hex"]
        assert any(v["plate"] == "ABC1D23" for v in g["vehicles"])
        assert g["documents"][0]["type"] == "ASO"

    def test_duplicate_card(self, session, companies):
        own = next(c for c in companies if c["type"] == "propria")
        cats = session.get(f"{API}/access/categories/all").json()
        # Use card value from the previous test (TestPersonCRUD.created_ids[1])
        pid = TestPersonCRUD.created_ids[1]
        existing = session.get(f"{API}/registry/people/{pid}").json()
        card_val = [i for i in existing["identifiers"] if i["type"] == "cartao"][0]["value"]
        body = {"person_type": "funcionario", "name": "TEST_DupCard", "cpf": _gen_cpf(),
                "company_id": own["id"], "category_ids": [cats[0]["id"]], "matricula": "T9003",
                "identifiers": [{"type": "cartao", "value": card_val}]}
        r = session.post(f"{API}/registry/people", json=body)
        assert r.status_code == 422
        f = r.json()["detail"]["fields"]
        assert any(k.startswith("identifiers.") for k in f), f

    def test_terceiro_expired_doc_becomes_vencido(self, session, companies):
        alfa = next(c for c in companies if "Alfa" in c["name"])
        cats = session.get(f"{API}/access/categories/all").json()
        body = {"person_type": "terceiro", "name": "TEST_ExpiredDoc", "cpf": _gen_cpf(),
                "company_id": alfa["id"], "category_ids": [cats[0]["id"]],
                "valid_from": "2024-01-01", "valid_until": "2027-01-01",
                "documents": [{"type": "ASO", "valid_until": "2024-01-01"}]}
        r = session.post(f"{API}/registry/people", json=body)
        assert r.status_code == 200, r.text
        pid = r.json()["person"]["id"]
        TestPersonCRUD.created_ids.append(pid)
        g = session.get(f"{API}/registry/people/{pid}").json()
        assert g["status"] == "vencido", f"expected vencido, got {g['status']} reason={g.get('status_reason')}"

    def test_delete_logical(self, session):
        pid = TestPersonCRUD.created_ids[0]
        r = session.delete(f"{API}/registry/people/{pid}")
        assert r.status_code == 200
        g = session.get(f"{API}/registry/people/{pid}").json()
        assert g.get("deleted") is True or g.get("status") == "inativo"


# ----------------- Bulk -----------------
class TestBulk:
    def test_bulk_block_unblock(self, session):
        ids = [i for i in TestPersonCRUD.created_ids[1:3] if i]
        assert ids
        r = session.post(f"{API}/registry/people/bulk", json={"ids": ids, "action": "block", "reason": "TEST"})
        assert r.status_code == 200 and r.json()["affected"] == len(ids)
        for pid in ids:
            assert session.get(f"{API}/registry/people/{pid}").json()["status"] == "bloqueado"
        r = session.post(f"{API}/registry/people/bulk", json={"ids": ids, "action": "unblock"})
        assert r.status_code == 200

    def test_bulk_sync(self, session):
        ids = [i for i in TestPersonCRUD.created_ids[1:3] if i]
        r = session.post(f"{API}/registry/people/bulk", json={"ids": ids, "action": "sync"})
        assert r.status_code == 200
        assert r.json()["synced"] == len(ids)

    def test_bulk_renew(self, session):
        ids = [i for i in TestPersonCRUD.created_ids[1:3] if i]
        r = session.post(f"{API}/registry/people/bulk", json={"ids": ids, "action": "renew",
                                                               "valid_until": "2027-06-30"})
        assert r.status_code == 200

    def test_bulk_set_category(self, session):
        ids = [i for i in TestPersonCRUD.created_ids[1:3] if i]
        cats = session.get(f"{API}/access/categories/all").json()
        r = session.post(f"{API}/registry/people/bulk",
                         json={"ids": ids, "action": "set_category", "category_ids": [cats[0]["id"]]})
        assert r.status_code == 200


# ----------------- Photo check -----------------
class TestPhoto:
    def test_blank_image_no_face(self, session):
        from PIL import Image
        import io as _io
        im = Image.new("RGB", (300, 400), "white")
        buf = _io.BytesIO(); im.save(buf, "JPEG")
        b64 = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
        r = session.post(f"{API}/registry/photo/check", json={"image": b64})
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is False
        assert any("rosto" in i.lower() for i in d["issues"]), d

    def test_real_face_image(self, session):
        try:
            img = requests.get("https://i.pravatar.cc/400?img=12", timeout=10).content
        except Exception:
            pytest.skip("pravatar unreachable")
        b64 = "data:image/jpeg;base64," + base64.b64encode(img).decode()
        r = session.post(f"{API}/registry/photo/check", json={"image": b64})
        assert r.status_code == 200
        d = r.json()
        # Expect at least a face detected (ok may still be False due to centering)
        assert d["metrics"].get("faces", 0) >= 1, d


# ----------------- Visitors -----------------
class TestVisitors:
    created_visit_ids = []

    def test_lookup_not_found(self, session):
        r = session.get(f"{API}/registry/visitors/lookup", params={"document": "ZZZZZ999"})
        assert r.status_code == 200 and r.json()["found"] is False

    def test_create_visit_and_checkin(self, session):
        hosts = session.get(f"{API}/registry/people", params={"status": "ativo", "limit": 5}).json()["items"]
        host = next(p for p in hosts if p["person_type"] == "funcionario")
        body = {
            "visitor": {"name": "TEST_Visitor One", "document": f"TEST_DOC_{int(time.time())}",
                        "origin_company": "Acme Consultoria"},
            "visit": {"host_id": host["id"], "reason": "TEST",
                      "expected_start": "2026-06-01T09:00", "expected_end": "2026-06-01T18:00"},
            "checkin": True,
        }
        r = session.post(f"{API}/registry/visits", json=body)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["visit"]["status"] == "presente"
        TestVisitors.created_visit_ids.append(d["visit"]["id"])

    def test_reuse_existing_visitor(self, session):
        hosts = session.get(f"{API}/registry/people", params={"status": "ativo", "limit": 5}).json()["items"]
        host = next(p for p in hosts if p["person_type"] == "funcionario")
        doc = f"TEST_REUSE_{int(time.time())}"
        body = {"visitor": {"name": "TEST_Reuse", "document": doc, "origin_company": "Acme Consultoria"},
                "visit": {"host_id": host["id"], "expected_start": "2026-06-01T09:00",
                          "expected_end": "2026-06-01T18:00"}}
        r1 = session.post(f"{API}/registry/visits", json=body)
        assert r1.status_code == 200
        vid1 = r1.json()["visitor"]["id"]
        body["visitor"]["name"] = "TEST_Reuse2"  # should still reuse
        r2 = session.post(f"{API}/registry/visits", json=body)
        assert r2.status_code == 200
        assert r2.json()["visitor"]["id"] == vid1
        TestVisitors.created_visit_ids.append(r2.json()["visit"]["id"])

    def test_blacklisted_409(self, session):
        # find blacklisted visitor from seed
        vs = session.get(f"{API}/registry/visitors").json()["items"]
        hosts = session.get(f"{API}/registry/people", params={"status": "ativo", "limit": 5}).json()["items"]
        host = next(p for p in hosts if p["person_type"] == "funcionario")
        # Fetch each one to find blacklisted (list endpoint may not include flag)
        black = None
        for v in vs:
            full = session.get(f"{API}/registry/visitors/{v['id']}").json()
            if full.get("blacklist"):
                black = full
                break
        assert black, "no blacklisted visitor in seed"
        body = {"visitor": {"document": black["document"], "name": black["name"],
                            "origin_company": black.get("origin_company", "")},
                "visit": {"host_id": host["id"], "expected_start": "2026-06-01T09:00",
                          "expected_end": "2026-06-01T18:00"}}
        r = session.post(f"{API}/registry/visits", json=body)
        assert r.status_code == 409, f"expected 409 blacklist, got {r.status_code}"

    def test_checkout(self, session):
        if not TestVisitors.created_visit_ids:
            pytest.skip("no visit created")
        vid = TestVisitors.created_visit_ids[0]
        r = session.post(f"{API}/registry/visits/{vid}/checkout")
        assert r.status_code == 200

    def test_present_list(self, session):
        r = session.get(f"{API}/registry/visits/present")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ----------------- Permissions-Policy header -----------------
class TestHeaders:
    def test_permissions_policy_header(self, session):
        r = session.get(f"{API}/health")
        assert r.headers.get("Permissions-Policy") == "camera=(self)"


# ----------------- helper -----------------
def _gen_cpf():
    import random
    n = [random.randint(0, 9) for _ in range(9)]
    for i in (9, 10):
        s = sum(n[k] * ((i + 1) - k) for k in range(i))
        n.append((s * 10 % 11) % 10)
    d = "".join(map(str, n))
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"


# ----------------- Cleanup -----------------
@pytest.fixture(scope="module", autouse=True)
def _cleanup(session):
    yield
    for pid in TestPersonCRUD.created_ids:
        try:
            session.delete(f"{API}/registry/people/{pid}")
        except Exception:
            pass

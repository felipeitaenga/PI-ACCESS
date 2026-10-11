"""Tests for GET /api/visits/visitor-search and /api/visits/visitor/{id}/prefill."""
import os
import re
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://nx-access-demo.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "felipejferreira@gmail.com"
ADMIN_PASS = "NxAccess@2026"


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS})
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    tok = r.json().get("access_token") or r.json().get("token")
    if tok:
        s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


@pytest.fixture(scope="module")
def created(client):
    """Create a TEST_ visitor via a visit so prefill has a last_visit."""
    # pick a visit type and a host (any active company+person who can authorize)
    vt = client.get(f"{BASE_URL}/api/visits/types?active=true").json()
    assert vt
    visit_type_id = vt[0]["id"]
    # Find a host company+person
    comps = client.get(f"{BASE_URL}/api/registry/companies?limit=50").json()
    host_company_id, host_person_id = None, None
    for c in (comps.get("items") if isinstance(comps, dict) else comps):
        pl = client.get(f"{BASE_URL}/api/registry/people?status=ativo&authorize=true&limit=5&company_id={c['id']}").json()
        items = pl.get("items", pl) if isinstance(pl, dict) else pl
        if items:
            host_company_id = c["id"]; host_person_id = items[0]["id"]; break
    assert host_person_id, "no host found"
    payload = {
        "visit_type_id": visit_type_id,
        "start_at": "2026-01-15T12:00:00Z",
        "end_at": "2026-01-15T18:00:00Z",
        "end_at_manual": False,
        "host_company_id": host_company_id,
        "host_person_id": host_person_id,
        "name": "TEST_SuggestVisitor João",
        "doc_type": "cpf",
        "doc_number": "529.982.247-25",  # valid CPF
        "visitor_company": "TEST_Acme Ltda",
        "identifier": {"type": "cartao", "value": "7777"},
        "plate": "", "notes": "TEST notes do caso", "photo": "",
    }
    r = client.post(f"{BASE_URL}/api/visits", json=payload)
    assert r.status_code == 200, r.text
    data = r.json()
    visit_id = data["visit"]["id"]
    visitor_id = data["visit"]["visitor_id"]
    yield {"visitor_id": visitor_id, "visit_id": visit_id, "visit_type_id": visit_type_id,
           "host_company_id": host_company_id, "host_person_id": host_person_id}
    # teardown — end visit then soft-delete visitor
    try:
        client.post(f"{BASE_URL}/api/visits/{visit_id}/end")
    except Exception:
        pass


class TestVisitorSearch:
    def test_short_query_returns_empty(self, client):
        r = client.get(f"{BASE_URL}/api/visits/visitor-search?q=ab")
        assert r.status_code == 200
        assert r.json() == []

    def test_by_name(self, client, created):
        r = client.get(f"{BASE_URL}/api/visits/visitor-search?q=TEST_Suggest")
        assert r.status_code == 200
        items = r.json()
        assert any(v["id"] == created["visitor_id"] for v in items)
        v = next(v for v in items if v["id"] == created["visitor_id"])
        assert v["name"].startswith("TEST_Suggest")
        assert v.get("doc_type")  # legacy fill ensured
        assert v.get("doc_number")

    def test_by_doc_digits(self, client, created):
        # CPF 529.982.247-25 → digits 52998224725
        r = client.get(f"{BASE_URL}/api/visits/visitor-search?q=52998224725")
        assert r.status_code == 200
        items = r.json()
        assert any(v["id"] == created["visitor_id"] for v in items)

    def test_limit_8(self, client):
        r = client.get(f"{BASE_URL}/api/visits/visitor-search?q=aaa")
        assert r.status_code == 200
        assert len(r.json()) <= 8


class TestPrefill:
    def test_unknown_returns_404(self, client):
        r = client.get(f"{BASE_URL}/api/visits/visitor/does-not-exist-xyz/prefill")
        assert r.status_code == 404

    def test_prefill_returns_visitor_and_last_visit(self, client, created):
        r = client.get(f"{BASE_URL}/api/visits/visitor/{created['visitor_id']}/prefill")
        assert r.status_code == 200, r.text
        data = r.json()
        v = data["visitor"]
        assert v["id"] == created["visitor_id"]
        assert v["name"].startswith("TEST_Suggest")
        assert v["doc_type"] == "cpf"
        assert re.sub(r"\D", "", v["doc_number"]) == "52998224725"
        assert v["origin_company"] == "TEST_Acme Ltda"
        lv = data["last_visit"]
        assert lv is not None
        assert lv["visit_type_id"] == created["visit_type_id"]
        assert lv["host_company_id"] == created["host_company_id"]
        assert lv["host_person_id"] == created["host_person_id"]
        assert lv["host_name"]
        assert lv["id_type"] == "cartao"
        assert lv["id_value"] == "7777"
        assert lv["notes"] == "TEST notes do caso"

    def test_legacy_seed_bernardo(self, client):
        # Seed visitor Bernardo Araújo (per request context)
        r = client.get(f"{BASE_URL}/api/visits/visitor-search?q=Bern")
        assert r.status_code == 200
        items = r.json()
        if not items:
            pytest.skip("no Bernardo seed in this environment")
        b = items[0]
        # legacy may have doc_type filled or inferred as cpf when cpf_digits present
        assert b.get("doc_number")
        r2 = client.get(f"{BASE_URL}/api/visits/visitor/{b['id']}/prefill")
        assert r2.status_code == 200
        d = r2.json()
        assert d["visitor"]["id"] == b["id"]
        assert d["visitor"]["doc_type"] in ("cpf", "rg", "passaporte", "outro")

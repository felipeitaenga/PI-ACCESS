"""Tests for registry refactor: doc_type/doc_number, matricula optional,
can_authorize_visits and ?authorize=true filter, backward compat with cpf."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
ADMIN = {"email": "felipejferreira@gmail.com", "password": "NxAccess@2026"}

CREATED = []


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=ADMIN)
    assert r.status_code == 200, r.text
    s.headers.update({"Authorization": f"Bearer {r.json()['access_token']}",
                      "Content-Type": "application/json"})
    yield s
    # cleanup
    for pid in CREATED:
        try:
            s.delete(f"{API}/registry/people/{pid}")
        except Exception:
            pass


@pytest.fixture(scope="module")
def company_id(session):
    r = session.get(f"{API}/registry/companies")
    assert r.status_code == 200
    # pick a 'propria' or any
    for c in r.json():
        if c.get("type") in ("propria", "cliente"):
            return c["id"]
    return r.json()[0]["id"]


@pytest.fixture(scope="module")
def category_id(session):
    r = session.get(f"{API}/cadastros/categories") if False else session.get(f"{API}/categories")
    if r.status_code != 200:
        # try other router
        r = session.get(f"{API}/access/categories")
    assert r.status_code == 200, f"categories: {r.status_code} {r.text}"
    data = r.json()
    items = data if isinstance(data, list) else data.get("items", [])
    assert items, "no categories available"
    return items[0]["id"]


def _mk(company_id, category_id, **extra):
    body = {
        "person_type": "funcionario",
        "name": extra.pop("name", "TEST_ RegistryDocType"),
        "company_id": company_id,
        "category_ids": [category_id],
        "doc_type": "cpf",
        "doc_number": "529.982.247-25",
    }
    body.update(extra)
    return body


# ---------- Doc type validation ----------

def test_create_person_cpf_valid(session, company_id, category_id):
    r = session.post(f"{API}/registry/people",
                     json=_mk(company_id, category_id, name="TEST_ DocCpfOk"))
    assert r.status_code == 200, r.text
    p = r.json()["person"]
    assert p["doc_type"] == "cpf"
    assert p["cpf"]  # formatted
    assert p["doc_number"]
    assert p["can_authorize_visits"] is True
    CREATED.append(p["id"])
    # GET verifies persistence
    g = session.get(f"{API}/registry/people/{p['id']}")
    assert g.status_code == 200
    assert g.json()["doc_type"] == "cpf"


def test_create_person_cpf_invalid(session, company_id, category_id):
    r = session.post(f"{API}/registry/people",
                     json=_mk(company_id, category_id, name="TEST_ CpfBad",
                              doc_number="111.111.111-11"))
    assert r.status_code == 422
    assert "doc_number" in r.json()["detail"]["fields"]


def test_create_person_rg(session, company_id, category_id):
    r = session.post(f"{API}/registry/people", json=_mk(company_id, category_id,
                     name="TEST_ RgOk", doc_type="rg", doc_number="12.345.678-X"))
    assert r.status_code == 200, r.text
    p = r.json()["person"]
    assert p["doc_type"] == "rg"
    assert p["rg"]
    CREATED.append(p["id"])


def test_create_person_passport_uppercase(session, company_id, category_id):
    r = session.post(f"{API}/registry/people", json=_mk(company_id, category_id,
                     name="TEST_ Pass", doc_type="passaporte", doc_number="ab123456"))
    assert r.status_code == 200, r.text
    p = r.json()["person"]
    assert p["doc_type"] == "passaporte"
    assert p["doc_number"] == "AB123456"
    CREATED.append(p["id"])


def test_duplicate_document(session, company_id, category_id):
    r1 = session.post(f"{API}/registry/people", json=_mk(company_id, category_id,
                     name="TEST_ Dup1", doc_number="153.509.460-56"))
    assert r1.status_code == 200, r1.text
    CREATED.append(r1.json()["person"]["id"])
    r2 = session.post(f"{API}/registry/people", json=_mk(company_id, category_id,
                     name="TEST_ Dup2", doc_number="153.509.460-56"))
    assert r2.status_code == 422
    msg = r2.json()["detail"]["fields"].get("doc_number", "")
    assert "cadastrado" in msg.lower()


# ---------- Matricula optional ----------

def test_matricula_not_required(session, company_id, category_id):
    body = _mk(company_id, category_id, name="TEST_ SemMatricula",
               doc_number="390.533.447-05")
    body.pop("matricula", None)
    r = session.post(f"{API}/registry/people", json=body)
    assert r.status_code == 200, r.text
    CREATED.append(r.json()["person"]["id"])


# ---------- Backward compat: cpf only ----------

def test_backend_compat_cpf_only(session, company_id, category_id):
    # No doc_type, only cpf -> treated as CPF
    body = {
        "person_type": "funcionario",
        "name": "TEST_ CompatCpf",
        "company_id": company_id,
        "category_ids": [category_id],
        "cpf": "248.438.034-80",
    }
    r = session.post(f"{API}/registry/people", json=body)
    assert r.status_code == 200, r.text
    p = r.json()["person"]
    assert p["doc_type"] == "cpf"
    assert p["doc_number"]
    CREATED.append(p["id"])


# ---------- can_authorize_visits + authorize filter ----------

def test_can_authorize_default_true_and_filter(session, company_id, category_id):
    r = session.post(f"{API}/registry/people", json=_mk(company_id, category_id,
                     name="TEST_ AuthYes", doc_type="rg", doc_number="AUTH-YES-TEST"))
    assert r.status_code == 200, r.text
    pid_yes = r.json()["person"]["id"]
    CREATED.append(pid_yes)
    assert r.json()["person"]["can_authorize_visits"] is True

    r2 = session.post(f"{API}/registry/people", json=_mk(company_id, category_id,
                     name="TEST_ AuthNo", doc_type="rg", doc_number="AUTH-NO-TEST",
                     can_authorize_visits=False))
    assert r2.status_code == 200, r2.text
    pid_no = r2.json()["person"]["id"]
    CREATED.append(pid_no)
    assert r2.json()["person"]["can_authorize_visits"] is False

    # Reload keeps value
    g = session.get(f"{API}/registry/people/{pid_no}")
    assert g.json()["can_authorize_visits"] is False

    # Filter authorize=true excludes pid_no
    r3 = session.get(f"{API}/registry/people?authorize=true&q=TEST_&limit=200")
    assert r3.status_code == 200
    ids = {p["id"] for p in r3.json()["items"]}
    assert pid_yes in ids
    assert pid_no not in ids


# ---------- Migration: existing people have authorize=true and doc_type=cpf ----------

def test_migration_existing_people(session):
    r = session.get(f"{API}/registry/people?limit=200")
    assert r.status_code == 200
    items = r.json()["items"]
    # at least a few seeded people
    sample = [p for p in items if not p["name"].startswith("TEST_")][:20]
    assert sample, "no non-TEST people"
    # fetch detail to confirm fields exist
    for p in sample[:5]:
        g = session.get(f"{API}/registry/people/{p['id']}")
        gd = g.json()
        assert gd.get("can_authorize_visits") is not False, f"{p['name']} should be True"
        assert gd.get("doc_type") in ("cpf", "rg", "passaporte", "outro")


# ---------- Visits: 422 for host not authorizing ----------

def test_visit_rejects_non_authorizing_host(session, company_id, category_id):
    # create a person with authorize=False in a company
    r = session.post(f"{API}/registry/people", json=_mk(company_id, category_id,
                     name="TEST_ HostDenied", doc_type="rg", doc_number="HOST-DENIED-TST",
                     can_authorize_visits=False))
    assert r.status_code == 200
    pid = r.json()["person"]["id"]
    CREATED.append(pid)
    # fetch an active visit_type
    vt = session.get(f"{API}/visits/types?active=true").json()
    assert vt
    visit_body = {
        "visit_type_id": vt[0]["id"],
        "host_company_id": company_id,
        "host_person_id": pid,
        "name": "TEST_ VisitorHostDenied",
        "doc_type": "cpf",
        "doc_number": "529.982.247-25",
        "identifier": {"type": "qrcode", "value": ""},
    }
    rv = session.post(f"{API}/visits", json=visit_body)
    assert rv.status_code == 422, rv.text
    assert "host_person_id" in rv.json()["detail"]["fields"]

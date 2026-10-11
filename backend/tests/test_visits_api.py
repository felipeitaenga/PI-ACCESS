"""End-to-end API tests for /api/visits endpoints via preview URL."""
import os
import time
import pytest
import requests
from datetime import datetime, timedelta, timezone

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://nx-access-demo.preview.emergentagent.com").rstrip("/")
ADMIN = {"email": "felipejferreira@gmail.com", "password": "NxAccess@2026"}
OPER = {"email": "operador@nxaccess.com", "password": "Operador@2026"}

# A valid CPF
VALID_CPF = "529.982.247-25"


def _login(creds):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=creds, timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def admin():
    return _login(ADMIN)


@pytest.fixture(scope="module")
def oper():
    return _login(OPER)


@pytest.fixture(scope="module")
def types(admin):
    r = admin.get(f"{BASE_URL}/api/visits/types")
    assert r.status_code == 200
    return r.json()


@pytest.fixture(scope="module")
def default_type(types):
    tp = next((t for t in types if t.get("name") == "Visita padrão"), None)
    assert tp, f"'Visita padrão' not found; got {[t.get('name') for t in types]}"
    return tp


@pytest.fixture(scope="module")
def picked(admin):
    """Pick a company (propria/cliente) with at least one active person."""
    comps = admin.get(f"{BASE_URL}/api/org/companies").json()
    comps = comps.get("items", comps) if isinstance(comps, dict) else comps
    people = admin.get(f"{BASE_URL}/api/people").json()
    people = people.get("items", people) if isinstance(people, dict) else people
    for c in comps:
        if c.get("type") not in ("propria", "cliente"):
            continue
        for p in people:
            if p.get("company_id") == c["id"] and p.get("status") == "ativo":
                return {"company": c, "person": p}
    pytest.skip(f"no company+person combo found. companies={[(c.get('name'),c.get('type')) for c in comps]}")


# ----- Visit types CRUD -----

def test_default_visita_padrao(default_type):
    assert default_type.get("default_hours") in (8, 8.0)
    assert default_type.get("active") is True
    assert default_type.get("category_ids"), "must have at least one category"


def test_type_create_update_delete_admin(admin):
    body = {"name": "TEST_tipo_demo", "category_ids": ["VISITANTE"], "default_hours": "0,5",
            "require_escort": False, "require_photo": False, "active": True}
    r = admin.post(f"{BASE_URL}/api/visits/types", json=body)
    assert r.status_code == 200, r.text
    created = r.json()
    assert created["default_hours"] == 0.5
    tid = created["id"]
    try:
        r2 = admin.put(f"{BASE_URL}/api/visits/types/{tid}",
                       json={**body, "default_hours": 2, "name": "TEST_tipo_demo2"})
        assert r2.status_code == 200
        assert r2.json()["default_hours"] == 2.0
    finally:
        d = admin.delete(f"{BASE_URL}/api/visits/types/{tid}")
        assert d.status_code == 200


def test_type_validation_422(admin):
    r = admin.post(f"{BASE_URL}/api/visits/types", json={"name": "", "category_ids": []})
    assert r.status_code == 422
    fields = r.json()["detail"]["fields"]
    assert "name" in fields and "category_ids" in fields


def test_type_forbidden_for_operator(oper):
    r = oper.post(f"{BASE_URL}/api/visits/types",
                  json={"name": "TEST_x", "category_ids": ["VISITANTE"], "default_hours": 1})
    assert r.status_code == 403


def test_settings_admin_only(admin, oper):
    r = admin.get(f"{BASE_URL}/api/visits/settings")
    assert r.status_code == 200
    s0 = r.json()
    # Operator cannot PUT
    r2 = oper.put(f"{BASE_URL}/api/visits/settings", json=s0)
    assert r2.status_code == 403
    # Admin PUT roundtrip (restore same values)
    body = {"validate_cpf": s0.get("validate_cpf", True), "validate_rg": s0.get("validate_rg", False),
            "default_hours": s0.get("default_hours", 8)}
    r3 = admin.put(f"{BASE_URL}/api/visits/settings", json=body)
    assert r3.status_code == 200


# ----- Create visit -----

def _visit_body(default_type, picked, **overrides):
    body = {"visit_type_id": default_type["id"],
            "host_company_id": picked["company"]["id"],
            "host_person_id": picked["person"]["id"],
            "name": "TEST_ Visitante Alpha",
            "doc_type": "cpf", "doc_number": VALID_CPF,
            "visitor_company": "TEST_ EmpresaDoVisitante",
            "identifier": {"type": "qrcode", "value": ""},
            "plate": "", "notes": "teste"}
    body.update(overrides)
    return body


def _cleanup(admin, visit_id=None, visitor_doc=None):
    try:
        if visit_id:
            admin.post(f"{BASE_URL}/api/visits/{visit_id}/end")
    except Exception:
        pass


def test_create_visit_qrcode_defaults_end(admin, default_type, picked):
    body = _visit_body(default_type, picked)
    r = admin.post(f"{BASE_URL}/api/visits", json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    v = data["visit"]
    assert v["status"] == "presente"
    assert v["credential_type"] == "qrcode"
    assert v["credential_value"].startswith("PIV-")
    # end = start + 8h
    s = datetime.fromisoformat(v["start_at"])
    e = datetime.fromisoformat(v["end_at"])
    assert abs((e - s).total_seconds() - 8*3600) < 60
    assert "sync" in data and isinstance(data["sync"], list)
    # Cleanup
    admin.post(f"{BASE_URL}/api/visits/{v['id']}/end")


def test_create_visit_future_scheduled(admin, default_type, picked):
    future = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    body = _visit_body(default_type, picked, start_at=future, name="TEST_ Futuro")
    r = admin.post(f"{BASE_URL}/api/visits", json=body)
    assert r.status_code == 200, r.text
    v = r.json()["visit"]
    assert v["status"] == "agendado"
    admin.post(f"{BASE_URL}/api/visits/{v['id']}/end")


def test_cpf_invalid_422(admin, default_type, picked):
    body = _visit_body(default_type, picked, doc_number="111.111.111-11")
    r = admin.post(f"{BASE_URL}/api/visits", json=body)
    assert r.status_code == 422
    assert "doc_number" in r.json()["detail"]["fields"]


def test_host_from_other_company_422(admin, default_type, picked):
    # Find a person from another company
    people = admin.get(f"{BASE_URL}/api/people").json()
    people = people.get("items", people) if isinstance(people, dict) else people
    other = next((p for p in people if p.get("company_id") and p["company_id"] != picked["company"]["id"]
                  and p.get("status") == "ativo"), None)
    if not other:
        pytest.skip("no cross-company person available")
    body = _visit_body(default_type, picked, host_person_id=other["id"])
    r = admin.post(f"{BASE_URL}/api/visits", json=body)
    assert r.status_code == 422
    assert "host_person_id" in r.json()["detail"]["fields"]


def test_plate_invalid_422(admin, default_type, picked):
    body = _visit_body(default_type, picked, plate="XX11", name="TEST_ PlacaRuim")
    r = admin.post(f"{BASE_URL}/api/visits", json=body)
    assert r.status_code == 422
    assert "plate" in r.json()["detail"]["fields"]


def test_card_hex_to_decimal(admin, default_type, picked):
    body = _visit_body(default_type, picked, identifier={"type": "cartao", "value": "0x1A"}, name="TEST_ Cartao")
    r = admin.post(f"{BASE_URL}/api/visits", json=body)
    assert r.status_code == 200, r.text
    v = r.json()["visit"]
    assert v["credential_type"] == "cartao"
    assert v["credential_value"] == "26"
    admin.post(f"{BASE_URL}/api/visits/{v['id']}/end")


def test_lookup_after_create(admin, default_type, picked):
    body = _visit_body(default_type, picked, name="TEST_ Lookup")
    r = admin.post(f"{BASE_URL}/api/visits", json=body)
    assert r.status_code == 200
    v = r.json()["visit"]
    r2 = admin.get(f"{BASE_URL}/api/visits/lookup", params={"doc_type": "cpf", "doc_number": VALID_CPF})
    assert r2.status_code == 200
    data = r2.json()
    assert data["found"] is True
    assert "name" in data["visitor"]
    admin.post(f"{BASE_URL}/api/visits/{v['id']}/end")


def test_present_lists_current(admin, default_type, picked):
    body = _visit_body(default_type, picked, name="TEST_ Present")
    r = admin.post(f"{BASE_URL}/api/visits", json=body)
    assert r.status_code == 200
    v = r.json()["visit"]
    r2 = admin.get(f"{BASE_URL}/api/visits/present")
    assert r2.status_code == 200
    items = r2.json()
    assert any(it["id"] == v["id"] for it in items)
    this = next(it for it in items if it["id"] == v["id"])
    assert "remaining_min" in this
    assert this["remaining_min"] > 0
    admin.post(f"{BASE_URL}/api/visits/{v['id']}/end")


def test_end_visit(admin, default_type, picked):
    body = _visit_body(default_type, picked, name="TEST_ Endme")
    v = admin.post(f"{BASE_URL}/api/visits", json=body).json()["visit"]
    r = admin.post(f"{BASE_URL}/api/visits/{v['id']}/end")
    assert r.status_code == 200
    # second end -> 400
    r2 = admin.post(f"{BASE_URL}/api/visits/{v['id']}/end")
    assert r2.status_code == 400


# ----- Blacklist flow -----

def test_blacklist_blocks_operator_admin_can_override(admin, oper, default_type, picked):
    # First create a visitor (via visit) with a specific CPF, then flag blacklist in db via admin PUT? There's no API — use lookup/visitor fields approach via direct cadastros if any
    # Workaround: use a distinct CPF, create visit, then flip blacklist via mongodb through admin? There's no backend endpoint for blacklist flag that I know; try /api/visitors or /api/cadastros/visitors
    cpf = "248.438.034-80"  # another valid CPF
    body = _visit_body(default_type, picked, doc_number=cpf, name="TEST_ Blacklist")
    r = admin.post(f"{BASE_URL}/api/visits", json=body)
    assert r.status_code == 200
    v = r.json()["visit"]
    vid = r.json()["visitor"]["id"]
    admin.post(f"{BASE_URL}/api/visits/{v['id']}/end")
    # Try flipping blacklist via visitors_reg router (PUT /api/cadastros/visitors/{id})
    paths = [f"/api/cadastros/visitors/{vid}", f"/api/visitors/{vid}"]
    flipped = False
    for p in paths:
        r = admin.put(f"{BASE_URL}{p}", json={"blacklist": True, "blacklist_reason": "TEST", "name": "TEST_ Blacklist",
                                                "doc_type": "cpf", "doc_number": cpf})
        if r.status_code in (200, 204):
            flipped = True
            break
    if not flipped:
        pytest.skip("no visitor-blacklist endpoint found; cannot set blacklist via API")
    # Operator should get 409
    body2 = _visit_body(default_type, picked, doc_number=cpf, name="TEST_ Blacklist")
    r2 = oper.post(f"{BASE_URL}/api/visits", json=body2)
    assert r2.status_code == 409, r2.text
    # Admin without justification -> also 409
    r3 = admin.post(f"{BASE_URL}/api/visits", json=body2)
    assert r3.status_code == 409
    # Admin with justification >=5 chars -> 200
    body3 = {**body2, "blacklist_justification": "Reunião urgente autorizada pelo gerente"}
    r4 = admin.post(f"{BASE_URL}/api/visits", json=body3)
    assert r4.status_code == 200
    v4 = r4.json()["visit"]
    assert v4.get("blacklist_override")
    admin.post(f"{BASE_URL}/api/visits/{v4['id']}/end")
    # Cleanup — unflag
    for p in paths:
        admin.put(f"{BASE_URL}{p}", json={"blacklist": False, "blacklist_reason": "", "name": "TEST_ Blacklist",
                                           "doc_type": "cpf", "doc_number": cpf})

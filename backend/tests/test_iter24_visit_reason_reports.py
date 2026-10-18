"""Iter24: visit_reason (portaria) persists, shows in reports visits (json/xlsx/pdf); portaria lookup by CPF."""
import io
import os

import pytest
import requests

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api"
ADMIN = {"email": "felipejferreira@gmail.com", "password": "NxAccess@2026"}
UI_CPF = "74400000486"  # created by UI test (ui_setup_iter24) if present


@pytest.fixture(scope="module")
def s():
    x = requests.Session()
    x.headers["Authorization"] = "Bearer " + x.post(f"{API}/auth/login", json=ADMIN, timeout=20).json()["access_token"]
    return x


# Reports › Visitas: column Motivo present
def test_reports_visits_has_motivo_column(s):
    d = s.get(f"{API}/reports/data/visits?format=json", timeout=30).json()
    assert {"key": "visit_reason", "label": "Motivo"} in d["columns"]


# Visit created by UI portaria carries visit_reason in the report rows
def test_ui_visit_reason_in_report(s):
    d = s.get(f"{API}/reports/data/visits?format=json&person=TEST_UI24", timeout=30).json()
    rows = [r for r in d["rows"] if "TEST_UI24" in str(r.get("visitor_name", "")) or "TEST_UI24" in str(r)]
    if not rows:
        pytest.skip("no TEST_UI24 visit created by UI")
    assert any(r.get("visit_reason") == "TEST_UI24 manutenção ar" for r in rows), rows[:2]


# Present visits endpoint keeps the reason (portaria)
def test_present_visit_has_reason(s):
    data = s.get(f"{API}/visits/present", timeout=20).json()
    items = data if isinstance(data, list) else data.get("items", data.get("visits", []))
    mine = [v for v in items if "TEST_UI24" in str(v.get("visitor_name", ""))]
    if not mine:
        pytest.skip("no TEST_UI24 present visit")
    assert mine[0].get("visit_reason") == "TEST_UI24 manutenção ar"


# Excel and PDF contain Motivo header
def test_xlsx_pdf_have_motivo(s):
    from openpyxl import load_workbook
    r = s.get(f"{API}/reports/data/visits?format=xlsx", timeout=60)
    assert r.status_code == 200
    ws = load_workbook(io.BytesIO(r.content)).active
    vals = [c.value for row in ws.iter_rows(min_row=1, max_row=6) for c in row]
    assert "Motivo" in vals
    p = s.get(f"{API}/reports/data/visits?format=pdf", timeout=60)
    assert p.status_code == 200 and p.content[:4] == b"%PDF"


# Portaria lookup rejects invalid CPF / non-cpf doc types
def test_portaria_lookup_invalid_cpf(s):
    r = s.get(f"{API}/visits/lookup?doc_type=cpf&doc_number=12345678900", timeout=20)
    assert r.status_code in (200, 400, 422)
    if r.status_code == 200:
        assert r.json().get("found") is False

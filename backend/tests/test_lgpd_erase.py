"""LGPD erase: admin-only POST /api/lgpd/erase + anonymization of access_events,
visits, identifiers, vehicles, mqtt_commands, audit_logs; GET /api/lgpd/erasures."""
import os
import uuid
import pytest
import requests
from pymongo import MongoClient

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
ADMIN = ("felipejferreira@gmail.com", "NxAccess@2026")
OPERATOR = ("operador@nxaccess.com", "Operador@2026")
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
TAG = "TEST_LGPD_" + uuid.uuid4().hex[:6]
ANON = "Pessoa removida (LGPD)"


def _login(email, pwd):
    s = requests.Session()
    r = s.post(f"{BASE}/auth/login", json={"email": email, "password": pwd}, timeout=20)
    assert r.status_code == 200, r.text
    tok = r.json().get("access_token")
    s.headers.update({"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
    return s


def _cpf(seed):
    n = [int(x) for x in f"{seed:09d}"[-9:]]
    for k in (10, 11):
        d = (sum(a * b for a, b in zip(n, range(k, 1, -1))) * 10) % 11 % 10
        n.append(d)
    return "".join(map(str, n))


@pytest.fixture(scope="module")
def adm():
    return _login(*ADMIN)


@pytest.fixture(scope="module")
def op():
    try:
        return _login(*OPERATOR)
    except AssertionError:
        pytest.skip("Operator login failed")


@pytest.fixture(scope="module")
def ctx(adm):
    """Fetch a valid company (propria) + visit type."""
    comps = adm.get(f"{BASE}/registry/companies").json()
    own = next((c for c in comps if c.get("type") == "propria"), None)
    assert own, "No propria company"
    cats = adm.get(f"{BASE}/access/categories/all").json()
    assert cats
    vtypes = adm.get(f"{BASE}/visits/types").json()
    vt = next((t for t in vtypes if t.get("active")), vtypes[0])
    return {"company": own, "cat_id": cats[0]["id"], "visit_type_id": vt["id"]}


def _make_person(adm, ctx, name_suffix="Host", card="1234567"):
    body = {
        "person_type": "funcionario",
        "name": f"{TAG} {name_suffix}",
        "doc_type": "cpf",
        "doc_number": _cpf(int(uuid.uuid4().int % 10**9)),
        "company_id": ctx["company"]["id"],
        "category_ids": [ctx["cat_id"]],
        "can_authorize_visits": True,
        "email": f"{TAG.lower()}_{name_suffix.lower()}@test.com",
        "photo": "",
        "identifiers": [{"type": "cartao", "value": card}],
        "vehicles": [{"plate": "ABC1D23", "model": "Teste", "color": "Preto"}],
    }
    r = adm.post(f"{BASE}/registry/people", json=body)
    assert r.status_code == 200, r.text
    return r.json()["person"]


def _make_visit(adm, ctx, host_pid, name_suffix="Visita"):
    body = {
        "visit_type_id": ctx["visit_type_id"],
        "host_company_id": ctx["company"]["id"],
        "host_person_id": host_pid,
        "name": f"{TAG} {name_suffix}",
        "doc_type": "outro",
        "doc_number": f"{TAG}{name_suffix[:3]}",
        "identifier": {"type": "qrcode"},
    }
    r = adm.post(f"{BASE}/visits", json=body)
    assert r.status_code == 200, r.text
    return r.json()


# --------------------- Permission + validation errors ---------------------

class TestLgpdValidation:
    def test_operator_forbidden(self, op):
        r = op.post(f"{BASE}/lgpd/erase", json={"kind": "person", "id": "x", "justification": "x" * 15})
        assert r.status_code == 403, r.text

    def test_operator_cannot_list_erasures(self, op):
        r = op.get(f"{BASE}/lgpd/erasures")
        assert r.status_code == 403

    def test_admin_short_justification_422(self, adm):
        r = adm.post(f"{BASE}/lgpd/erase", json={"kind": "person", "id": "any", "justification": "short"})
        assert r.status_code == 422

    def test_admin_invalid_kind_400(self, adm):
        r = adm.post(f"{BASE}/lgpd/erase", json={"kind": "banana", "id": "x", "justification": "x" * 15})
        assert r.status_code == 400

    def test_admin_missing_id_400(self, adm):
        r = adm.post(f"{BASE}/lgpd/erase", json={"kind": "person", "id": "", "justification": "x" * 15})
        assert r.status_code == 400

    def test_admin_not_found_404(self, adm):
        r = adm.post(f"{BASE}/lgpd/erase",
                     json={"kind": "person", "id": "nope-" + uuid.uuid4().hex, "justification": "x" * 15})
        assert r.status_code == 404


# --------------------- Person (fixo) erase flow ---------------------

class TestLgpdErasePerson:
    pid = None
    visit_id = None
    visitor_id = None

    def test_setup_person_card_plate_vehicle(self, adm, ctx):
        p = _make_person(adm, ctx, name_suffix="Fixo")
        TestLgpdErasePerson.pid = p["id"]
        # confirm children exist
        assert db.identifiers.count_documents({"person_id": p["id"]}) >= 1
        assert db.vehicles.count_documents({"person_id": p["id"]}) >= 1
        # seed an access_event for this person
        db.access_events.insert_one({
            "id": f"{TAG}-ev-person", "person_id": p["id"], "person_name": p["name"],
            "company_id": ctx["company"]["id"], "person_photo": "data:image/png;base64,xxx",
            "captured_photo": "data:image/png;base64,yyy", "document": p.get("doc_number", ""),
            "timestamp": "2099-01-01T00:00:00+00:00", "access_result": "granted",
        })
        # seed a sync_job + mqtt_command referring to this id
        db.sync_jobs.insert_one({"id": f"{TAG}-sj-person", "person_id": p["id"],
                                 "device_name": "Dispositivo X", "status": "pending"})
        db.mqtt_commands.insert_one({"id": f"{TAG}-mq-person", "payload": {"info": {"customId": p["id"]}}})

    def test_setup_visit_hosted_by_person(self, adm, ctx):
        v = _make_visit(adm, ctx, TestLgpdErasePerson.pid, name_suffix="Hosted")
        TestLgpdErasePerson.visit_id = v["visit"]["id"]
        TestLgpdErasePerson.visitor_id = v["visitor"]["id"]
        # verify host set
        doc = db.visits.find_one({"id": v["visit"]["id"]})
        assert doc["host_name"] and TAG in doc["host_name"]

    def test_erase_person(self, adm):
        pid = TestLgpdErasePerson.pid
        r = adm.post(f"{BASE}/lgpd/erase", json={
            "kind": "person", "id": pid,
            "justification": "Pedido do titular (LGPD) — protocolo TEST_" + uuid.uuid4().hex[:6],
        })
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert body["counts"].get("eventos", 0) >= 1
        assert body["counts"].get("identificadores", 0) >= 1
        assert body["counts"].get("veiculos", 0) >= 1
        assert body["counts"].get("visitas_anfitriao", 0) >= 1

    def test_person_record_deleted(self):
        assert db.people.find_one({"id": TestLgpdErasePerson.pid}) is None

    def test_identifiers_and_vehicles_deleted(self):
        assert db.identifiers.count_documents({"person_id": TestLgpdErasePerson.pid}) == 0
        assert db.vehicles.count_documents({"person_id": TestLgpdErasePerson.pid}) == 0

    def test_access_events_anonymized(self):
        ev = db.access_events.find_one({"id": f"{TAG}-ev-person"})
        assert ev is not None
        assert ev["person_id"] is None
        assert ev["person_name"] == ANON
        assert ev["person_photo"] == ""
        assert ev["captured_photo"] == ""
        assert ev.get("anonymized") is True

    def test_hosted_visit_anonymized_host(self):
        v = db.visits.find_one({"id": TestLgpdErasePerson.visit_id})
        assert v is not None
        assert v["host_name"] == ANON

    def test_audit_logs_anonymized(self):
        # Pre-existing audit logs (criar/editar) must have details anonymized.
        # The new lgpd-exclusao record is written AFTER the update_many so it keeps
        # the initials + justification for accountability (expected by implementation).
        logs = list(db.audit_logs.find({"entity_id": TestLgpdErasePerson.pid}))
        assert logs, "Expected at least one audit log for the erased person"
        prior = [lg for lg in logs if lg.get("action") != "lgpd-exclusao"]
        assert prior, "Expected a prior audit log (criar) for the erased person"
        for lg in prior:
            assert lg.get("details") == ANON, lg
        erase_log = next((lg for lg in logs if lg.get("action") == "lgpd-exclusao"), None)
        assert erase_log is not None
        assert "·" in (erase_log.get("details") or ""), erase_log

    def test_sync_jobs_renamed(self):
        sj = db.sync_jobs.find_one({"id": f"{TAG}-sj-person"})
        assert sj is not None
        assert sj.get("device_name", "").startswith("LGPD:")
        assert sj.get("person_id") is None

    def test_mqtt_commands_deleted(self):
        assert db.mqtt_commands.find_one({"id": f"{TAG}-mq-person"}) is None

    def test_lgpd_erasure_record_person(self):
        rec = db.lgpd_erasures.find_one({"subject_id": TestLgpdErasePerson.pid})
        assert rec is not None
        assert rec["kind"] == "person"
        assert rec["by"] == ADMIN[0]
        assert len(rec["justification"]) >= 10
        assert rec["initials"]
        assert "eventos" in rec["counts"]


# --------------------- Visitor erase flow ---------------------

class TestLgpdEraseVisitor:
    visit_id = None
    visitor_id = None
    host_pid = None

    def test_setup_visitor(self, adm, ctx):
        host = _make_person(adm, ctx, name_suffix="HostV", card="2345678")
        TestLgpdEraseVisitor.host_pid = host["id"]
        v = _make_visit(adm, ctx, host["id"], name_suffix="Visitante")
        TestLgpdEraseVisitor.visit_id = v["visit"]["id"]
        TestLgpdEraseVisitor.visitor_id = v["visitor"]["id"]
        # seed mqtt command with visitor id
        db.mqtt_commands.insert_one({"id": f"{TAG}-mq-visitor",
                                     "payload": {"info": {"customId": v["visitor"]["id"]}}})
        # seed a self_registration with same visitor_id
        db.self_registrations.insert_one({"id": f"{TAG}-sr-visitor",
                                          "visitor_id": v["visitor"]["id"], "status": "approved"})

    def test_erase_visitor(self, adm):
        r = adm.post(f"{BASE}/lgpd/erase", json={
            "kind": "visitor", "id": TestLgpdEraseVisitor.visitor_id,
            "justification": "Solicitação do visitante — LGPD TEST",
        })
        assert r.status_code == 200, r.text
        counts = r.json()["counts"]
        assert counts.get("visitas", 0) >= 1
        assert counts.get("solicitacoes", 0) >= 1

    def test_visitor_record_deleted(self):
        assert db.visitors.find_one({"id": TestLgpdEraseVisitor.visitor_id}) is None

    def test_visit_anonymized(self):
        v = db.visits.find_one({"id": TestLgpdEraseVisitor.visit_id})
        assert v is not None
        assert v["visitor_id"] is None
        assert v["visitor_name"] == ANON
        assert v["doc_number"] == ""
        assert v.get("anonymized") is True

    def test_self_registration_deleted(self):
        assert db.self_registrations.find_one({"id": f"{TAG}-sr-visitor"}) is None

    def test_mqtt_commands_deleted(self):
        assert db.mqtt_commands.find_one({"id": f"{TAG}-mq-visitor"}) is None

    def test_lgpd_erasure_record_visitor(self):
        rec = db.lgpd_erasures.find_one({"subject_id": TestLgpdEraseVisitor.visitor_id})
        assert rec is not None
        assert rec["kind"] == "visitor"


# --------------------- Erasures listing ---------------------

class TestLgpdListErasures:
    def test_admin_lists(self, adm):
        r = adm.get(f"{BASE}/lgpd/erasures")
        assert r.status_code == 200
        items = r.json()
        assert isinstance(items, list)
        subs = {it.get("subject_id") for it in items}
        assert TestLgpdErasePerson.pid in subs
        assert TestLgpdEraseVisitor.visitor_id in subs


# --------------------- Cleanup ---------------------

@pytest.fixture(scope="module", autouse=True)
def _cleanup():
    yield
    # Erase lgpd test traces
    db.access_events.delete_many({"id": {"$regex": f"^{TAG}"}})
    db.sync_jobs.delete_many({"id": {"$regex": f"^{TAG}"}})
    db.mqtt_commands.delete_many({"id": {"$regex": f"^{TAG}"}})
    db.self_registrations.delete_many({"id": {"$regex": f"^{TAG}"}})
    # Delete anonymized visits created in tests
    for vid in [TestLgpdErasePerson.visit_id, TestLgpdEraseVisitor.visit_id]:
        if vid:
            db.visits.delete_many({"id": vid})
    # Delete the extra host person used in visitor test if still present
    if TestLgpdEraseVisitor.host_pid:
        db.people.delete_many({"id": TestLgpdEraseVisitor.host_pid})
        db.identifiers.delete_many({"person_id": TestLgpdEraseVisitor.host_pid})
        db.vehicles.delete_many({"person_id": TestLgpdEraseVisitor.host_pid})
    # Clean up lgpd_erasures created by tests
    db.lgpd_erasures.delete_many({"subject_id": {
        "$in": [TestLgpdErasePerson.pid, TestLgpdEraseVisitor.visitor_id]
    }})
    # Clean up audit_logs anonymized that reference our ids
    for eid in [TestLgpdErasePerson.pid, TestLgpdEraseVisitor.visitor_id, TestLgpdEraseVisitor.host_pid]:
        if eid:
            db.audit_logs.delete_many({"entity_id": eid})

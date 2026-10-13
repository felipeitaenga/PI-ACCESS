"""Autocadastro (selfreg) + agendamentos — testes end-to-end A..K.

Rode: cd /app/backend && python -m pytest -q -o addopts='' tests/test_selfreg_flow.py
"""
import asyncio
import base64
import hashlib
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import requests

_LOOP = asyncio.new_event_loop()

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

asyncio.set_event_loop(_LOOP)
db = AsyncIOMotorClient(os.environ["MONGO_URL"], io_loop=_LOOP)[os.environ["DB_NAME"]]

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://nx-access-demo.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"
ADMIN = {"email": "felipejferreira@gmail.com", "password": "NxAccess@2026"}
OPER = {"email": "operador@nxaccess.com", "password": "Operador@2026"}
RECEP = {"email": "recepcao@nxaccess.com", "password": "Recepcao@2026"}
MGR = {"email": "TEST_gestor_selfreg@teste.com", "password": "TEST_Gestor@2026"}
FACE = Path("/tmp/face.jpg")

# -------- helpers --------
def _sha(t):
    return hashlib.sha256((t or "").encode()).hexdigest()


def login(creds):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=creds, timeout=20)
    assert r.status_code == 200, f"login {creds['email']}: {r.status_code} {r.text}"
    s.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    return s, r.json()


def face_dataurl():
    with open(FACE, "rb") as f:
        return "data:image/jpeg;base64," + base64.b64encode(f.read()).decode()


async def _mongo_clear_rate():
    await db.rate_hits.delete_many({})


def clear_rate():
    _LOOP.run_until_complete(_mongo_clear_rate())


def valid_cpf(seed=12345678):
    # algoritmo pt-BR
    digits = [int(x) for x in str(seed).zfill(9)]
    for i in range(2):
        s = sum((len(digits) + 1 - j) * d for j, d in enumerate(digits))
        digits.append(((s * 10) % 11) % 10)
    return "".join(str(d) for d in digits)


@pytest.fixture(scope="module")
def admin():
    s, u = login(ADMIN)
    return s, u


@pytest.fixture(scope="module")
def oper():
    return login(OPER)[0]


@pytest.fixture(scope="module")
def recep():
    return login(RECEP)[0]


@pytest.fixture(scope="module")
def companies(admin):
    s, _ = admin
    r = s.get(f"{API}/selfreg/companies")
    assert r.status_code == 200
    return r.json()


@pytest.fixture(scope="module")
def visit_type(admin):
    s, _ = admin
    r = s.get(f"{API}/visits/types?active=true")
    assert r.status_code == 200 and r.json()
    return r.json()[0]


@pytest.fixture(scope="module")
def host_person(admin, companies):
    s, _ = admin
    # pick a person from first company
    cid = companies[0]["id"]
    # Query people directly via Mongo (API is paginated/global)
    loop = _LOOP
    async def find():
        return await db.people.find({"company_id": cid, "status": "ativo",
                                     "can_authorize_visits": {"$ne": False},
                                     "deleted": {"$ne": True}},
                                    {"_id": 0, "id": 1, "name": 1, "email": 1,
                                     "company_id": 1}).limit(1).to_list(1)
    people = loop.run_until_complete(find())
    if not people:
        # try other companies
        for c in companies:
            people = loop.run_until_complete(
                db.people.find({"company_id": c["id"], "status": "ativo",
                                "can_authorize_visits": {"$ne": False},
                                "deleted": {"$ne": True}},
                               {"_id": 0, "id": 1, "name": 1, "email": 1, "company_id": 1}).limit(1).to_list(1))
            if people:
                return people[0], c
        pytest.skip("no active host person in any company")
    return people[0], companies[0]


# ============ A. Link de empresa ============
class TestA_CompanyLink:
    def test_enable_company_link_and_submit(self, admin, host_person, visit_type):
        s, _ = admin
        clear_rate()
        host, comp = host_person
        cid = comp["id"]
        r = s.put(f"{API}/selfreg/companies/{cid}",
                  json={"enabled": True, "visit_type_id": visit_type["id"], "regenerate": True})
        assert r.status_code == 200, r.text
        code = r.json()["selfreg_code"]
        assert code
        pytest.selfreg_code = code
        pytest.selfreg_cid = cid
        pytest.selfreg_host = host

        # info — anonymous
        r = requests.get(f"{API}/public/selfreg/info", params={"code": code})
        assert r.status_code == 200, r.text
        info = r.json()
        assert info["company"] == comp["name"]
        assert info["visit_type"] == visit_type["name"]
        assert info["companies"] is None
        assert info["otp"] is False  # SMTP não configurado

        # hosts search
        q_short = requests.post(f"{API}/public/selfreg/hosts", json={"code": code, "q": "ab"})
        assert q_short.status_code == 200 and q_short.json() == []
        name_part = host["name"].split(" ")[0][:5]
        r = requests.post(f"{API}/public/selfreg/hosts", json={"code": code, "q": name_part})
        assert r.status_code == 200
        got = r.json()
        assert len(got) <= 3
        assert any(x["id"] == host["id"] for x in got), f"host not in results: {got}"

        # NoSQL injection — operator object as q
        bad = requests.post(f"{API}/public/selfreg/hosts", json={"code": code, "q": {"$ne": None}})
        assert bad.status_code == 200 and bad.json() == []

        # submit
        cpf = valid_cpf(99988877)
        body = {"code": code, "consent": True, "name": "TEST Visitante Alfa",
                "doc_type": "cpf", "doc_number": cpf,
                "visitor_company": "TEST Co", "host_person_id": host["id"],
                "photo": face_dataurl()}
        r = requests.post(f"{API}/public/selfreg/submit", json=body)
        assert r.status_code == 200, r.text
        js = r.json()
        assert js["status"] == "pendente"
        pytest.selfreg_status_token = js["status_token"]
        pytest.selfreg_cpf_A = cpf

    def test_status_route(self):
        r = requests.get(f"{API}/public/selfreg/status/{pytest.selfreg_status_token}")
        assert r.status_code == 200
        assert r.json()["status"] == "pendente"


# ============ B. QR único (site-link) ============
class TestB_SiteLink:
    def test_site_link_admin_only(self, oper, recep, admin):
        for s in (oper, recep):
            r = s.get(f"{API}/selfreg/site-link")
            assert r.status_code == 403
            r2 = s.put(f"{API}/selfreg/site-link", json={"enabled": True})
            assert r2.status_code == 403
        s, _ = admin
        r = s.get(f"{API}/selfreg/site-link")
        assert r.status_code == 200

    def test_site_link_enable_and_info(self, admin):
        s, _ = admin
        clear_rate()
        r = s.put(f"{API}/selfreg/site-link", json={"enabled": True, "regenerate": True})
        assert r.status_code == 200, r.text
        code = r.json()["code"]
        assert code
        pytest.site_code = code
        info = requests.get(f"{API}/public/selfreg/info", params={"code": code}).json()
        assert info["companies"] is not None
        # should include company A (enabled earlier)
        ids = [c["id"] for c in info["companies"]]
        assert pytest.selfreg_cid in ids

    def test_site_submit_requires_company(self, admin):
        clear_rate()
        cpf = valid_cpf(88877766)
        host = pytest.selfreg_host
        body = {"code": pytest.site_code, "consent": True, "name": "TEST Visitante Site",
                "doc_type": "cpf", "doc_number": cpf, "host_person_id": host["id"],
                "photo": face_dataurl()}
        # without company_id → "Escolha a empresa"
        r = requests.post(f"{API}/public/selfreg/submit", json=body)
        assert r.status_code == 422
        assert "company_id" in str(r.json().get("detail", {}))

        # with company_id → ok
        body["company_id"] = pytest.selfreg_cid
        r = requests.post(f"{API}/public/selfreg/submit", json=body)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "pendente"
        pytest.site_cpf = cpf

    def test_site_disable_all_returns_404(self, admin):
        # Disable all companies self reg → info 404
        s, _ = admin
        # Disable the only enabled company
        s.put(f"{API}/selfreg/companies/{pytest.selfreg_cid}", json={"enabled": False})
        r = requests.get(f"{API}/public/selfreg/info", params={"code": pytest.site_code})
        assert r.status_code == 404
        # re-enable for next tests
        s.put(f"{API}/selfreg/companies/{pytest.selfreg_cid}",
              json={"enabled": True, "visit_type_id": None})


# ============ C. Approval flows & concurrency ============
class TestC_Approval:
    def _create_pending(self, admin, cpf_seed=10, suffix="C"):
        s, _ = admin
        clear_rate()
        cpf = valid_cpf(cpf_seed)
        host = pytest.selfreg_host
        r = requests.post(f"{API}/public/selfreg/submit", json={
            "code": pytest.selfreg_code, "consent": True, "name": f"TEST Visit {suffix}",
            "doc_type": "cpf", "doc_number": cpf, "host_person_id": host["id"],
            "photo": face_dataurl()})
        assert r.status_code == 200, r.text
        # find request id
        _LOOP.run_until_complete(asyncio.sleep(0.3))
        async def find():
            return await db.self_registrations.find_one({"status_token_hash": _sha(r.json()["status_token"])},
                                                        {"_id": 0, "id": 1})
        reg = _LOOP.run_until_complete(find())
        assert reg
        return reg["id"], cpf

    def test_reception_approve(self, admin, recep):
        rid, cpf = self._create_pending(admin, 20010001, "C1")
        r = recep.post(f"{API}/selfreg/requests/{rid}/approve", json={})
        assert r.status_code == 200, r.text
        assert r.json().get("visit_id")
        # second attempt → 409
        r2 = recep.post(f"{API}/selfreg/requests/{rid}/approve", json={})
        assert r2.status_code == 409
        pytest.cpf_c1 = cpf
        pytest.rid_c1 = rid

    def test_host_decision_link(self, admin):
        rid, cpf = self._create_pending(admin, 20020002, "C2")
        # inject a known decision_token
        tok = "TESTtokenC2_" + os.urandom(6).hex()
        loop = _LOOP
        loop.run_until_complete(db.self_registrations.update_one(
            {"id": rid}, {"$set": {"decision_token_hash": _sha(tok)}}))
        # GET view
        r = requests.get(f"{API}/public/selfreg/decision/{tok}")
        assert r.status_code == 200
        assert r.json()["status"] == "pendente"
        # approve
        r = requests.post(f"{API}/public/selfreg/decision/{tok}", json={"action": "approve"})
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "aprovado"
        # second → 409
        r2 = requests.post(f"{API}/public/selfreg/decision/{tok}", json={"action": "approve"})
        assert r2.status_code == 409
        pytest.cpf_c2 = cpf

    def test_host_link_does_not_change_end_at(self, admin):
        rid, cpf = self._create_pending(admin, 20030003, "C3")
        tok = "TESTtokenC3_" + os.urandom(6).hex()
        loop = _LOOP
        loop.run_until_complete(db.self_registrations.update_one(
            {"id": rid}, {"$set": {"decision_token_hash": _sha(tok)}}))
        original = loop.run_until_complete(db.self_registrations.find_one({"id": rid}, {"_id": 0, "end_at": 1}))
        r = requests.post(f"{API}/public/selfreg/decision/{tok}", json={"action": "approve", "end_at": "2099-01-01T00:00:00+00:00"})
        assert r.status_code == 200
        after = loop.run_until_complete(db.self_registrations.find_one({"id": rid}, {"_id": 0, "end_at": 1, "visit_id": 1}))
        # host link ignores end_at override — selfreg kept original end
        assert after["end_at"] == original["end_at"], f"host end_at changed from {original['end_at']} to {after['end_at']}"
        pytest.cpf_c3 = cpf

    def test_concurrency_only_one_visit(self, admin, recep, oper):
        rid, cpf = self._create_pending(admin, 20040004, "C4")
        import threading
        results = {}
        def go(sess, tag):
            r = sess.post(f"{API}/selfreg/requests/{rid}/approve", json={})
            results[tag] = (r.status_code, r.text[:200])
        t1 = threading.Thread(target=go, args=(recep, "r"))
        t2 = threading.Thread(target=go, args=(oper, "o"))
        t1.start(); t2.start(); t1.join(); t2.join()
        codes = sorted([v[0] for v in results.values()])
        assert codes == [200, 409], f"expected [200,409], got {codes} {results}"
        loop = _LOOP
        async def count():
            visitor = await db.visitors.find_one({"doc_key": re.sub(r"\D", "", cpf)}, {"_id": 0, "id": 1})
            if not visitor:
                return 0
            return await db.visits.count_documents({"visitor_id": visitor["id"]})
        n = loop.run_until_complete(count())
        assert n == 1, f"expected 1 visit for {cpf}, got {n}"
        pytest.cpf_c4 = cpf


# ============ D. Convite ============
class TestD_Invite:
    def test_invite_auto_approve_flow(self, admin):
        s, _ = admin
        clear_rate()
        host = pytest.selfreg_host
        r = s.post(f"{API}/selfreg/invites", json={
            "host_company_id": pytest.selfreg_cid, "host_person_id": host["id"],
            "visit_type_id": pytest.selfreg_code and None or None,  # placeholder
            "guest_name": "TEST Convidado D1", "auto_approve": True})
        # need to retrieve visit_type id properly
        assert r.status_code in (200, 422)
        if r.status_code == 422:
            # supply visit_type_id
            vt_r = s.get(f"{API}/visits/types?active=true").json()[0]
            r = s.post(f"{API}/selfreg/invites", json={
                "host_company_id": pytest.selfreg_cid, "host_person_id": host["id"],
                "visit_type_id": vt_r["id"], "guest_name": "TEST Convidado D1",
                "auto_approve": True})
            assert r.status_code == 200, r.text
        js = r.json()
        token = js["link"].rsplit("/", 1)[-1]
        pytest.invite_D1_id = js["invite"]["id"]
        # end_at computed from type
        assert js["invite"]["end_at"]

        cpf = valid_cpf(30010001)
        sub = requests.post(f"{API}/public/selfreg/submit", json={
            "invite": token, "consent": True, "name": "TEST Convidado D1 Nome",
            "doc_type": "cpf", "doc_number": cpf, "photo": face_dataurl()})
        assert sub.status_code == 200, sub.text
        assert sub.json()["status"] == "aprovado"
        pytest.cpf_d1 = cpf

        # second use of same invite token → 404 or 409
        sub2 = requests.post(f"{API}/public/selfreg/submit", json={
            "invite": token, "consent": True, "name": "TEST Convidado D1 Again",
            "doc_type": "cpf", "doc_number": valid_cpf(30011111), "photo": face_dataurl()})
        assert sub2.status_code in (404, 409), f"expected 404/409, got {sub2.status_code}"

    def test_invite_without_auto_approve(self, admin):
        s, _ = admin
        clear_rate()
        host = pytest.selfreg_host
        vt = s.get(f"{API}/visits/types?active=true").json()[0]
        r = s.post(f"{API}/selfreg/invites", json={
            "host_company_id": pytest.selfreg_cid, "host_person_id": host["id"],
            "visit_type_id": vt["id"], "guest_name": "TEST Convidado D2", "auto_approve": False})
        assert r.status_code == 200, r.text
        token = r.json()["link"].rsplit("/", 1)[-1]
        pytest.invite_D2_id = r.json()["invite"]["id"]
        cpf = valid_cpf(30020002)
        sub = requests.post(f"{API}/public/selfreg/submit", json={
            "invite": token, "consent": True, "name": "TEST Convidado D2 Nome",
            "doc_type": "cpf", "doc_number": cpf, "photo": face_dataurl()})
        assert sub.status_code == 200, sub.text
        assert sub.json()["status"] == "pendente"
        pytest.cpf_d2 = cpf


# ============ E. Rejection ============
class TestE_Reject:
    def test_reject_no_visit(self, admin, recep):
        s, _ = admin
        clear_rate()
        cpf = valid_cpf(50050005)
        host = pytest.selfreg_host
        r = requests.post(f"{API}/public/selfreg/submit", json={
            "code": pytest.selfreg_code, "consent": True, "name": "TEST Rejeitado E",
            "doc_type": "cpf", "doc_number": cpf, "host_person_id": host["id"],
            "photo": face_dataurl()})
        assert r.status_code == 200
        loop = _LOOP
        reg = loop.run_until_complete(db.self_registrations.find_one(
            {"status_token_hash": _sha(r.json()["status_token"])}, {"_id": 0, "id": 1}))
        rid = reg["id"]
        rr = recep.post(f"{API}/selfreg/requests/{rid}/reject", json={"reason": "teste"})
        assert rr.status_code == 200
        v = loop.run_until_complete(db.visitors.find_one({"doc_key": re.sub(r"\D", "", cpf)}, {"_id": 0, "id": 1}))
        n_visits = loop.run_until_complete(db.visits.count_documents({"visitor_id": v["id"]})) if v else 0
        assert n_visits == 0
        n_sync = loop.run_until_complete(db.sync_jobs.count_documents(
            {"device_name": {"$regex": "TEST Rejeitado E"}}))
        assert n_sync == 0
        pytest.cpf_e = cpf


# ============ F. Lista negra ============
class TestF_Blacklist:
    def test_blacklist_flow(self, admin, recep, oper):
        s, _ = admin
        clear_rate()
        cpf = valid_cpf(60060006)
        # 1) Create blacklisted visitor manually
        loop = _LOOP
        from models import new_id
        vid = new_id()
        loop.run_until_complete(db.visitors.insert_one({
            "id": vid, "name": "TEST Blacklist F", "doc_type": "cpf", "doc_number": cpf,
            "doc_key": re.sub(r"\D", "", cpf), "cpf": cpf, "cpf_digits": re.sub(r"\D", "", cpf),
            "blacklist": True, "blacklist_reason": "TEST reason", "enabled": True, "deleted": False,
            "created_at": datetime.now(timezone.utc).isoformat()}))

        host = pytest.selfreg_host
        # Submit via invite auto_approve → should remain pending because blacklist
        vt = s.get(f"{API}/visits/types?active=true").json()[0]
        inv = s.post(f"{API}/selfreg/invites", json={
            "host_company_id": pytest.selfreg_cid, "host_person_id": host["id"],
            "visit_type_id": vt["id"], "guest_name": "TEST BL Invite", "auto_approve": True}).json()
        token = inv["link"].rsplit("/", 1)[-1]
        sub = requests.post(f"{API}/public/selfreg/submit", json={
            "invite": token, "consent": True, "name": "TEST Blacklist F",
            "doc_type": "cpf", "doc_number": cpf, "photo": face_dataurl()})
        assert sub.status_code == 200
        assert sub.json()["status"] == "pendente", f"blacklist auto-approve must NOT release: got {sub.json()}"
        reg = loop.run_until_complete(db.self_registrations.find_one(
            {"status_token_hash": _sha(sub.json()["status_token"])}, {"_id": 0, "id": 1}))
        rid = reg["id"]

        # Host approve → 409
        tok = "TESTtokenF_" + os.urandom(6).hex()
        loop.run_until_complete(db.self_registrations.update_one(
            {"id": rid}, {"$set": {"decision_token_hash": _sha(tok)}}))
        r = requests.post(f"{API}/public/selfreg/decision/{tok}", json={"action": "approve"})
        assert r.status_code == 409

        # Reception approve → 409
        r = recep.post(f"{API}/selfreg/requests/{rid}/approve", json={})
        assert r.status_code == 409, f"reception blacklist approve must 409: {r.status_code} {r.text}"

        # Admin without justification → 409
        r = s.post(f"{API}/selfreg/requests/{rid}/approve", json={})
        assert r.status_code == 409

        # Admin with justification → 200
        r = s.post(f"{API}/selfreg/requests/{rid}/approve",
                   json={"blacklist_justification": "TEST autorizado administrativamente"})
        assert r.status_code == 200, r.text
        pytest.cpf_f = cpf
        pytest.vid_f = vid


# ============ G. Company manager scope ============
class TestG_ManagerScope:
    def test_create_manager_and_scoped(self, admin):
        s, _ = admin
        clear_rate()
        # Create second company for scope test
        import uuid
        cidB = str(uuid.uuid4())
        loop = _LOOP
        loop.run_until_complete(db.companies.insert_one({
            "id": cidB, "name": "TEST_EmpresaB", "enabled": True, "selfreg_enabled": False,
            "deleted": False, "created_at": datetime.now(timezone.utc).isoformat()}))
        pytest.cidB = cidB
        # Create manager user
        r = s.post(f"{API}/auth/users", json={
            "name": "TEST Gestor", "email": MGR["email"], "password": MGR["password"],
            "role": "company_manager", "company_ids": [pytest.selfreg_cid]})
        if r.status_code not in (200, 201, 409):
            pytest.skip(f"manager create: {r.status_code} {r.text}")
        if r.status_code == 409:
            # update existing
            users = s.get(f"{API}/auth/users").json()
            u = next((x for x in users if x["email"] == MGR["email"]), None)
            if u:
                s.put(f"{API}/auth/users/{u['id']}", json={"company_ids": [pytest.selfreg_cid], "password": MGR["password"]})
        mgr = login(MGR)[0]
        pytest.mgr = mgr

        # PUT companies/{empresaB} → 404
        r = mgr.put(f"{API}/selfreg/companies/{cidB}", json={"enabled": True})
        assert r.status_code == 404

        # Create a pending reg in company A → manager can see; manager cannot see empresaB stuff (there is none)
        r = mgr.get(f"{API}/selfreg/requests")
        assert r.status_code == 200
        items = r.json()
        for it in items:
            assert it["host_company_id"] == pytest.selfreg_cid, f"manager sees out-of-scope: {it['host_company_id']}"

        # Approve of out-of-scope request → 404
        # create one in empresaB manually
        from models import new_id
        rid_b = new_id()
        loop.run_until_complete(db.self_registrations.insert_one({
            "id": rid_b, "status": "pendente", "source": "link",
            "host_company_id": cidB, "host_company_name": "TEST_EmpresaB",
            "name": "TEST Fora", "doc_type": "cpf", "doc_number": valid_cpf(70070007),
            "host_person_id": "x", "host_name": "x", "created_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": datetime.now(timezone.utc) + timedelta(hours=24),
            "end_at": datetime.now(timezone.utc).isoformat(), "start_at": datetime.now(timezone.utc).isoformat(),
            "visit_type_id": "x", "visit_type_name": "x", "doc_key": "x"}))
        pytest.rid_b = rid_b
        r = mgr.post(f"{API}/selfreg/requests/{rid_b}/approve", json={})
        assert r.status_code == 404
        r = mgr.post(f"{API}/selfreg/requests/{rid_b}/reject", json={})
        assert r.status_code == 404


# ============ H. Agendamentos ============
class TestH_Scheduled:
    def test_scheduled_and_cancel(self, admin, recep):
        s, _ = admin
        clear_rate()
        # create pending + approve with future start to produce 'agendado'
        host = pytest.selfreg_host
        start = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
        r = requests.post(f"{API}/public/selfreg/submit", json={
            "code": pytest.selfreg_code, "consent": True, "name": "TEST Agendado H",
            "doc_type": "cpf", "doc_number": valid_cpf(80080008),
            "host_person_id": host["id"], "start_at": start, "photo": face_dataurl()})
        assert r.status_code == 200
        loop = _LOOP
        reg = loop.run_until_complete(db.self_registrations.find_one(
            {"status_token_hash": _sha(r.json()["status_token"])}, {"_id": 0, "id": 1}))
        ap = recep.post(f"{API}/selfreg/requests/{reg['id']}/approve", json={})
        assert ap.status_code == 200
        vid = ap.json()["visit_id"]
        # scheduled list should include it
        for days in (1, 7, 30):
            lst = s.get(f"{API}/visits/scheduled?days={days}").json()
            assert any(v["id"] == vid for v in lst), f"visit missing from scheduled?days={days}"
        # cancel
        c = s.post(f"{API}/visits/{vid}/cancel")
        assert c.status_code == 200, c.text
        # sync_jobs removal
        n = loop.run_until_complete(db.sync_jobs.count_documents({"person_id": {"$exists": True}}))
        assert n > 0
        # cannot cancel again
        c2 = s.post(f"{API}/visits/{vid}/cancel")
        assert c2.status_code == 400
        pytest.visit_h = vid


# ============ I. SMTP ausente ============
class TestI_NoSMTP:
    def test_info_otp_false_and_notifications_error(self):
        info = requests.get(f"{API}/public/selfreg/info", params={"code": pytest.selfreg_code}).json()
        assert info["otp"] is False
        # notifications table should have error entries from prior sends
        loop = _LOOP
        n = loop.run_until_complete(db.notifications.count_documents(
            {"error": {"$regex": "SMTP não configurado"}}))
        assert n >= 1, "expected 'SMTP não configurado' notifications but found 0"


# ============ J. Retenção ============
class TestJ_Retention:
    def test_retention_tick(self, admin):
        from models import new_id
        from selfreg_core import retention_tick
        loop = _LOOP
        now = datetime.now(timezone.utc)
        # (a) comum com visita finalizada há 40 dias
        vid1 = new_id()
        loop.run_until_complete(db.visitors.insert_one({
            "id": vid1, "name": "TEST RetA", "doc_type": "cpf", "doc_number": valid_cpf(91010001),
            "doc_key": re.sub(r"\D", "", valid_cpf(91010001)), "photo": "data:image/jpeg;base64,xxxx",
            "photo_thumb": "data:image/jpeg;base64,xx", "remember": False, "blacklist": False,
            "enabled": True, "deleted": False, "created_at": (now - timedelta(days=100)).isoformat()}))
        loop.run_until_complete(db.visits.insert_one({
            "id": new_id(), "visitor_id": vid1, "status": "finalizado",
            "end_at": (now - timedelta(days=40)).isoformat(),
            "ended_at": (now - timedelta(days=40)).isoformat()}))
        # (b) recorrente, 40 dias → mantém
        vid2 = new_id()
        loop.run_until_complete(db.visitors.insert_one({
            "id": vid2, "name": "TEST RetB", "doc_type": "cpf", "doc_number": valid_cpf(91020002),
            "doc_key": re.sub(r"\D", "", valid_cpf(91020002)), "photo": "data:image/jpeg;base64,xxxx",
            "photo_thumb": "", "remember": True, "blacklist": False,
            "enabled": True, "deleted": False, "created_at": (now - timedelta(days=100)).isoformat()}))
        loop.run_until_complete(db.visits.insert_one({
            "id": new_id(), "visitor_id": vid2, "status": "finalizado",
            "end_at": (now - timedelta(days=40)).isoformat(),
            "ended_at": (now - timedelta(days=40)).isoformat()}))
        # (c) recorrente, 13 meses → apaga
        vid3 = new_id()
        loop.run_until_complete(db.visitors.insert_one({
            "id": vid3, "name": "TEST RetC", "doc_type": "cpf", "doc_number": valid_cpf(91030003),
            "doc_key": re.sub(r"\D", "", valid_cpf(91030003)), "photo": "data:image/jpeg;base64,xxxx",
            "photo_thumb": "", "remember": True, "blacklist": False,
            "enabled": True, "deleted": False, "created_at": (now - timedelta(days=500)).isoformat()}))
        loop.run_until_complete(db.visits.insert_one({
            "id": new_id(), "visitor_id": vid3, "status": "finalizado",
            "end_at": (now - timedelta(days=400)).isoformat(),
            "ended_at": (now - timedelta(days=400)).isoformat()}))
        # (d) blacklist, antigo → nunca apaga
        vid4 = new_id()
        loop.run_until_complete(db.visitors.insert_one({
            "id": vid4, "name": "TEST RetD BL", "doc_type": "cpf", "doc_number": valid_cpf(91040004),
            "doc_key": re.sub(r"\D", "", valid_cpf(91040004)), "photo": "data:image/jpeg;base64,xxxx",
            "photo_thumb": "", "remember": False, "blacklist": True,
            "enabled": True, "deleted": False, "created_at": (now - timedelta(days=500)).isoformat()}))
        loop.run_until_complete(db.visits.insert_one({
            "id": new_id(), "visitor_id": vid4, "status": "finalizado",
            "end_at": (now - timedelta(days=400)).isoformat(),
            "ended_at": (now - timedelta(days=400)).isoformat()}))
        # (e) self_registration pendente expirado
        from models import new_id as nid
        rid_exp = nid()
        loop.run_until_complete(db.self_registrations.insert_one({
            "id": rid_exp, "status": "pendente", "name": "TEST RetE", "doc_type": "cpf",
            "doc_number": valid_cpf(91050005), "doc_key": "x",
            "host_company_id": "x", "host_company_name": "x", "host_person_id": "x", "host_name": "x",
            "visit_type_id": "x", "visit_type_name": "x",
            "start_at": now.isoformat(), "end_at": now.isoformat(),
            "created_at": (now - timedelta(hours=48)).isoformat(),
            "expires_at": now - timedelta(hours=1)}))
        pytest.ret_ids = [vid1, vid2, vid3, vid4, rid_exp]

        out = loop.run_until_complete(retention_tick(now=now))
        # Check
        a = loop.run_until_complete(db.visitors.find_one({"id": vid1}, {"_id": 0, "photo": 1}))
        assert a["photo"] == "", f"comum (40d) deveria ter photo apagada: {a}"
        b = loop.run_until_complete(db.visitors.find_one({"id": vid2}, {"_id": 0, "photo": 1}))
        assert b["photo"] != "", "recorrente 40d deveria manter"
        c = loop.run_until_complete(db.visitors.find_one({"id": vid3}, {"_id": 0, "photo": 1}))
        assert c["photo"] == "", "recorrente 13 meses deveria apagar"
        d = loop.run_until_complete(db.visitors.find_one({"id": vid4}, {"_id": 0, "photo": 1}))
        assert d["photo"] != "", "blacklist nunca apaga"
        e = loop.run_until_complete(db.self_registrations.find_one({"id": rid_exp}, {"_id": 0, "status": 1}))
        assert e["status"] == "expirado"


# ============ Cleanup ============
def test_zzz_cleanup(admin):
    s, _ = admin
    loop = _LOOP

    async def do():
        # restore company A to disabled selfreg (original) — admin test req says restore
        await db.companies.update_one({"id": pytest.selfreg_cid},
                                      {"$set": {"selfreg_enabled": False, "selfreg_code": ""}})
        await db.settings.update_one({"id": "selfreg"}, {"$set": {"site_enabled": False, "site_code": ""}})

        # delete TEST visitors
        await db.visitors.delete_many({"name": {"$regex": "^TEST "}})
        await db.visits.delete_many({"visitor_name": {"$regex": "^TEST "}})
        await db.visits.delete_many({"visitor_name": {"$regex": "TEST "}})
        await db.self_registrations.delete_many({"name": {"$regex": "^TEST"}})
        await db.selfreg_invites.delete_many({"guest_name": {"$regex": "^TEST"}})
        await db.companies.delete_many({"name": {"$regex": "^TEST_"}})
        await db.rate_hits.delete_many({})
        # Delete manager
        from models import new_id  # noqa
        u = await db.users.find_one({"email": MGR["email"]}, {"_id": 1})
        if u:
            await db.users.delete_one({"_id": u["_id"]})

    loop.run_until_complete(do())
    print("cleanup done")

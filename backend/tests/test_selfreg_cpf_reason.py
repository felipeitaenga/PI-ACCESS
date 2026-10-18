"""Autocadastro: só CPF, sem busca pública por CPF, conferência de foto e motivo da visita."""
import asyncio
import base64
import os
import uuid
from pathlib import Path

import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api"
ADMIN = {"email": "felipejferreira@gmail.com", "password": "NxAccess@2026"}
TAG = f"TEST_CPF_{uuid.uuid4().hex[:6]}"
_LOOP = asyncio.new_event_loop()
db = AsyncIOMotorClient(os.environ["MONGO_URL"], io_loop=_LOOP)[os.environ["DB_NAME"]]
FACE = "data:image/jpeg;base64," + base64.b64encode((Path(__file__).parent / "fixtures" / "face.jpg").read_bytes()).decode()


def run(c):
    return _LOOP.run_until_complete(c)


def cpf(seed):
    d = [int(x) for x in str(seed).zfill(9)]
    for _ in range(2):
        s = sum((len(d) + 1 - j) * v for j, v in enumerate(d))
        d.append(((s * 10) % 11) % 10)
    return "".join(map(str, d))


KNOWN = cpf(733000001)


@pytest.fixture(scope="module")
def ctx():
    s = requests.Session()
    s.headers["Authorization"] = "Bearer " + s.post(f"{API}/auth/login", json=ADMIN, timeout=20).json()["access_token"]
    vt = s.get(f"{API}/visits/types?active=true").json()[0]
    comp = host = None
    for c in s.get(f"{API}/selfreg/companies").json():
        host = run(db.people.find_one({"company_id": c["id"], "status": "ativo", "deleted": {"$ne": True},
                                       "can_authorize_visits": {"$ne": False}}, {"_id": 0, "id": 1}))
        if host:
            comp = c
            break
    if not host:
        pytest.skip("sem anfitrião")
    s.put(f"{API}/selfreg/companies/{comp['id']}", json={"enabled": True, "visit_type_id": vt["id"]})
    code = next(c for c in s.get(f"{API}/selfreg/companies").json() if c["id"] == comp["id"])["selfreg_code"]
    run(db.visitors.insert_one({"id": f"{TAG}-v", "name": f"{TAG} Mariana Souza", "doc_type": "cpf", "doc_number": KNOWN,
                                "doc_key": KNOWN, "origin_company": "TEST Origem", "phone": "(11) 99999-0000",
                                "deleted": False, "enabled": True}))
    run(db.rate_hits.delete_many({}))
    yield s, code, host
    run(db.self_registrations.delete_many({"doc_key": {"$in": [KNOWN, cpf(733000002)]}}))
    run(db.visitors.delete_many({"$or": [{"id": f"{TAG}-v"}, {"name": {"$regex": f"^{TAG}"}}]}))
    run(db.rate_hits.delete_many({}))
    s.put(f"{API}/selfreg/companies/{comp['id']}", json={"enabled": bool(comp.get("selfreg_enabled")),
                                                          "visit_type_id": comp.get("selfreg_visit_type_id") or vt["id"]})


def test_info_only_cpf(ctx):
    _, code, _ = ctx
    assert requests.get(f"{API}/public/selfreg/info?code={code}", timeout=10).json()["doc_types"] == ["cpf"]


def test_public_lookup_removed(ctx):
    _, code, _ = ctx
    r = requests.post(f"{API}/public/selfreg/lookup", json={"code": code, "doc_number": KNOWN}, timeout=10)
    assert r.status_code in (404, 405)
    assert "Mariana" not in r.text


def test_submit_rg_rejected(ctx):
    _, code, host = ctx
    r = requests.post(f"{API}/public/selfreg/submit", json={"code": code, "consent": True, "name": "Fulano de Tal", "doc_type": "rg",
                                                            "doc_number": "123456789", "photo": FACE, "host_person_id": host["id"]}, timeout=30)
    assert r.status_code == 422 and "doc_type" in r.json()["detail"]["fields"]


def test_name_required(ctx):
    _, code, host = ctx
    run(db.rate_hits.delete_many({}))
    r = requests.post(f"{API}/public/selfreg/submit", json={"code": code, "consent": True, "name": "", "doc_type": "cpf",
                                                            "doc_number": KNOWN, "photo": FACE, "host_person_id": host["id"]}, timeout=30)
    assert r.status_code == 422 and "name" in r.json()["detail"]["fields"]


def test_known_cpf_flags_identity_check_and_keeps_reason(ctx):
    s, code, host = ctx
    run(db.rate_hits.delete_many({}))
    r = requests.post(f"{API}/public/selfreg/submit", json={"code": code, "consent": True, "name": "Outra Pessoa", "doc_type": "cpf",
                                                            "doc_number": KNOWN, "photo": FACE, "host_person_id": host["id"],
                                                            "visit_reason": "Reunião comercial"}, timeout=30)
    assert r.status_code == 200, r.text
    assert "Mariana" not in r.text
    reg = run(db.self_registrations.find_one({"doc_key": KNOWN, "status": "pendente"}, {"_id": 0}))
    assert reg["name"] == "Outra Pessoa" and reg["visit_reason"] == "Reunião comercial"
    assert reg["doc_known"] is True and reg["owner_verified"] is False
    det = s.get(f"{API}/selfreg/requests/{reg['id']}").json()
    assert det["existing_name"] == f"{TAG} Mariana Souza" and "existing_photo" in det

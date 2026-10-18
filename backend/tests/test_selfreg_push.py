"""Web Push do autocadastro: chave pública, inscrição só com texto e envio na decisão."""
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
TAG = f"TEST_PUSH_{uuid.uuid4().hex[:6]}"
_LOOP = asyncio.new_event_loop()
db = AsyncIOMotorClient(os.environ["MONGO_URL"], io_loop=_LOOP)[os.environ["DB_NAME"]]
FACE = "data:image/jpeg;base64," + base64.b64encode((Path(__file__).parent / "fixtures" / "face.jpg").read_bytes()).decode()
SUB = {"endpoint": "https://fcm.googleapis.com/fcm/send/test-endpoint-invalido",
       "keys": {"p256dh": "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QTpQtUbVlUls0VJXg7A8u-Ts1XbjhazAkj7I99e8QcYP7DkM",
                "auth": "tBHItJI5svbpez7KI4CCXg"}}


def run(c):
    return _LOOP.run_until_complete(c)


def cpf(seed):
    d = [int(x) for x in str(seed).zfill(9)]
    for _ in range(2):
        s = sum((len(d) + 1 - j) * v for j, v in enumerate(d))
        d.append(((s * 10) % 11) % 10)
    return "".join(map(str, d))


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
    run(db.rate_hits.delete_many({}))
    r = requests.post(f"{API}/public/selfreg/submit", json={"code": code, "consent": True, "name": f"{TAG} Pessoa",
                                                            "doc_type": "cpf", "doc_number": cpf(732000001), "photo": FACE,
                                                            "host_person_id": host["id"]}, timeout=30)
    assert r.status_code == 200, r.text
    yield s, r.json()["status_token"]
    reg = run(db.self_registrations.find_one({"name": f"{TAG} Pessoa"}, {"_id": 0, "id": 1, "visitor_id": 1}))
    if reg:
        run(db.notifications.delete_many({"ref": reg["id"]}))
        if reg.get("visitor_id"):
            run(db.visits.delete_many({"visitor_id": reg["visitor_id"]}))
            run(db.visitors.delete_many({"id": reg["visitor_id"]}))
    run(db.self_registrations.delete_many({"name": f"{TAG} Pessoa"}))
    run(db.rate_hits.delete_many({}))
    s.put(f"{API}/selfreg/companies/{comp['id']}", json={"enabled": bool(comp.get("selfreg_enabled")),
                                                          "visit_type_id": comp.get("selfreg_visit_type_id") or vt["id"]})


def test_push_key_public():
    d = requests.get(f"{API}/public/selfreg/push-key", timeout=10).json()
    assert d["enabled"] is True and len(d["key"]) > 40


def test_subscribe_rejects_objects_and_bad_endpoint(ctx):
    _, tok = ctx
    bad = {"endpoint": {"$ne": None}, "keys": {"p256dh": {"$gt": ""}, "auth": "x"}}
    assert requests.post(f"{API}/public/selfreg/push/{tok}", json=bad, timeout=10).status_code == 400
    http = {**SUB, "endpoint": "http://exemplo.com/x"}
    assert requests.post(f"{API}/public/selfreg/push/{tok}", json=http, timeout=10).status_code == 400
    assert requests.post(f"{API}/public/selfreg/push/token-inexistente", json=SUB, timeout=10).status_code == 404


def test_subscribe_and_push_on_approval(ctx):
    s, tok = ctx
    assert requests.post(f"{API}/public/selfreg/push/{tok}", json=SUB, timeout=10).status_code == 200
    reg = run(db.self_registrations.find_one({"name": f"{TAG} Pessoa"}, {"_id": 0}))
    assert reg["push_sub"]["endpoint"] == SUB["endpoint"]
    r = s.post(f"{API}/selfreg/requests/{reg['id']}/approve", json={})
    assert r.status_code == 200, r.text
    rec = run(db.notifications.find_one({"ref": reg["id"], "channel": "push"}, {"_id": 0}))
    assert rec and rec["subject"] == "Visita aprovada"


def test_status_polling_not_rate_limited(ctx):
    _, tok = ctx
    run(db.rate_hits.delete_many({}))
    codes = {requests.get(f"{API}/public/selfreg/status/{tok}", timeout=10).status_code for _ in range(70)}
    assert codes == {200}

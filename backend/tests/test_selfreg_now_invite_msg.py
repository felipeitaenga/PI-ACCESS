"""Autocadastro: solicitação vale do envio (sem agendamento), início na aprovação e mensagem do convite."""
import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api"
ADMIN = {"email": "felipejferreira@gmail.com", "password": "NxAccess@2026"}
TAG = f"TEST_NOW_{uuid.uuid4().hex[:6]}"
_LOOP = asyncio.new_event_loop()
db = AsyncIOMotorClient(os.environ["MONGO_URL"], io_loop=_LOOP)[os.environ["DB_NAME"]]


def run(c):
    return _LOOP.run_until_complete(c)


def cpf(seed):
    d = [int(x) for x in str(seed).zfill(9)]
    for _ in range(2):
        s = sum((len(d) + 1 - j) * v for j, v in enumerate(d))
        d.append(((s * 10) % 11) % 10)
    return "".join(map(str, d))


def face():
    import base64
    from pathlib import Path
    data = (Path(__file__).parent / "fixtures" / "face.jpg").read_bytes()
    return "data:image/jpeg;base64," + base64.b64encode(data).decode()


@pytest.fixture(scope="module")
def ctx():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=ADMIN, timeout=20)
    s.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    comps = s.get(f"{API}/selfreg/companies").json()
    vt = s.get(f"{API}/visits/types?active=true").json()[0]
    host = comp = None
    for c in comps:
        host = run(db.people.find_one({"company_id": c["id"], "status": "ativo", "deleted": {"$ne": True},
                                       "can_authorize_visits": {"$ne": False}}, {"_id": 0, "id": 1, "name": 1}))
        if host:
            comp = c
            break
    if not host:
        pytest.skip("sem anfitrião")
    prev = {"enabled": comp.get("selfreg_enabled"), "vt": comp.get("selfreg_visit_type_id")}
    s.put(f"{API}/selfreg/companies/{comp['id']}", json={"enabled": True, "visit_type_id": vt["id"]})
    code = next(c for c in s.get(f"{API}/selfreg/companies").json() if c["id"] == comp["id"])["selfreg_code"]
    yield s, comp, host, vt, code
    run(db.self_registrations.delete_many({"name": {"$regex": f"^{TAG}"}}))
    vids = [v["id"] for v in run(db.visitors.find({"name": {"$regex": f"^{TAG}"}}, {"id": 1}).to_list(50))]
    run(db.visits.delete_many({"visitor_id": {"$in": vids}}))
    run(db.visitors.delete_many({"id": {"$in": vids}}))
    run(db.selfreg_invites.delete_many({"guest_name": {"$regex": f"^{TAG}"}}))
    run(db.rate_hits.delete_many({}))
    s.put(f"{API}/selfreg/companies/{comp['id']}", json={"enabled": bool(prev["enabled"]), "visit_type_id": prev["vt"] or vt["id"]})


def _submit(code, host, n, **extra):
    run(db.rate_hits.delete_many({}))
    body = {"code": code, "consent": True, "name": f"{TAG} Pessoa {n}", "doc_type": "cpf", "doc_number": cpf(731000000 + n),
            "photo": face(), "host_person_id": host["id"], **extra}
    return requests.post(f"{API}/public/selfreg/submit", json=body, timeout=30)


def test_submit_ignores_scheduled_start(ctx):
    s, comp, host, vt, code = ctx
    future = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    r = _submit(code, host, 1, start_at=future)
    assert r.status_code == 200, r.text
    reg = run(db.self_registrations.find_one({"name": f"{TAG} Pessoa 1"}, {"_id": 0}))
    start = datetime.fromisoformat(reg["start_at"])
    assert abs((start - datetime.now(timezone.utc)).total_seconds()) < 120


def test_approval_starts_visit_now_keeping_duration(ctx):
    s, comp, host, vt, code = ctx
    assert _submit(code, host, 2).status_code == 200
    reg = run(db.self_registrations.find_one({"name": f"{TAG} Pessoa 2"}, {"_id": 0}))
    old_start = datetime.now(timezone.utc) - timedelta(hours=1)
    dur = datetime.fromisoformat(reg["end_at"]) - datetime.fromisoformat(reg["start_at"])
    run(db.self_registrations.update_one({"id": reg["id"]}, {"$set": {"start_at": old_start.isoformat(),
                                                                         "end_at": (old_start + dur).isoformat()}}))
    r = s.post(f"{API}/selfreg/requests/{reg['id']}/approve", json={})
    assert r.status_code == 200, r.text
    v = run(db.visits.find_one({"id": r.json()["visit_id"]}, {"_id": 0, "start_at": 1, "end_at": 1}))
    vs, ve = datetime.fromisoformat(v["start_at"]), datetime.fromisoformat(v["end_at"])
    assert abs((vs - datetime.now(timezone.utc)).total_seconds()) < 120
    assert abs(((ve - vs) - dur).total_seconds()) < 120


def test_invite_returns_message_with_details(ctx):
    s, comp, host, vt, code = ctx
    r = s.post(f"{API}/selfreg/invites", json={"host_company_id": comp["id"], "host_person_id": host["id"],
                                                 "visit_type_id": vt["id"], "guest_name": f"{TAG} Convidado",
                                                 "notes": "Trazer EPI", "auto_approve": False})
    assert r.status_code == 200, r.text
    d = r.json()
    msg = d["message"]
    for part in (comp["name"], host["name"], vt["name"], "Trazer EPI", d["link"], "Data/hora:"):
        assert part in msg, part

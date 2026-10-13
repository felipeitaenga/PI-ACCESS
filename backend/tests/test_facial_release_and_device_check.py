"""v1.4.6 — release_visitor (mantém no facial quando há outra visita ativa) + /visits/{id}/device-check.

Rode: cd /app/backend && python -m pytest -q -o addopts='' tests/test_facial_release_and_device_check.py
"""
import asyncio
import base64
import hashlib
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import db  # noqa: E402

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://nx-access-demo.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"
ADMIN = {"email": "felipejferreira@gmail.com", "password": "NxAccess@2026"}
RECEP = {"email": "recepcao@nxaccess.com", "password": "Recepcao@2026"}
VIEWER = {"email": "leitura@nxaccess.com", "password": "Leitura@2026"}
FACE = Path("/tmp/face.jpg")


def _bcrypt(pw):
    import bcrypt
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def login(creds):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=creds, timeout=20)
    assert r.status_code == 200, f"login {creds['email']}: {r.status_code} {r.text}"
    s.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    return s, r.json()


def face_dataurl():
    with open(FACE, "rb") as f:
        return "data:image/jpeg;base64," + base64.b64encode(f.read()).decode()


def valid_cpf(seed):
    digits = [int(x) for x in str(seed).zfill(9)]
    for _ in range(2):
        s = sum((len(digits) + 1 - j) * d for j, d in enumerate(digits))
        digits.append(((s * 10) % 11) % 10)
    return "".join(str(d) for d in digits)


async def _reset():
    await db.rate_hits.delete_many({})


@pytest.fixture(scope="module")
def loop():
    lo = asyncio.new_event_loop()
    asyncio.set_event_loop(lo)
    yield lo
    lo.close()


@pytest.fixture(scope="module", autouse=True)
def _clear_rate(loop):
    loop.run_until_complete(_reset())
    yield
    loop.run_until_complete(_reset())


@pytest.fixture(scope="module")
def admin():
    return login(ADMIN)[0]


@pytest.fixture(scope="module")
def recep():
    return login(RECEP)[0]


@pytest.fixture(scope="module")
def viewer():
    return login(VIEWER)[0]


@pytest.fixture(scope="module")
def ctx(admin, loop):
    """Pega visit_type ativo, empresa com host ativo que autoriza visitas."""
    vt = admin.get(f"{API}/visits/types?active=true").json()
    assert vt, "need at least 1 active visit_type"

    async def pick():
        people = await db.people.find({"status": "ativo", "can_authorize_visits": {"$ne": False}, "deleted": {"$ne": True}},
                                      {"_id": 0, "id": 1, "name": 1, "company_id": 1}).to_list(500)
        assert people, "need an active host"
        host = next((p for p in people if p.get("company_id")), None)
        assert host, "need a host with a company"
        comp = await db.companies.find_one({"id": host["company_id"]}, {"_id": 0, "id": 1, "name": 1})
        return host, comp
    host, comp = loop.run_until_complete(pick())
    return {"visit_type_id": vt[0]["id"], "host": host, "comp": comp}


@pytest.fixture(scope="module")
def visitor_pair(recep, ctx, loop):
    """Cria 2 visitas presentes para o MESMO documento."""
    doc = valid_cpf(98765432)
    photo = face_dataurl()
    now = datetime.now(timezone.utc)
    end = (now + timedelta(hours=4)).isoformat()
    created = []
    for i in range(2):
        body = {
            "visit_type_id": ctx["visit_type_id"],
            "host_company_id": ctx["comp"]["id"],
            "host_person_id": ctx["host"]["id"],
            "name": "TEST_ FacialKeep Visitor",
            "doc_type": "cpf",
            "doc_number": doc,
            "visitor_company": "TEST_VC",
            "identifier": {"type": "facial"},
            "photo": photo if i == 0 else "",
            "start_at": now.isoformat(),
            "end_at": end,
        }
        r = recep.post(f"{API}/visits", json=body, timeout=30)
        assert r.status_code == 200, r.text
        created.append(r.json())
    v1, v2 = created
    assert v1["visitor"]["id"] == v2["visitor"]["id"], "same visitor on both visits"
    assert v1["visit"]["status"] == "presente"
    yield {"doc": doc, "visitor_id": v1["visitor"]["id"], "visit1": v1["visit"]["id"], "visit2": v2["visit"]["id"]}

    async def cleanup():
        vid = v1["visitor"]["id"]
        await db.visits.delete_many({"visitor_id": vid})
        await db.visitors.delete_many({"id": vid})
        await db.visit_history.delete_many({"visitor_id": vid})
        await db.sync_jobs.delete_many({"person_id": vid})
        await db.mqtt_commands.delete_many({"payload.info.customId": vid})
        await db.audit.delete_many({"entity": "visit", "entity_id": {"$in": [v1["visit"]["id"], v2["visit"]["id"]]}})
    loop.run_until_complete(cleanup())


# ---------- A) release_visitor: mantém quando há outra visita ativa ----------
def _latest_sync_job(loop, visitor_id):
    async def q():
        return await db.sync_jobs.find_one({"person_id": visitor_id}, {"_id": 0}, sort=[("started_at", -1)])
    return loop.run_until_complete(q())


def test_end_visit_with_other_active_keeps_in_facial(recep, visitor_pair, loop):
    r = recep.post(f"{API}/visits/{visitor_pair['visit1']}/end", timeout=20)
    assert r.status_code == 200, r.text
    job = _latest_sync_job(loop, visitor_pair["visitor_id"])
    assert job, "sync_job not registered"
    assert job["device_name"].startswith("Fim da visita (mantido: outra visita ativa)"), job["device_name"]
    # a visita 2 continua presente
    async def check():
        v2 = await db.visits.find_one({"id": visitor_pair["visit2"]}, {"_id": 0})
        assert v2["status"] == "presente"
    loop.run_until_complete(check())


def test_end_second_visit_removes_from_facial(recep, visitor_pair, loop):
    r = recep.post(f"{API}/visits/{visitor_pair['visit2']}/end", timeout=20)
    assert r.status_code == 200, r.text
    job = _latest_sync_job(loop, visitor_pair["visitor_id"])
    assert job and job["device_name"].startswith("Fim da visita:"), job["device_name"]
    assert "mantido" not in job["device_name"]


# ---------- B) /visits/{id}/device-check ----------
@pytest.fixture(scope="module")
def device_check_visit(recep, ctx, loop):
    doc = valid_cpf(44332211)
    body = {
        "visit_type_id": ctx["visit_type_id"],
        "host_company_id": ctx["comp"]["id"],
        "host_person_id": ctx["host"]["id"],
        "name": "TEST_ DevCheck Visitor",
        "doc_type": "cpf", "doc_number": doc,
        "identifier": {"type": "facial"},
        "photo": face_dataurl(),
    }
    r = recep.post(f"{API}/visits", json=body, timeout=30)
    assert r.status_code == 200, r.text
    vid = r.json()["visitor"]["id"]
    visit_id = r.json()["visit"]["id"]
    yield {"visit_id": visit_id, "visitor_id": vid}

    async def cleanup():
        await db.visits.delete_many({"visitor_id": vid})
        await db.visitors.delete_many({"id": vid})
        await db.visit_history.delete_many({"visitor_id": vid})
        await db.sync_jobs.delete_many({"person_id": vid})
        await db.mqtt_commands.delete_many({"payload.info.customId": vid})
    loop.run_until_complete(cleanup())


def test_device_check_shape(recep, device_check_visit):
    r = recep.post(f"{API}/visits/{device_check_visit['visit_id']}/device-check", timeout=20)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["visitor_id"] == device_check_visit["visitor_id"]
    assert d["visitor_name"] == "TEST_ DevCheck Visitor"
    assert d["has_photo"] is True
    # No preview, se houver controllers beward_mqtt (seed), devem estar offline sem heartbeat (sem broker real).
    assert isinstance(d["controllers"], list)
    for c in d["controllers"]:
        assert c.get("online") is False
        assert c.get("error") == "Facial offline ou broker MQTT desconectado"


def test_device_check_offline_beward_mqtt(recep, device_check_visit, loop):
    """Com um TEST_ controller brand=beward_mqtt sem heartbeat, retorna 'Facial offline...' e NÃO enfileira nada."""
    cid = "TEST_CTRL_BEWARD_MQTT"

    async def setup():
        await db.controllers.delete_many({"id": cid})
        await db.controllers.insert_one({
            "id": cid, "name": "TEST_ Beward MQTT", "brand": "beward_mqtt",
            "beward_device_id": "TEST_DEVID", "enabled": True, "deleted": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        before = await db.mqtt_commands.count_documents({"status": "queued"})
        return before

    async def teardown(before):
        after = await db.mqtt_commands.count_documents({"status": "queued"})
        await db.controllers.delete_many({"id": cid})
        await db.mqtt_commands.delete_many({"device_id": "TEST_DEVID"})
        return before, after

    before = loop.run_until_complete(setup())
    try:
        r = recep.post(f"{API}/visits/{device_check_visit['visit_id']}/device-check", timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        mine = [c for c in d["controllers"] if c["controller_id"] == cid]
        assert len(mine) == 1, d["controllers"]
        c0 = mine[0]
        assert c0.get("online") is False
        assert c0.get("error") == "Facial offline ou broker MQTT desconectado", c0
    finally:
        before2, after = loop.run_until_complete(teardown(before))
        assert after == before2, f"mqtt_commands queued cresceu: {before2} → {after}"


def test_device_check_viewer_403(viewer, device_check_visit):
    r = viewer.post(f"{API}/visits/{device_check_visit['visit_id']}/device-check", timeout=20)
    assert r.status_code == 403, r.status_code


def test_device_check_manager_out_of_scope_404(admin, device_check_visit, ctx, loop):
    """Gestor sem a empresa host da visita → 404 (find_scoped)."""
    email = "TEST_mgr_devcheck@teste.com"

    async def pick_other():
        comp = await db.companies.find_one({"id": {"$ne": ctx["comp"]["id"]}, "deleted": {"$ne": True}}, {"_id": 0, "id": 1})
        if comp:
            return comp["id"], False
        await db.companies.insert_one({"id": "TEST_OTHER_COMP", "name": "TEST_ Other", "deleted": False,
                                       "created_at": datetime.now(timezone.utc).isoformat()})
        return "TEST_OTHER_COMP", True
    other, created_comp = loop.run_until_complete(pick_other())
    # cria o gestor via API admin
    admin.post(f"{API}/auth/users", json={
        "email": email, "password": "TEST_Mgr@2026", "name": "TEST_ Mgr",
        "role": "company_manager", "site_ids": [], "company_ids": [other],
    }, timeout=20)
    try:
        mgr, _ = login({"email": email, "password": "TEST_Mgr@2026"})
        r = mgr.post(f"{API}/visits/{device_check_visit['visit_id']}/device-check", timeout=20)
        assert r.status_code == 404, f"{r.status_code} {r.text}"
    finally:
        async def cleanup():
            await db.users.delete_many({"email": email})
            if created_comp:
                await db.companies.delete_many({"id": "TEST_OTHER_COMP"})
        loop.run_until_complete(cleanup())

"""Isolamento do perfil Gestor de empresa: empresas A e B, um gestor de cada."""
import os
import uuid
import pytest
import requests
from pymongo import MongoClient

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
ADMIN = ("felipejferreira@gmail.com", "NxAccess@2026")
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
TAG = "TEST_SCOPE_" + uuid.uuid4().hex[:6]


def login(email, pwd):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": pwd}, timeout=20)
    assert r.status_code == 200, r.text
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    s.token = r.json()["access_token"]
    return s


def _cpf(seed):
    n = [int(x) for x in f"{seed:09d}"[-9:]]
    for k in (10, 11):
        d = (sum(a * b for a, b in zip(n, range(k, 1, -1))) * 10) % 11 % 10
        n.append(d)
    return "".join(map(str, n))


@pytest.fixture(scope="module")
def env():
    adm = login(*ADMIN)
    cats = adm.get(f"{BASE}/access/categories/all").json()
    cat_a, cat_b = cats[0]["id"], cats[1]["id"]
    vtype = adm.get(f"{BASE}/visits/types").json()[0]["id"]
    comps = {}
    for k, cat in (("A", cat_a), ("B", cat_b)):
        r = adm.post(f"{BASE}/org/companies", json={"name": f"{TAG} {k}", "type": "propria", "enabled": True,
                                                   "allowed_category_ids": [cat], "allowed_visit_type_ids": [vtype]})
        assert r.status_code == 200, r.text
        comps[k] = r.json()["id"]
    mgr, people, visits = {}, {}, {}
    for i, k in enumerate(("A", "B")):
        email = f"{TAG.lower()}_{k.lower()}@teste.com"
        r = adm.post(f"{BASE}/auth/users", json={"email": email, "password": "Gestor@2026", "name": f"{TAG} Gestor {k}",
                                                 "role": "company_manager", "company_ids": [comps[k]]})
        assert r.status_code == 200, r.text
        r = adm.post(f"{BASE}/registry/people", json={"person_type": "funcionario", "name": f"{TAG} Pessoa {k}",
                                                      "doc_type": "cpf", "doc_number": _cpf(int(uuid.uuid4().int % 10**9)),
                                                      "company_id": comps[k], "category_ids": [cat_a if k == "A" else cat_b],
                                                      "can_authorize_visits": True})
        assert r.status_code == 200, r.text
        people[k] = r.json()["person"]["id"]
        r = adm.post(f"{BASE}/visits", json={"visit_type_id": vtype, "host_company_id": comps[k], "host_person_id": people[k],
                                             "name": f"{TAG} Visitante {k}", "doc_type": "outro", "doc_number": f"{TAG}{k}",
                                             "identifier": {"type": "qrcode"}})
        assert r.status_code == 200, r.text
        visits[k] = r.json()["visit"]
        db.access_events.insert_one({"id": f"{TAG}-ev-{k}", "person_id": people[k], "person_name": f"{TAG} Pessoa {k}",
                                     "company_id": comps[k], "timestamp": "2099-01-01T00:00:00+00:00", "access_result": "granted"})
        mgr[k] = login(email, "Gestor@2026")
    yield {"adm": adm, "comps": comps, "mgr": mgr, "people": people, "visits": visits, "cat_a": cat_a, "cat_b": cat_b}
    for v in visits.values():
        adm.post(f"{BASE}/visits/{v['id']}/end")
    vids = [v["visitor_id"] for v in visits.values()]
    pids = list(people.values())
    db.visits.delete_many({"visitor_id": {"$in": vids}})
    db.visitors.delete_many({"id": {"$in": vids}})
    db.visit_history.delete_many({"visitor_id": {"$in": vids}})
    db.people.delete_many({"id": {"$in": pids}})
    db.identifiers.delete_many({"person_id": {"$in": pids}})
    db.sync_jobs.delete_many({"person_id": {"$in": pids + vids}})
    db.mqtt_commands.delete_many({"status": "queued", "payload.info.customId": {"$in": pids + vids}})
    db.mqtt_commands.delete_many({"status": "queued", "payload.info.customId": {"$elemMatch": {"$in": pids + vids}}})
    db.access_events.delete_many({"$or": [{"id": {"$regex": f"^{TAG}"}}, {"person_id": {"$in": pids + vids}}]})
    db.companies.delete_many({"id": {"$in": list(comps.values())}})
    db.users.delete_many({"email": {"$regex": f"^{TAG.lower()}"}})


def test_lists_only_own(env):
    a, comps = env["mgr"]["A"], env["comps"]
    assert [c["id"] for c in a.get(f"{BASE}/registry/companies").json()] == [comps["A"]]
    ids = [p["id"] for p in a.get(f"{BASE}/registry/people?limit=200").json()["items"]]
    assert env["people"]["A"] in ids and env["people"]["B"] not in ids
    assert all(p["company_id"] == comps["A"] for p in a.get(f"{BASE}/registry/people?company_id={comps['B']}").json()["items"])
    ev = a.get(f"{BASE}/events?limit=200").json()["items"]
    assert ev and all(e.get("company_id") == comps["A"] for e in ev)
    rep = a.get(f"{BASE}/reports/access").json()["items"]
    assert all(e.get("company_id") == comps["A"] for e in rep)
    names = [v["name"] for v in a.get(f"{BASE}/visits/visitor-search?q={TAG}").json()]
    assert f"{TAG} Visitante A" in names and f"{TAG} Visitante B" not in names
    assert all(v["host_company_id"] == comps["A"] for v in a.get(f"{BASE}/visits/present").json())
    vis = [v["id"] for v in a.get(f"{BASE}/registry/visitors").json()["items"]]
    assert env["visits"]["A"]["visitor_id"] in vis and env["visits"]["B"]["visitor_id"] not in vis


def test_404_on_other_company_ids(env):
    a, b = env["mgr"]["A"], env
    pb, vb = b["people"]["B"], b["visits"]["B"]
    assert a.get(f"{BASE}/registry/people/{pb}").status_code == 404
    assert a.put(f"{BASE}/registry/people/{pb}", json={"name": "x"}).status_code == 404
    assert a.get(f"{BASE}/registry/visitors/{vb['visitor_id']}").status_code == 404
    assert a.get(f"{BASE}/visits/visitor/{vb['visitor_id']}/prefill").status_code == 404
    assert a.post(f"{BASE}/visits/{vb['id']}/end").status_code == 404
    assert a.post(f"{BASE}/registry/people/bulk", json={"ids": [pb], "action": "block"}).status_code == 404


def test_403_on_config_routes(env):
    a = env["mgr"]["A"]
    for m, p in (("get", "/auth/users"), ("get", "/admin/settings"), ("get", "/admin/audit"), ("get", "/equipment/controllers"),
                 ("get", "/structure/sites"), ("get", "/integrations/mqtt"), ("post", "/access/categories"),
                 ("get", "/people/export/csv"), ("delete", f"/registry/people/{env['people']['A']}"), ("get", "/alarms")):
        assert getattr(a, m)(f"{BASE}{p}").status_code == 403, p
    assert a.post(f"{BASE}/equipment/access-points/qualquer/open", json={}).status_code == 403
    assert a.post(f"{BASE}/auth/users", json={"email": "x@x.com", "password": "12345678", "name": "x", "role": "admin"}).status_code == 403


def test_only_allowed_categories(env):
    a, comps = env["mgr"]["A"], env["comps"]
    cats = [c["id"] for c in a.get(f"{BASE}/access/categories/all").json()]
    assert cats == [env["cat_a"]]
    body = {"person_type": "funcionario", "name": f"{TAG} Nova", "doc_type": "outro", "doc_number": f"{TAG}N",
            "company_id": comps["A"], "category_ids": [env["cat_b"]]}
    r = a.post(f"{BASE}/registry/people", json=body)
    assert r.status_code == 422 and "category_ids" in r.json()["detail"]["fields"]
    r = a.post(f"{BASE}/registry/people", json={**body, "company_id": comps["B"], "category_ids": [env["cat_a"]]})
    assert r.status_code == 422
    r = a.post(f"{BASE}/registry/people", json={**body, "category_ids": [env["cat_a"]]})
    assert r.status_code == 200, r.text
    env["people"]["A2"] = r.json()["person"]["id"]


def test_ws_filter():
    from scope import ws_visible
    u = {"role": "company_manager", "company_ids": ["A"]}
    assert ws_visible(u, {"type": "access_event", "data": {"company_id": "A"}})
    assert not ws_visible(u, {"type": "access_event", "data": {"company_id": "B"}})
    assert not ws_visible(u, {"type": "alarm", "data": {}})
    assert ws_visible({"role": "admin"}, {"type": "alarm", "data": {}})

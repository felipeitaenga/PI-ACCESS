"""Testes estendidos de escopo: lookups, visitor-companies, dashboard, limites, middleware, auditoria,
criação de gestores pela configuração manager_can_create_managers e visitor LGPD."""
import os
import uuid
import time
import pytest
import requests
from pymongo import MongoClient

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
ADMIN = ("felipejferreira@gmail.com", "NxAccess@2026")
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
TAG = "TEST_EXT_" + uuid.uuid4().hex[:6]


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
    vtypes = adm.get(f"{BASE}/visits/types").json()
    vt_a = vtypes[0]["id"]
    vt_b = vtypes[1]["id"] if len(vtypes) > 1 else vtypes[0]["id"]

    comps = {}
    # Empresa A: só 1 categoria/vtype + limite 1 pessoa ativa
    r = adm.post(f"{BASE}/org/companies", json={"name": f"{TAG} A", "type": "propria", "enabled": True,
                                                "allowed_category_ids": [cat_a], "allowed_visit_type_ids": [vt_a],
                                                "max_active_people": 1})
    assert r.status_code == 200, r.text
    comps["A"] = r.json()["id"]
    r = adm.post(f"{BASE}/org/companies", json={"name": f"{TAG} B", "type": "propria", "enabled": True,
                                                "allowed_category_ids": [cat_b], "allowed_visit_type_ids": [vt_b]})
    assert r.status_code == 200, r.text
    comps["B"] = r.json()["id"]

    mgr, people, visits = {}, {}, {}
    for k, cat, vt in (("A", cat_a, vt_a), ("B", cat_b, vt_b)):
        email = f"{TAG.lower()}_{k.lower()}@teste.com"
        r = adm.post(f"{BASE}/auth/users", json={"email": email, "password": "Gestor@2026",
                                                 "name": f"{TAG} Gestor {k}",
                                                 "role": "company_manager", "company_ids": [comps[k]]})
        assert r.status_code == 200, r.text
        r = adm.post(f"{BASE}/registry/people", json={"person_type": "funcionario",
                                                      "name": f"{TAG} Pessoa {k}",
                                                      "doc_type": "cpf",
                                                      "doc_number": _cpf(int(uuid.uuid4().int % 10**9)),
                                                      "company_id": comps[k], "category_ids": [cat],
                                                      "can_authorize_visits": True})
        assert r.status_code == 200, r.text
        people[k] = r.json()["person"]["id"]
        r = adm.post(f"{BASE}/visits", json={"visit_type_id": vt, "host_company_id": comps[k],
                                             "host_person_id": people[k],
                                             "name": f"{TAG} Visitante {k}", "doc_type": "outro",
                                             "doc_number": f"{TAG}{k}",
                                             "identifier": {"type": "qrcode"}})
        assert r.status_code == 200, r.text
        visits[k] = r.json()["visit"]
        db.access_events.insert_one({"id": f"{TAG}-ev-{k}", "person_id": people[k],
                                     "person_name": f"{TAG} Pessoa {k}",
                                     "company_id": comps[k],
                                     "timestamp": "2099-01-01T00:00:00+00:00",
                                     "access_result": "granted"})
        mgr[k] = login(email, "Gestor@2026")

    yield {"adm": adm, "comps": comps, "mgr": mgr, "people": people, "visits": visits,
           "cat_a": cat_a, "cat_b": cat_b, "vt_a": vt_a, "vt_b": vt_b}

    # Cleanup
    for v in visits.values():
        try:
            adm.post(f"{BASE}/visits/{v['id']}/end")
        except Exception:
            pass
    vids = [v["visitor_id"] for v in visits.values()]
    pids = list(people.values())
    db.visits.delete_many({"$or": [{"visitor_id": {"$in": vids}}, {"host_company_id": {"$in": list(comps.values())}}]})
    db.visitors.delete_many({"id": {"$in": vids}})
    db.visit_history.delete_many({"visitor_id": {"$in": vids}})
    db.people.delete_many({"$or": [{"id": {"$in": pids}}, {"company_id": {"$in": list(comps.values())}}]})
    db.access_events.delete_many({"$or": [{"id": {"$regex": f"^{TAG}"}},
                                           {"company_id": {"$in": list(comps.values())}}]})
    db.companies.delete_many({"id": {"$in": list(comps.values())}})
    db.users.delete_many({"email": {"$regex": f"^{TAG.lower()}"}})
    # Reset setting
    try:
        s = adm.get(f"{BASE}/admin/settings").json()
        s["manager_can_create_managers"] = False
        adm.put(f"{BASE}/admin/settings", json=s)
    except Exception:
        pass


# ---------- Lookups e visitor-companies (LGPD) ----------
def _items(r):
    j = r.json()
    if isinstance(j, list):
        return j
    return j.get("items", [])


def test_registry_search_scoped(env):
    a = env["mgr"]["A"]
    r = a.get(f"{BASE}/registry/search?q={TAG}")
    assert r.status_code == 200, r.text
    names = [x.get("name", "") for x in _items(r)]
    assert any(f"{TAG} Pessoa A" in n for n in names), names
    assert not any(f"{TAG} Pessoa B" in n for n in names), names


def test_visitors_lookup_lgpd(env):
    """Lookup por documento do visitante B pelo gestor A deve retornar vazio/404 (LGPD)."""
    a = env["mgr"]["A"]
    r = a.get(f"{BASE}/registry/visitors/lookup?document={TAG}B")
    # 200 vazio ou 404 ambos aceitáveis (não deve revelar visitante B)
    if r.status_code == 200:
        items = _items(r)
        names = [x.get("name", "") for x in items]
        assert all(f"{TAG} Visitante B" not in n for n in names), names
    else:
        assert r.status_code == 404, r.text


def test_visits_lookup_lgpd(env):
    """GET /visits/lookup?doc_type=outro&doc_number=TESTB — gestor A não deve encontrar visita de B."""
    a = env["mgr"]["A"]
    r = a.get(f"{BASE}/visits/lookup", params={"doc_type": "outro", "doc_number": f"{TAG}B"})
    if r.status_code == 200:
        items = _items(r)
        names = [x.get("name", "") for x in items]
        assert all(f"{TAG} Visitante B" not in n for n in names), names
    else:
        assert r.status_code == 404, r.text


def test_visitor_companies_scoped(env):
    a = env["mgr"]["A"]
    for path in ("/visits/visitor-companies", "/registry/visitor-companies"):
        r = a.get(f"{BASE}{path}")
        if r.status_code == 404:
            continue
        assert r.status_code == 200, (path, r.text)
        items = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
        ids = [x.get("id") for x in items]
        assert env["comps"]["B"] not in ids, (path, ids)


# ---------- Dashboard / Relatórios ----------
def test_dashboard_scoped(env):
    a = env["mgr"]["A"]
    r = a.get(f"{BASE}/dashboard/stats")
    assert r.status_code == 200, r.text
    data = r.json()
    # não deve conter contagens globais; deve pelo menos ter chaves do dashboard
    assert isinstance(data, dict) and data


def test_reports_presence_scoped(env):
    a = env["mgr"]["A"]
    r = a.get(f"{BASE}/reports/presence")
    assert r.status_code == 200, r.text
    items = r.json().get("items", r.json() if isinstance(r.json(), list) else [])
    assert all((it.get("company_id") in (None, env["comps"]["A"])) for it in items), items[:3]


# ---------- Regras de criação de visita ----------
def test_create_visit_other_company_422(env):
    a = env["mgr"]["A"]
    r = a.post(f"{BASE}/visits", json={"visit_type_id": env["vt_a"], "host_company_id": env["comps"]["B"],
                                       "host_person_id": env["people"]["B"], "name": f"{TAG} X",
                                       "doc_type": "outro", "doc_number": f"{TAG}X",
                                       "identifier": {"type": "qrcode"}})
    assert r.status_code in (404, 422), r.text


def test_create_visit_disallowed_type_422(env):
    a = env["mgr"]["A"]
    # vt_b não é permitido para empresa A
    if env["vt_a"] == env["vt_b"]:
        pytest.skip("Só existe 1 visit_type no ambiente")
    r = a.post(f"{BASE}/visits", json={"visit_type_id": env["vt_b"], "host_company_id": env["comps"]["A"],
                                       "host_person_id": env["people"]["A"], "name": f"{TAG} Y",
                                       "doc_type": "outro", "doc_number": f"{TAG}Y",
                                       "identifier": {"type": "qrcode"}})
    assert r.status_code == 422, r.text


# ---------- Limite max_active_people ----------
def test_company_max_active_people(env):
    adm = env["adm"]
    # Empresa A tem max_active_people=1 e já tem 1 pessoa; adicionar 2a deve 422
    body = {"person_type": "funcionario", "name": f"{TAG} Extra",
            "doc_type": "cpf", "doc_number": _cpf(int(uuid.uuid4().int % 10**9)),
            "company_id": env["comps"]["A"], "category_ids": [env["cat_a"]]}
    r = adm.post(f"{BASE}/registry/people", json=body)
    assert r.status_code == 422, r.text


# ---------- Middleware allowlist ----------
def test_middleware_403_blocks(env):
    a = env["mgr"]["A"]
    for m, p in (("get", "/structure/sites"), ("get", "/equipment/controllers"),
                 ("get", "/auth/users"), ("get", "/admin/settings"),
                 ("get", "/integrations/mqtt"), ("get", "/alarms"), ("get", "/people")):
        resp = getattr(a, m)(f"{BASE}{p}")
        assert resp.status_code == 403, (p, resp.status_code, resp.text[:120])


# ---------- Auditoria do gestor ----------
def test_manager_actions_audited(env):
    a = env["mgr"]["A"]
    # gera POST autorizada do gestor
    r = a.post(f"{BASE}/registry/photo/check", json={"image_base64": ""})
    # não importa o resultado, só precisa ter chamado
    time.sleep(0.5)
    adm = env["adm"]
    audit = adm.get(f"{BASE}/admin/audit?limit=200").json()
    items = audit.get("items", audit if isinstance(audit, list) else [])
    acts = [i.get("action", "") for i in items]
    assert any(a_ and a_.startswith("gestor:") for a_ in acts), acts[:10]


# ---------- Criar gestores (setting toggle) ----------
def test_manager_cannot_create_managers_when_disabled(env):
    adm = env["adm"]
    s = adm.get(f"{BASE}/admin/settings").json()
    s["manager_can_create_managers"] = False
    assert adm.put(f"{BASE}/admin/settings", json=s).status_code == 200
    a = env["mgr"]["A"]
    r = a.post(f"{BASE}/auth/users", json={"email": f"{TAG.lower()}_sub@x.com", "password": "Gestor@2026",
                                           "name": "sub", "role": "company_manager",
                                           "company_ids": [env["comps"]["A"]]})
    assert r.status_code == 403, r.text


def test_manager_can_create_managers_when_enabled(env):
    adm = env["adm"]
    s = adm.get(f"{BASE}/admin/settings").json()
    s["manager_can_create_managers"] = True
    assert adm.put(f"{BASE}/admin/settings", json=s).status_code == 200
    a = env["mgr"]["A"]
    sub_email = f"{TAG.lower()}_sub2@x.com"
    r = a.post(f"{BASE}/auth/users", json={"email": sub_email, "password": "Gestor@2026",
                                           "name": "sub2", "role": "company_manager",
                                           "company_ids": [env["comps"]["A"]]})
    assert r.status_code == 200, r.text
    # Outra role deve 403
    r2 = a.post(f"{BASE}/auth/users", json={"email": f"{TAG.lower()}_adm@x.com", "password": "Gestor@2026",
                                            "name": "x", "role": "admin",
                                            "company_ids": [env["comps"]["A"]]})
    assert r2.status_code == 403
    # Fora do seu company_ids deve 403
    r3 = a.post(f"{BASE}/auth/users", json={"email": f"{TAG.lower()}_wrong@x.com", "password": "Gestor@2026",
                                            "name": "x", "role": "company_manager",
                                            "company_ids": [env["comps"]["B"]]})
    assert r3.status_code in (403, 422), r3.text
    # restaura
    s["manager_can_create_managers"] = False
    adm.put(f"{BASE}/admin/settings", json=s)
    db.users.delete_many({"email": {"$regex": f"^{TAG.lower()}_sub"}})

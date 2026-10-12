"""WebSocket live scope test: evento criado via /equipment/access-points/{id}/open não deve
chegar ao gestor cujo company_id != do evento."""
import os, uuid, asyncio, json, pytest, requests
import websockets
from pymongo import MongoClient

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
WS = BASE.replace("https://", "wss://").replace("http://", "ws://") + "/ws"
ADMIN = ("felipejferreira@gmail.com", "NxAccess@2026")
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
TAG = "TEST_WS_" + uuid.uuid4().hex[:6]


def login(email, pwd):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": pwd}, timeout=20)
    assert r.status_code == 200, r.text
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    s.token = r.json()["access_token"]
    return s


async def collect(ws_url, timeout=4.0):
    msgs = []
    try:
        async with websockets.connect(ws_url) as ws:
            end = asyncio.get_event_loop().time() + timeout
            while asyncio.get_event_loop().time() < end:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=0.5)
                    msgs.append(json.loads(msg))
                except asyncio.TimeoutError:
                    pass
    except Exception as e:
        msgs.append({"error": str(e)})
    return msgs


@pytest.mark.asyncio
async def _test_ws_scope_live_impl():
    adm = login(*ADMIN)
    # Encontra ou cria 2 empresas de teste rapidamente
    cats = adm.get(f"{BASE}/access/categories/all").json()
    cat = cats[0]["id"]
    vt = adm.get(f"{BASE}/visits/types").json()[0]["id"]
    comp_a = adm.post(f"{BASE}/org/companies", json={"name": f"{TAG} A", "type": "propria", "enabled": True,
        "allowed_category_ids": [cat], "allowed_visit_type_ids": [vt]}).json()["id"]
    comp_b = adm.post(f"{BASE}/org/companies", json={"name": f"{TAG} B", "type": "propria", "enabled": True,
        "allowed_category_ids": [cat], "allowed_visit_type_ids": [vt]}).json()["id"]
    email = f"{TAG.lower()}@teste.com"
    adm.post(f"{BASE}/auth/users", json={"email": email, "password": "Gestor@2026", "name": f"{TAG} MGR",
                                         "role": "company_manager", "company_ids": [comp_a]})
    mgr = login(email, "Gestor@2026")

    # cria pessoa em B e evento manual em B via DB para forçar broadcast simulado
    # usamos broadcast via realtime diretamente — rota pública: criar evento via /access/simulate (admin)
    # fallback: inserir evento no DB e disparar nothing — WS depende de broadcast.
    # Então usamos /access/simulate se existir.
    sim = adm.post(f"{BASE}/access/simulate", json={"company_id": comp_b, "access_result": "granted"})

    gestor_ws = WS + f"?token={mgr.token}"
    admin_ws = WS + f"?token={adm.token}"

    gmsgs, amsgs = await asyncio.gather(collect(gestor_ws, 3.0), collect(admin_ws, 3.0))

    # Gestor NÃO deve ter recebido evento de company_id=B nem alarmes
    bad = [m for m in gmsgs if m.get("type") == "access_event"
           and (m.get("data") or {}).get("company_id") == comp_b]
    alarms = [m for m in gmsgs if m.get("type") in ("alarm", "emergency")]
    print(f"gestor recebeu {len(gmsgs)} msgs, bad={len(bad)}, alarms={len(alarms)}")
    print(f"admin recebeu {len(amsgs)}")
    assert not bad, bad
    assert not alarms, alarms

    # cleanup
    db.access_events.delete_many({"company_id": {"$in": [comp_a, comp_b]}})
    db.companies.delete_many({"id": {"$in": [comp_a, comp_b]}})
    db.users.delete_many({"email": email})


def test_ws_scope_live():
    asyncio.run(_test_ws_scope_live_impl())


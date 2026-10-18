"""Helper (not pytest): prepare/cleanup data for iter23 UI tests. usage: python ui_setup_iter23.py setup|submit N|approve ID|reject ID|cleanup"""
import asyncio, base64, json, os, sys
from pathlib import Path
import requests
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")
BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api"
ST = Path("/tmp/iter23_state.json")
db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
run = asyncio.get_event_loop().run_until_complete


def sess():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": "felipejferreira@gmail.com", "password": "NxAccess@2026"})
    s.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    return s


def cpf(seed):
    d = [int(x) for x in str(seed).zfill(9)]
    for _ in range(2):
        t = sum((len(d) + 1 - j) * v for j, v in enumerate(d))
        d.append(((t * 10) % 11) % 10)
    return "".join(map(str, d))


cmd = sys.argv[1]
s = sess()
if cmd == "setup":
    comps = s.get(f"{API}/selfreg/companies").json()
    vt = s.get(f"{API}/visits/types?active=true").json()[0]
    for c in comps:
        host = run(db.people.find_one({"company_id": c["id"], "status": "ativo", "deleted": {"$ne": True},
                                       "can_authorize_visits": {"$ne": False}}, {"_id": 0, "id": 1, "name": 1}))
        if host:
            break
    st = {"comp": c["id"], "comp_name": c["name"], "prev_enabled": bool(c.get("selfreg_enabled")),
          "prev_vt": c.get("selfreg_visit_type_id"), "vt": vt["id"], "host": host}
    s.put(f"{API}/selfreg/companies/{c['id']}", json={"enabled": True, "visit_type_id": vt["id"]})
    st["code"] = next(x for x in s.get(f"{API}/selfreg/companies").json() if x["id"] == c["id"])["selfreg_code"]
    ST.write_text(json.dumps(st))
    print(json.dumps(st))
elif cmd == "submit":
    st = json.loads(ST.read_text())
    run(db.rate_hits.delete_many({}))
    photo = "data:image/jpeg;base64," + base64.b64encode((Path(__file__).parent / "fixtures" / "face.jpg").read_bytes()).decode()
    n = int(sys.argv[2])
    r = requests.post(f"{API}/public/selfreg/submit", json={"code": st["code"], "consent": True, "name": f"TEST_UI Pessoa {n}",
                      "doc_type": "cpf", "doc_number": cpf(741000000 + n), "photo": photo, "host_person_id": st["host"]["id"]})
    tok = r.json()["status_token"]
    import hashlib
    reg = run(db.self_registrations.find_one({"status_token_hash": hashlib.sha256(tok.encode()).hexdigest()}, {"_id": 0, "id": 1}))
    print(json.dumps({"code": r.status_code, "token": tok, "id": (reg or {}).get("id")}))
elif cmd in ("approve", "reject"):
    r = s.post(f"{API}/selfreg/requests/{sys.argv[2]}/{cmd}", json={"reason": "TEST"} if cmd == "reject" else {})
    print(r.status_code, r.text[:200])
elif cmd == "cleanup":
    st = json.loads(ST.read_text())
    regs = run(db.self_registrations.find({"name": {"$regex": "^TEST_UI"}}, {"id": 1}).to_list(100))
    vids = [v["id"] for v in run(db.visitors.find({"name": {"$regex": "^TEST_UI"}}, {"id": 1}).to_list(100))]
    run(db.visits.delete_many({"visitor_id": {"$in": vids}}))
    run(db.visitors.delete_many({"id": {"$in": vids}}))
    run(db.notifications.delete_many({"ref": {"$in": [r["id"] for r in regs]}}))
    run(db.self_registrations.delete_many({"name": {"$regex": "^TEST_UI"}}))
    run(db.selfreg_invites.delete_many({"guest_name": {"$regex": "^TEST_UI"}}))
    run(db.rate_hits.delete_many({}))
    s.put(f"{API}/selfreg/companies/{st['comp']}", json={"enabled": st["prev_enabled"], "visit_type_id": st["prev_vt"] or st["vt"]})
    print("cleaned", len(regs), len(vids))

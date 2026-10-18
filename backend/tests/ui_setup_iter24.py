"""Helper (not pytest): iter24 UI setup/cleanup for CPF-first selfreg + visit reason. usage: python ui_setup_iter24.py setup|hosttoken REGID|cleanup"""
import asyncio, hashlib, json, os, sys
from pathlib import Path
import requests
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")
BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api"
ST = Path("/tmp/iter24_state.json")
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


KNOWN, NEW, PORT_KNOWN, PORT_NEW = cpf(744000001), cpf(744000002), cpf(744000003), cpf(744000004)
cmd = sys.argv[1]
s = sess()
if cmd == "setup":
    comps = s.get(f"{API}/selfreg/companies").json()
    vt = s.get(f"{API}/visits/types?active=true").json()[0]
    hosts = {}
    for c in comps:
        host = run(db.people.find_one({"company_id": c["id"], "status": "ativo", "deleted": {"$ne": True},
                                       "can_authorize_visits": {"$ne": False}}, {"_id": 0, "id": 1, "name": 1}))
        if host:
            hosts[c["id"]] = host
    cid = next(iter(hosts))
    c = next(x for x in comps if x["id"] == cid)
    site = s.get(f"{API}/selfreg/site-link").json()
    st = {"comps_prev": {x["id"]: {"enabled": bool(x.get("selfreg_enabled")), "vt": x.get("selfreg_visit_type_id")} for x in comps},
          "comp": cid, "comp_name": c["name"], "vt": vt["id"], "host": hosts[cid], "hosts": hosts, "site_prev": site,
          "known": KNOWN, "new": NEW, "port_known": PORT_KNOWN, "port_new": PORT_NEW}
    for x in comps:
        if x["id"] in hosts:
            s.put(f"{API}/selfreg/companies/{x['id']}", json={"enabled": True, "visit_type_id": vt["id"]})
    sl = s.put(f"{API}/selfreg/site-link", json={"enabled": True}).json()
    st["site_code"] = s.get(f"{API}/selfreg/site-link").json()["code"]
    st["code"] = next(x for x in s.get(f"{API}/selfreg/companies").json() if x["id"] == cid)["selfreg_code"]
    run(db.visitors.insert_one({"id": "TEST_UI24-v1", "name": "TEST_UI24 Mariana Souza", "doc_type": "cpf", "doc_number": KNOWN,
                                "doc_key": KNOWN, "origin_company": "TEST Origem", "deleted": False, "enabled": True, "blacklist": False}))
    run(db.visitors.insert_one({"id": "TEST_UI24-v2", "name": "TEST_UI24 Portaria Silva", "doc_type": "cpf", "doc_number": PORT_KNOWN,
                                "doc_key": PORT_KNOWN, "origin_company": "TEST_ACME Origem", "deleted": False, "enabled": True, "blacklist": False}))
    run(db.rate_hits.delete_many({}))
    ST.write_text(json.dumps(st))
    print(json.dumps(st, indent=1))
elif cmd == "hosttoken":
    tok = "TESTUI24TOKEN" + sys.argv[2][:8]
    r = run(db.self_registrations.update_one({"id": sys.argv[2]}, {"$set": {"decision_token_hash": hashlib.sha256(tok.encode()).hexdigest()}}))
    print(tok, r.modified_count)
elif cmd == "cleanup":
    st = json.loads(ST.read_text())
    vq = {"$or": [{"name": {"$regex": "^TEST_UI24"}}, {"doc_key": {"$in": [KNOWN, NEW, PORT_KNOWN, PORT_NEW]}}]}
    vids = [v["id"] for v in run(db.visitors.find(vq, {"id": 1}).to_list(100))]
    regs = run(db.self_registrations.find({"doc_key": {"$in": [KNOWN, NEW]}}, {"id": 1}).to_list(100))
    run(db.notifications.delete_many({"ref": {"$in": [r["id"] for r in regs]}}))
    run(db.self_registrations.delete_many({"doc_key": {"$in": [KNOWN, NEW]}}))
    v = run(db.visits.delete_many({"visitor_id": {"$in": vids}}))
    run(db.visitors.delete_many({"id": {"$in": vids}}))
    run(db.rate_hits.delete_many({}))
    for cid, p in st["comps_prev"].items():
        if cid in st["hosts"]:
            s.put(f"{API}/selfreg/companies/{cid}", json={"enabled": p["enabled"], "visit_type_id": p["vt"] or st["vt"]})
    s.put(f"{API}/selfreg/site-link", json={"enabled": bool(st["site_prev"].get("enabled"))})
    print("cleaned regs", len(regs), "visitors", len(vids), "visits", v.deleted_count)

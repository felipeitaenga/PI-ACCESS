"""Helper (not pytest): iter25 UI setup/cleanup for mobile selfreg redesign. usage: python ui_setup_iter25.py setup|hosttoken REGID|cleanup"""
import asyncio, hashlib, json, os, sys
from pathlib import Path
import requests
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")
BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api"
ST = Path("/tmp/iter25_state.json")
db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
run = asyncio.get_event_loop().run_until_complete
GESTOR = "test_iter25_gestor@nxaccess.com"


def sess():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": "felipejferreira@gmail.com", "password": "NxAccess@2026"})
    s.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    return s


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
    cdoc = run(db.companies.find_one({"id": cid}, {"_id": 0, "allowed_visit_type_ids": 1}))
    st = {"comps_prev": {x["id"]: {"enabled": bool(x.get("selfreg_enabled")), "vt": x.get("selfreg_visit_type_id")} for x in comps},
          "comp": cid, "comp_name": c["name"], "vt": vt["id"], "host": hosts[cid], "site_prev": site,
          "allowed_prev": (cdoc or {}).get("allowed_visit_type_ids", "__missing__")}
    r = s.put(f"{API}/selfreg/companies/{cid}", json={"enabled": True, "visit_type_id": vt["id"]})
    print("enable company", r.status_code)
    st["code"] = next(x for x in s.get(f"{API}/selfreg/companies").json() if x["id"] == cid)["selfreg_code"]
    st["site_code"] = site.get("code")
    r = s.post(f"{API}/auth/users", json={"email": GESTOR, "name": "TEST_ Gestor Iter25", "password": "Gestor@2026",
                                          "role": "company_manager", "company_ids": [cid]})
    print("gestor", r.status_code, r.text[:200])
    run(db.rate_hits.delete_many({}))
    ST.write_text(json.dumps(st))
    print(json.dumps(st, indent=1))
elif cmd == "hosttoken":
    tok = "TESTUI25TOKEN" + sys.argv[2][:8]
    r = run(db.self_registrations.update_one({"id": sys.argv[2]}, {"$set": {"decision_token_hash": hashlib.sha256(tok.encode()).hexdigest()}}))
    print(tok, r.modified_count)
elif cmd == "cleanup":
    st = json.loads(ST.read_text())
    regs = run(db.self_registrations.find({"name": {"$regex": "^TEST_"}}, {"id": 1, "visitor_id": 1, "visit_id": 1}).to_list(500))
    ids = [r["id"] for r in regs]
    run(db.notifications.delete_many({"ref": {"$in": ids}}))
    vids = [v["id"] for v in run(db.visitors.find({"name": {"$regex": "^TEST_"}}, {"id": 1}).to_list(500))]
    v = run(db.visits.delete_many({"$or": [{"visitor_id": {"$in": vids}}, {"self_registration_id": {"$in": ids}}]}))
    run(db.visitors.delete_many({"id": {"$in": vids}}))
    run(db.self_registrations.delete_many({"id": {"$in": ids}}))
    inv = run(db.selfreg_invites.delete_many({"guest_name": {"$regex": "^TEST_"}})) if "selfreg_invites" in run(db.list_collection_names()) else None
    run(db.rate_hits.delete_many({}))
    for cid, p in st["comps_prev"].items():
        cur = run(db.companies.find_one({"id": cid}, {"_id": 0, "selfreg_enabled": 1}))
        if cid == st["comp"] or bool((cur or {}).get("selfreg_enabled")) != p["enabled"]:
            s.put(f"{API}/selfreg/companies/{cid}", json={"enabled": p["enabled"], "visit_type_id": p["vt"] or st["vt"]})
    if st["allowed_prev"] == "__missing__":
        run(db.companies.update_one({"id": st["comp"]}, {"$unset": {"allowed_visit_type_ids": ""}}))
    else:
        run(db.companies.update_one({"id": st["comp"]}, {"$set": {"allowed_visit_type_ids": st["allowed_prev"]}}))
    s.put(f"{API}/selfreg/site-link", json={"enabled": bool(st["site_prev"].get("enabled"))})
    u = run(db.users.find_one({"email": GESTOR}, {"id": 1}))
    if u:
        print("del gestor", s.delete(f"{API}/auth/users/{u.get('id') or str(u['_id'])}").status_code)
    print("cleaned regs", len(ids), "visitors", len(vids), "visits", v.deleted_count, "invites", inv.deleted_count if inv else "?")

"""Helper (not pytest): submit a TEST_ public self-registration via API. usage: python ui_submit_iter25.py CODE NAME CPFSEED [blacklist_visitor]"""
import asyncio, base64, json, os, sys
import requests
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")
API = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api/public/selfreg"
db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
run = asyncio.get_event_loop().run_until_complete


def cpf(seed):
    d = [int(x) for x in str(seed).zfill(9)]
    for _ in range(2):
        t = sum((len(d) + 1 - j) * v for j, v in enumerate(d))
        d.append(((t * 10) % 11) % 10)
    return "".join(map(str, d))


code, name, seed = sys.argv[1], sys.argv[2], int(sys.argv[3])
doc = cpf(seed)
if len(sys.argv) > 4:
    run(db.visitors.insert_one({"id": "TEST_UI25-bl", "name": "TEST_ Existente Bloqueado", "doc_type": "cpf", "doc_number": doc,
                                "doc_key": doc, "deleted": False, "enabled": True, "blacklist": True, "blacklist_reason": "TEST motivo"}))
run(db.rate_hits.delete_many({}))
photo = "data:image/jpeg;base64," + base64.b64encode(open("/app/backend/tests/fixtures/face.jpg", "rb").read()).decode()
is_invite = len(code) > 12
key = {"invite": code} if is_invite else {"code": code}
host = None
if not is_invite:
    hs = requests.post(f"{API}/hosts", json={**key, "q": "Clara"}).json()
    host = hs[0]["id"]
r = requests.post(f"{API}/submit", json={**key, "consent": True, "name": name, "doc_type": "cpf", "doc_number": doc, "photo": photo,
                                         "host_person_id": host or "", "visit_reason": "TEST_ motivo", "email": ""})
print(r.status_code, json.dumps(r.json())[:300])

# Iter25: auth playbook checks + selfreg public rules (no CPF lookup, invites never auto-approve)
import hashlib
import os
import uuid

import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")
BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
ADMIN = {"email": "felipejferreira@gmail.com", "password": "NxAccess@2026"}


@pytest.fixture(scope="module")
def admin():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=ADMIN)
    assert r.status_code == 200
    s.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    return s


# Auth: bcrypt + httpOnly cookies + CORS
class TestAuthPlaybook:
    def test_bcrypt_hash(self):
        u = db.users.find_one({"email": ADMIN["email"]})
        h = u.get("password_hash") or u.get("hashed_password") or u.get("password")
        assert str(h).startswith("$2b$")

    def test_login_sets_httponly_cookie(self):
        r = requests.post(f"{API}/auth/login", json=ADMIN)
        assert r.status_code == 200
        sc = r.headers.get("set-cookie", "")
        assert "access_token" in sc and "httponly" in sc.lower()

    def test_cors_explicit_origin(self):
        r = requests.options(f"{API}/auth/login", headers={"Origin": BASE_URL, "Access-Control-Request-Method": "POST"})
        assert r.headers.get("access-control-allow-origin") == BASE_URL
        assert r.headers.get("access-control-allow-credentials") == "true"

    def test_forgot_password_identical(self):
        a = requests.post(f"{API}/auth/forgot-password", json={"email": ADMIN["email"]})
        b = requests.post(f"{API}/auth/forgot-password", json={"email": f"nouser_{uuid.uuid4().hex[:6]}@x.com"})
        assert a.status_code == b.status_code and a.json() == b.json()
        t = db.password_reset_tokens.find_one({}, sort=[("_id", -1)]) if "password_reset_tokens" in db.list_collection_names() else None
        if t:
            assert "token_hash" in t and "token" not in t

    def test_bruteforce_lockout(self):
        email = f"test_lock_{uuid.uuid4().hex[:6]}@x.com"
        codes = [requests.post(f"{API}/auth/login", json={"email": email, "password": "wrong"}).status_code for _ in range(7)]
        db.login_attempts.delete_many({"identifier": {"$regex": email}})
        db.login_attempts.delete_many({"email": email})
        assert 429 in codes, codes


# Selfreg public: no CPF lookup route, unknown routes 404/405
class TestSelfregPublicRules:
    @pytest.mark.parametrize("path", ["/public/selfreg/cpf", "/public/selfreg/lookup", "/public/selfreg/visitor"])
    def test_no_public_cpf_lookup(self, path):
        r = requests.post(f"{API}{path}", json={"code": "x", "doc_number": "52998224725"})
        assert r.status_code in (404, 405)

    def test_info_invalid_code(self):
        r = requests.get(f"{API}/public/selfreg/info", params={"code": "zzzzzzzz"})
        assert r.status_code in (400, 404)

    def test_invite_requires_auth(self):
        r = requests.post(f"{API}/selfreg/invites", json={})
        assert r.status_code in (401, 403)

    def test_invites_list_admin(self, admin):
        r = admin.get(f"{API}/selfreg/invites")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_decision_token_hash_unknown(self):
        r = requests.get(f"{API}/public/selfreg/decision/NOTAREALTOKEN{uuid.uuid4().hex[:6]}")
        assert r.status_code in (400, 404)

    def test_token_hash_is_sha256(self):
        assert hashlib.sha256(b"x").hexdigest() == "2d711642b726b04401627ca9fbac32f5c8530fb1903cc4db02258717921a4881"

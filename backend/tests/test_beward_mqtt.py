"""Integration + unit tests for Beward MQTT/HTTP flow (iteration 7).

Covers:
- /api/integrations/mqtt GET/PUT/test/log (admin)
- Agent tokens CRUD + /api/agent/* with Bearer
- PUT /api/structure/sites/{id}/business-hours
- beward_ingest.on_mqtt (heartbeat, RecPush, dedup, direction mismatch)
- beward_ingest.watch_once (sem_eventos alarm within business hours)
- BewardMqttDriver.sync_person queueing when device offline
- Cleans up all TEST_ data.
"""
import os
import sys
import asyncio
import pytest
import requests


# Shared event loop across all tests in this module (motor binds to first loop)
@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


def _run(coro):
    """Run a coroutine on the module's event loop."""
    loop = asyncio.get_event_loop_policy().get_event_loop() if False else None
    # Use the module loop set by pytest-asyncio-like helper
    return _MODULE_LOOP.run_until_complete(coro)


_MODULE_LOOP = asyncio.new_event_loop()


@pytest.fixture(scope="module", autouse=True)
def _bind_loop():
    asyncio.set_event_loop(_MODULE_LOOP)
    yield
    # Close at the very end
    try:
        _MODULE_LOOP.close()
    except Exception:
        pass

# Add backend to path for unit-level imports
BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE:
    # Fallback to frontend .env
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    BASE = line.split("=", 1)[1].strip().rstrip("/")
    except Exception:
        pass
API = f"{BASE}/api"

ADMIN = {"email": "felipejferreira@gmail.com", "password": "NxAccess@2026"}

# ----------------- Fixtures -----------------
@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=ADMIN, timeout=15)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def site_id(admin_session):
    r = admin_session.get(f"{API}/structure/sites", timeout=10)
    assert r.status_code == 200
    sites = r.json()
    assert sites, "No sites seeded"
    return sites[0]["id"]


@pytest.fixture(scope="module")
def person_id(admin_session):
    r = admin_session.get(f"{API}/people?limit=1", timeout=10)
    assert r.status_code == 200
    data = r.json()
    items = data.get("items", data) if isinstance(data, dict) else data
    assert items, "No persons seeded"
    return items[0]["id"]


@pytest.fixture(scope="module")
def area_ids(admin_session, site_id):
    r = admin_session.get(f"{API}/structure/areas?site_id={site_id}", timeout=10)
    assert r.status_code == 200
    areas = r.json()
    assert len(areas) >= 2
    return areas[0]["id"], areas[1]["id"]


# ----------------- Cleanup helpers -----------------
_created = {"controllers": [], "agents": []}

@pytest.fixture(scope="module", autouse=True)
def _cleanup(admin_session):
    yield
    # Delete created controllers
    for cid in _created["controllers"]:
        try:
            admin_session.delete(f"{API}/equipment/controllers/{cid}", timeout=10)
        except Exception:
            pass
    # Revoke agent tokens
    for aid in _created["agents"]:
        try:
            admin_session.post(f"{API}/agents/{aid}/revoke", timeout=10)
        except Exception:
            pass
    # Direct mongo cleanup for alarms/events/mqtt_commands/dedup for TEST999
    async def _mongo_clean():
        from database import db
        for cid in _created["controllers"]:
            await db.alarms.delete_many({"controller_id": cid})
            await db.access_events.delete_many({"controller_id": cid})
            await db.access_points.delete_many({"controller_id": cid})
        await db.mqtt_commands.delete_many({"device_id": "TEST999"})
        await db.beward_dedup.delete_many({"_id": {"$regex": "^TEST999:"}})
    try:
        _run(_mongo_clean())
    except Exception:
        pass


# ----------------- 1) MQTT integration endpoints -----------------
class TestMqttIntegration:
    def test_get_mqtt(self, admin_session):
        r = admin_session.get(f"{API}/integrations/mqtt", timeout=10)
        assert r.status_code == 200
        j = r.json()
        assert "config" in j and "status" in j
        # host should be preserved
        assert j["config"].get("host") == "156.67.82.199"
        assert int(j["config"].get("port") or 0) == 1883

    def test_mqtt_test_connect(self, admin_session):
        r = admin_session.post(f"{API}/integrations/mqtt/test",
                               json={"host": "156.67.82.199", "port": 1883, "username": ""},
                               timeout=20)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("ok") is True, f"probe failed: {j}"
        assert "Conectado" in j.get("detail", "")

    def test_mqtt_log_connected(self, admin_session):
        r = admin_session.get(f"{API}/integrations/mqtt/log", timeout=10)
        assert r.status_code == 200
        j = r.json()
        assert "status" in j and "messages" in j
        # bus should be connected (started at app launch)
        assert j["status"].get("connected") is True, f"bus not connected: {j['status']}"

    def test_mqtt_put_round_trip(self, admin_session):
        # Save same config to confirm PUT path works, then restore
        r = admin_session.put(f"{API}/integrations/mqtt",
                              json={"host": "156.67.82.199", "port": 1883, "username": "", "enabled": True},
                              timeout=20)
        assert r.status_code == 200
        assert r.json().get("ok") is True


# ----------------- 2) Agent tokens + agent API -----------------
class TestAgents:
    def test_generate_and_revoke_old(self, admin_session, site_id):
        # Generate a token for site
        r = admin_session.post(f"{API}/agents", json={"site_id": site_id}, timeout=10)
        assert r.status_code == 200, r.text
        tok1 = r.json()
        assert tok1.get("token", "").startswith("nxa_")
        _created["agents"].append(tok1["id"])
        # List does not include token_hash
        r2 = admin_session.get(f"{API}/agents?site_id={site_id}", timeout=10)
        assert r2.status_code == 200
        assert all("token_hash" not in a for a in r2.json())
        # Generate again -> previous revoked
        r3 = admin_session.post(f"{API}/agents", json={"site_id": site_id}, timeout=10)
        tok2 = r3.json()
        _created["agents"].append(tok2["id"])
        assert tok2["token"] != tok1["token"]
        # Only one active now
        actives = admin_session.get(f"{API}/agents?site_id={site_id}", timeout=10).json()
        assert len(actives) == 1
        assert actives[0]["id"] == tok2["id"]
        # Save tok2 for next tests
        pytest._agent_token = tok2["token"]
        pytest._agent_id = tok2["id"]

    def test_invalid_token_401(self):
        r = requests.get(f"{API}/agent/config", headers={"Authorization": "Bearer nxa_invalid"}, timeout=10)
        assert r.status_code == 401

    def test_agent_config_filters_http(self, admin_session, site_id, area_ids):
        # Create a TEST_ HTTP controller on this site
        oid, did = area_ids
        body = {"name": "TEST_HTTP", "model_type": "beward_facial", "transport": "http",
                "beward_device_id": "TEST_HTTP_1", "site_id": site_id, "ip": "10.0.0.99", "port": 80,
                "username": "admin", "password": "secret", "num_access_points": 1,
                "access_points": [{"description": "P1", "type": "facial", "direction": "entrada",
                                   "origin_area_id": oid, "dest_area_id": did}]}
        r = admin_session.post(f"{API}/equipment/controllers", json=body, timeout=15)
        assert r.status_code == 200, r.text
        _created["controllers"].append(r.json()["id"])
        # Call /agent/config with token
        tok = pytest._agent_token
        r2 = requests.get(f"{API}/agent/config", headers={"Authorization": f"Bearer {tok}"}, timeout=10)
        assert r2.status_code == 200
        j = r2.json()
        assert j["site_id"] == site_id
        names = [d["name"] for d in j["devices"]]
        assert "TEST_HTTP" in names
        dev = next(d for d in j["devices"] if d["name"] == "TEST_HTTP")
        assert dev["password"] == "secret", "password should be decrypted"

    def test_agent_heartbeat_and_verify(self, admin_session, site_id, person_id):
        tok = pytest._agent_token
        headers = {"Authorization": f"Bearer {tok}"}
        # heartbeat
        r = requests.post(f"{API}/agent/events/heartbeat",
                          headers=headers, json={"device_id": "TEST_HTTP_1", "payload": {"info": {"DeviceID": "TEST_HTTP_1"}}}, timeout=10)
        assert r.status_code == 200
        assert r.json().get("code") == 200
        # verify (unknown person -> still 200 OK; server may decide no openDoor)
        r2 = requests.post(f"{API}/agent/events/verify", headers=headers,
                           json={"device_id": "TEST_HTTP_1",
                                 "payload": {"info": {"DeviceID": "TEST_HTTP_1", "PersonUUID": person_id,
                                                       "VerifyStatus": 1, "VerfyType": 1, "RecordID": "r1",
                                                       "Direction": 1, "SanpPic": ""}}},
                           timeout=10)
        assert r2.status_code == 200
        assert r2.json().get("code") == 200

    def test_agent_commands_poll_and_result(self, admin_session, site_id):
        tok = pytest._agent_token
        headers = {"Authorization": f"Bearer {tok}"}
        # Short poll with wait=1 should return [] quickly
        r = requests.get(f"{API}/agent/commands?wait=1", headers=headers, timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ----------------- 3) business-hours endpoint -----------------
class TestBusinessHours:
    def test_put_business_hours(self, admin_session, site_id):
        payload = {"days": [1, 2, 3, 4, 5], "start": "08:00", "end": "18:00"}
        r = admin_session.put(f"{API}/structure/sites/{site_id}/business-hours", json=payload, timeout=10)
        assert r.status_code == 200
        j = r.json()
        assert j["days"] == [1, 2, 3, 4, 5]
        assert j["start"] == "08:00" and j["end"] == "18:00"
        # Verify persisted
        s = admin_session.get(f"{API}/structure/sites", timeout=10).json()
        site = next(x for x in s if x["id"] == site_id)
        assert site.get("business_hours", {}).get("start") == "08:00"


# ----------------- 4) Unit level: beward_ingest on_mqtt + watch_once + driver queue -----------------
@pytest.fixture(scope="module")
def mqtt_controller(admin_session, site_id, area_ids):
    oid, did = area_ids
    body = {"name": "TEST_MQTT", "model_type": "beward_facial", "transport": "mqtt",
            "beward_device_id": "TEST999", "site_id": site_id, "num_access_points": 1,
            "decision_mode": "servidor",
            "access_points": [{"description": "TEST_MQTT P1", "type": "facial", "direction": "entrada",
                               "origin_area_id": oid, "dest_area_id": did}]}
    r = admin_session.post(f"{API}/equipment/controllers", json=body, timeout=15)
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    _created["controllers"].append(cid)
    return cid


class TestOnMqtt:
    def test_heartbeat_sets_online(self, mqtt_controller):
        import beward_ingest
        from database import db

        async def _inner():
            await beward_ingest.on_mqtt("mqtt/face/heartbeat", "HeartBeat",
                                        {"operator": "HeartBeat", "info": {"facesluiceId": "TEST999", "ip": "1.2.3.4"}},
                                        "TEST999")
            c = await db.controllers.find_one({"id": mqtt_controller}, {"_id": 0})
            return c
        c = _run(_inner())
        assert c["online"] is True
        assert c.get("last_heartbeat")
        assert c.get("device_ip") == "1.2.3.4"

    def test_recpush_creates_event_and_direction_mismatch(self, mqtt_controller, person_id):
        import beward_ingest
        from database import db

        tiny_b64 = "/9j/4AAQSkZJRgABAQAAAQABAAD//gA7AAAA"

        async def _inner():
            # direction=2 (saida) but point is entrada -> mismatch
            data = {"operator": "RecPush",
                    "info": {"facesluiceId": "TEST999", "customId": person_id, "RecordID": "REC_T1",
                             "VerifyStatus": 22, "VerfyType": 1, "Sendintime": 1, "direction": "2",
                             "pic": tiny_b64, "similarity1": 90}}
            await beward_ingest.on_mqtt("mqtt/face/TEST999/Rec", "RecPush", data, "TEST999")
            # Fetch event + ctrl
            ev = await db.access_events.find_one({"controller_id": mqtt_controller, "via": "mqtt"}, {"_id": 0})
            ctrl = await db.controllers.find_one({"id": mqtt_controller}, {"_id": 0})
            alarms = await db.alarms.find({"controller_id": mqtt_controller, "type": "sentido_divergente"}, {"_id": 0}).to_list(10)
            return ev, ctrl, alarms

        ev, ctrl, alarms = _run(_inner())
        assert ev is not None, "access_event not created"
        assert ev.get("captured_photo", "").startswith("data:image/jpeg;base64,")
        assert ev.get("direction_mismatch") is True
        assert ctrl.get("direction_mismatch") is not None
        assert ctrl.get("last_event_at")
        assert len(alarms) == 1, f"expected exactly 1 sentido_divergente alarm, got {len(alarms)}"

    def test_recpush_dedup(self, mqtt_controller, person_id):
        import beward_ingest
        from database import db

        async def _inner():
            data = {"operator": "RecPush",
                    "info": {"facesluiceId": "TEST999", "customId": person_id, "RecordID": "REC_T1",
                             "VerifyStatus": 22, "VerfyType": 1, "Sendintime": 1, "direction": "2", "pic": ""}}
            await beward_ingest.on_mqtt("mqtt/face/TEST999/Rec", "RecPush", data, "TEST999")
            n = await db.access_events.count_documents({"controller_id": mqtt_controller, "via": "mqtt"})
            # Still should only be 1 (dedup)
            return n
        n = _run(_inner())
        assert n == 1, f"dedup failed, got {n} events for same RecordID"


class TestWatchOnce:
    def test_sem_eventos_alarm_in_business_hours(self, mqtt_controller, admin_session, site_id):
        import beward_ingest
        from database import db
        from datetime import datetime, timezone, timedelta

        # Setup: set a very wide business hours (every day 00:00-23:59) to always be in window
        admin_session.put(f"{API}/structure/sites/{site_id}/business-hours",
                          json={"days": [1, 2, 3, 4, 5, 6, 7], "start": "00:00", "end": "23:59"}, timeout=10)

        async def _inner():
            # Force controller: online heartbeat NOW, last_event_at very old, no_event_alerted False, threshold=1min
            past = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
            now_iso_ = datetime.now(timezone.utc).isoformat()
            await db.controllers.update_one({"id": mqtt_controller}, {"$set": {
                "last_heartbeat": now_iso_, "online": True, "online_since": past,
                "last_event_at": past, "no_event_alerted": False, "no_event_alert_minutes": 1,
            }})
            # Clear any previous sem_eventos alarms on this ctrl
            await db.alarms.delete_many({"controller_id": mqtt_controller, "type": "sem_eventos"})
            await beward_ingest.watch_once()
            alarms = await db.alarms.find({"controller_id": mqtt_controller, "type": "sem_eventos"}, {"_id": 0}).to_list(10)
            c = await db.controllers.find_one({"id": mqtt_controller}, {"_id": 0})
            # Running again should NOT create another
            await beward_ingest.watch_once()
            alarms2 = await db.alarms.find({"controller_id": mqtt_controller, "type": "sem_eventos"}, {"_id": 0}).to_list(10)
            return alarms, c, alarms2

        alarms, c, alarms2 = _run(_inner())
        assert len(alarms) == 1, f"expected 1 sem_eventos alarm, got {len(alarms)}"
        assert alarms[0]["priority"] == "baixa"
        assert c.get("no_event_alerted") is True
        assert len(alarms2) == 1, "sem_eventos should not repeat"

    def test_sem_eventos_outside_hours(self, mqtt_controller, admin_session, site_id):
        import beward_ingest
        from database import db
        from datetime import datetime, timezone, timedelta

        # Set business hours to a tiny window far from now (00:00-00:01)
        admin_session.put(f"{API}/structure/sites/{site_id}/business-hours",
                          json={"days": [1, 2, 3, 4, 5], "start": "00:00", "end": "00:01"}, timeout=10)

        async def _inner():
            past = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
            now_iso_ = datetime.now(timezone.utc).isoformat()
            await db.controllers.update_one({"id": mqtt_controller}, {"$set": {
                "last_heartbeat": now_iso_, "online": True, "online_since": past,
                "last_event_at": past, "no_event_alerted": False, "no_event_alert_minutes": 1,
            }})
            await db.alarms.delete_many({"controller_id": mqtt_controller, "type": "sem_eventos"})
            await beward_ingest.watch_once()
            n = await db.alarms.count_documents({"controller_id": mqtt_controller, "type": "sem_eventos"})
            return n

        n = _run(_inner())
        assert n == 0, "should NOT alarm outside business hours"


class TestMqttDriverQueue:
    def test_sync_person_queues_when_offline(self, mqtt_controller, person_id):
        from drivers.beward import BewardMqttDriver
        from database import db
        from datetime import datetime, timezone, timedelta

        async def _inner():
            # Force controller offline (last_heartbeat long ago)
            old = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
            await db.controllers.update_one({"id": mqtt_controller}, {"$set": {"last_heartbeat": old, "online": False}})
            device = await db.controllers.find_one({"id": mqtt_controller}, {"_id": 0})
            drv = BewardMqttDriver(device)
            person = await db.people.find_one({"id": person_id}, {"_id": 0})
            res = await drv.sync_person(person)
            qdoc = await db.mqtt_commands.find_one({"device_id": "TEST999", "operator": "EditPerson", "status": "queued"}, {"_id": 0})
            return res, qdoc

        res, qdoc = _run(_inner())
        assert res.get("queued") is True, f"expected queued True, got {res}"
        assert qdoc is not None, "no mqtt_commands doc queued"
        assert qdoc["status"] == "queued"

"""Facial no modo "Verificação local Aberta à distância": o servidor decide e aplica anti-dupla entrada.
Comportamento real do facial 1457460: RecPush com VerifyStatus "0" e espera um Unlock com openDoor 1/0."""
import asyncio
from datetime import datetime, timedelta, timezone

import mongomock_motor
import pytest

import access_service
import beward_ingest
import scope
import visits_core

_LOOP = asyncio.new_event_loop()


def run(c):
    return _LOOP.run_until_complete(c)


@pytest.fixture()
def env(monkeypatch):
    db = mongomock_motor.AsyncMongoMockClient()["t_remote"]
    for m in (access_service, beward_ingest, scope, visits_core):
        monkeypatch.setattr(m, "db", db)
    sent = []
    monkeypatch.setattr(beward_ingest.bus, "publish_raw", lambda dev, p: sent.append(p) or True)

    async def _noop(*a, **k):
        return None
    monkeypatch.setattr(beward_ingest.manager, "broadcast", _noop)
    now = datetime.now(timezone.utc)
    run(db.controllers.insert_one({"id": "c1", "name": "Facial", "brand": "beward_mqtt", "beward_device_id": "1457460",
                                   "last_heartbeat": now.isoformat(), "deleted": False}))
    run(db.access_points.insert_one({"id": "ap1", "controller_id": "c1", "reader": 1, "site_id": "s1", "direction": "entrada",
                                     "origin_area_id": "ext", "dest_area_id": "int", "deleted": False}))
    run(db.areas.insert_many([{"id": "int", "description": "Interna", "anti_double_entry": False},
                              {"id": "ext", "description": "Externa", "is_exterior": True}]))
    run(db.time_ranges.insert_one({"id": "tr", "enabled": True, "weekdays": [0, 1, 2, 3, 4, 5, 6], "valid_on_holidays": True,
                                   "intervals": [{"start": "00:00", "end": "23:59"}]}))
    run(db.categories.insert_one({"id": "vis", "code": "VIS", "enabled": True, "impeditive": False, "control_origin": False,
                                  "control_anti_double": True, "reentry_timed": False, "reentry_minutes": 0,
                                  "access_areas": [{"area_id": "int", "time_range_id": "tr", "require_escort": False}]}))
    run(db.visitors.insert_one({"id": "v1", "name": "Visitante Teste", "photo": ""}))
    run(db.visits.insert_one({"id": "vis1", "visitor_id": "v1", "status": "presente", "deleted": False, "category_ids": ["vis"],
                              "start_at": (now - timedelta(hours=1)).isoformat(), "end_at": (now + timedelta(hours=3)).isoformat()}))
    return db, sent


def _rec(rid, status="0"):
    return {"operator": "RecPush", "info": {"customId": "v1", "RecordID": str(rid), "VerifyStatus": status, "direction": "entr",
                                            "otype": "1", "persionName": "Visitante Teste", "Sendintime": 1,
                                            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}}


def _unlocks(sent):
    return [p["info"]["openDoor"] for p in sent if p.get("operator") == "Unlock"]


def test_status_0_is_decided_by_server_with_anti_double(env):
    db, sent = env
    run(beward_ingest.on_mqtt("x/Rec", "RecPush", _rec(1), "1457460"))
    run(beward_ingest.on_mqtt("x/Rec", "RecPush", _rec(2), "1457460"))
    assert _unlocks(sent) == ["1", "0"]  # entra; a segunda é negada (já está dentro)
    evs = run(db.access_events.find({}, {"_id": 0}).sort("timestamp", 1).to_list(5))
    assert [e["access_result"] for e in evs] == ["granted", "denied"]
    assert evs[1]["reason"] == "Anti-dupla entrada"
    assert evs[0]["credential_type"] == "facial"
    assert run(db.visits.find_one({"id": "vis1"}))["current_area_id"] == "int"


def test_local_mode_status_1_only_logs(env):
    db, sent = env
    run(beward_ingest.on_mqtt("x/Rec", "RecPush", _rec(3, status="1"), "1457460"))
    assert _unlocks(sent) == []  # facial já decidiu sozinho; servidor só registra
    ev = run(db.access_events.find_one({}, {"_id": 0}))
    assert ev["access_result"] == "granted" and ev["reason"] == "Acesso liberado"

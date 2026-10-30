"""Confirmação de passagem: liberado só conta quando o sensor (giro) confirmar."""
import asyncio
import json
from datetime import datetime, timedelta, timezone

import mongomock_motor
import pytest

import access_service
import beward_ingest
import intelbras_ingest
import passage
import scope
import visits_core
from drivers import intelbras

_LOOP = asyncio.new_event_loop()


def run(c):
    return _LOOP.run_until_complete(c)


@pytest.fixture()
def env(monkeypatch):
    db = mongomock_motor.AsyncMongoMockClient()["t_passage"]
    for m in (access_service, beward_ingest, intelbras_ingest, scope, visits_core, intelbras, passage):
        monkeypatch.setattr(m, "db", db)
    sent = []

    async def _bc(msg):
        sent.append(msg)
    monkeypatch.setattr(passage.manager, "broadcast", _bc)
    monkeypatch.setattr(beward_ingest.manager, "broadcast", _bc)
    monkeypatch.setattr(intelbras_ingest.manager, "broadcast", _bc)
    now = datetime.now(timezone.utc)
    ctrl = {"id": "c1", "name": "Facial", "brand": "intelbras", "deleted": False, "online": True,
            "time_synced_at": now.isoformat(), "time_sync_tried_at": now.isoformat()}
    run(db.controllers.insert_one(dict(ctrl)))
    run(db.access_points.insert_one({"id": "ap1", "controller_id": "c1", "reader": 1, "direction": "entrada", "description": "Catraca 1",
                                     "origin_area_id": "ext", "dest_area_id": "int", "deleted": False,
                                     "passage_mode": "confirmacao", "passage_timeout": 10, "unauthorized_alarm": True}))
    run(db.areas.insert_many([{"id": "int", "description": "Interna", "current_occupancy": 0},
                              {"id": "ext", "description": "Externa", "is_exterior": True}]))
    run(db.time_ranges.insert_one({"id": "tr", "enabled": True, "weekdays": [0, 1, 2, 3, 4, 5, 6], "valid_on_holidays": True,
                                   "intervals": [{"start": "00:00", "end": "23:59"}]}))
    run(db.categories.insert_one({"id": "cat", "code": "FUNC", "enabled": True, "impeditive": False, "control_origin": False,
                                  "control_anti_double": True, "reentry_timed": False, "reentry_minutes": 0,
                                  "access_areas": [{"area_id": "int", "time_range_id": "tr", "require_escort": False}]}))
    run(db.people.insert_one({"id": "p1", "name": "Mariana Costa", "status": "ativo", "category_ids": ["cat"], "person_type": "funcionario"}))
    return db, ctrl, sent


def _access(db):
    person = run(db.people.find_one({"id": "p1"}, {"_id": 0}))
    ap = run(db.access_points.find_one({"id": "ap1"}, {"_id": 0}))
    return run(access_service.evaluate(person, ap))


def test_granted_waits_for_turnstile_then_counts(env):
    db, ctrl, sent = env
    res = _access(db)
    assert res["granted"] and res["event"]["passage"] == "pendente"
    assert run(db.people.find_one({"id": "p1"})).get("current_area_id") is None  # ainda não conta
    assert run(passage.on_sensor(ctrl)) == "confirmada"
    assert run(db.people.find_one({"id": "p1"}))["current_area_id"] == "int"
    assert run(db.areas.find_one({"id": "int"}))["current_occupancy"] == 1
    assert run(db.access_events.find_one({"id": res["event"]["id"]}))["passage"] == "confirmada"
    assert any(m["type"] == "access_event_update" and m["data"]["passage"] == "confirmada" for m in sent)
    assert _access(db)["reason"] == "Anti-dupla entrada"  # agora sim está dentro


def test_not_passed_does_not_count_and_can_try_again(env):
    db, ctrl, sent = env
    res = _access(db)
    run(db.passages.update_one({"event_id": res["event"]["id"]}, {"$set": {"expires_at": "2000-01-01T00:00:00+00:00"}}))
    run(passage.expire_once())
    ev = run(db.access_events.find_one({"id": res["event"]["id"]}))
    assert ev["passage"] == "nao_passou" and "não passou" in ev["reason"]
    assert run(db.people.find_one({"id": "p1"})).get("current_area_id") is None
    assert _access(db)["granted"]  # não caiu no anti-dupla
    assert run(passage.on_sensor(ctrl)) == "confirmada"  # o giro confirma a 2ª liberação, não a expirada


def test_turn_without_release_raises_alarm(env):
    db, ctrl, sent = env
    assert run(passage.on_sensor(ctrl)) == "nao_autorizada"
    alarm = run(db.alarms.find_one({}, {"_id": 0}))
    assert alarm["type"] == "passagem_nao_autorizada" and alarm["priority"] == "alta"


def test_open_close_of_same_turn_counts_once(env):
    db, ctrl, sent = env
    _access(db)
    assert run(passage.on_sensor(ctrl)) == "confirmada"
    assert run(passage.on_sensor(ctrl)) == "debounce"  # o fechar do mesmo giro não vira "não autorizada"
    assert run(db.alarms.count_documents({})) == 0


def test_simple_mode_unchanged(env):
    db, ctrl, sent = env
    run(db.access_points.update_one({"id": "ap1"}, {"$set": {"passage_mode": "simples"}}))
    res = _access(db)
    assert "passage" not in res["event"] and run(db.people.find_one({"id": "p1"}))["current_area_id"] == "int"
    assert run(passage.on_sensor(ctrl)) is None  # sensor ignorado neste modo


def test_intelbras_doorstatus_confirms(env):
    db, ctrl, sent = env
    res = _access(db)
    body = (b"--myboundary\r\nContent-Type: text/plain\r\n\r\n" +
            json.dumps({"Events": [{"Code": "DoorStatus", "Data": {"Status": "Open", "UTC": 1}}]}).encode() + b"\r\n--myboundary--\r\n")
    run(intelbras_ingest.handle_notification(ctrl, body, ""))
    assert run(db.access_events.find_one({"id": res["event"]["id"]}))["passage"] == "confirmada"


def test_configure_door_sends_sensor_settings(env, monkeypatch):
    calls = []

    async def _req(drv, method, cgi, query="", body=None, timeout=8):
        calls.append(query)
        return {"ok": True, "code": 200, "text": "OK", "detail": ""}
    monkeypatch.setattr(intelbras.IntelbrasDriver, "_req", _req)
    ap = {"passage_mode": "confirmacao", "relay_time": 3, "door_open_time": 15, "sensor_type": "NF"}
    assert run(intelbras.IntelbrasDriver({"ip": "x"}).configure_door(ap))["ok"]
    assert "UnlockHoldInterval=3000" in calls[0] and "CloseTimeout=15" in calls[0] and "SensorEnable=true" in calls[0]
    assert "SensorType=1" in calls[1]

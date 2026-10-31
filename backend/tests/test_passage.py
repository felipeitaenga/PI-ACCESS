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
    ev = run(db.access_events.find_one({}, {"_id": 0}))  # também aparece no Ao vivo
    assert ev["person_name"] == "Giro sem liberação" and ev["access_result"] == "denied" and ev["passage"] == "nao_autorizada"
    assert ev["person_photo"].startswith("data:image/svg+xml")  # selo AL
    assert any(m["type"] == "access_event" for m in sent)


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


def _fake_device(monkeypatch, accept=True):
    """Facial falso: guarda o que o setConfig gravou e devolve no getConfig."""
    calls, cfg = [], {}

    async def _req(drv, method, cgi, query="", body=None, timeout=8):
        calls.append(query)
        if "setConfig" in query:
            k, v = query.split("&", 1)[1].split("=", 1)
            if accept or "SensorEnable" not in k:
                cfg["table." + k] = v
            return {"ok": True, "code": 200, "text": "OK", "detail": ""}
        return {"ok": True, "code": 200, "text": "\n".join(f"{k}={v}" for k, v in cfg.items()), "detail": ""}
    monkeypatch.setattr(intelbras.IntelbrasDriver, "_req", _req)
    return calls, cfg


def test_configure_door_sends_each_setting_and_verifies(env, monkeypatch):
    calls, cfg = _fake_device(monkeypatch)
    ap = {"passage_mode": "confirmacao", "relay_time": 3, "door_open_time": 15, "sensor_type": "NA"}
    r = run(intelbras.IntelbrasDriver({"ip": "x"}).configure_door(ap))
    assert r["ok"], r
    assert cfg["table.AccessControl[0].SensorEnable"] == "true" and cfg["table.AccessControl[0].UnlockHoldInterval"] == "3000"
    assert cfg["table.AccessControl[0].SensorType"] == "1"  # NA = 1 no SS 3532 MF W (testado)
    assert sum("setConfig" in c for c in calls) >= 4 and calls[-1].startswith("action=getConfig")


def test_configure_door_nf_and_reports_refused(env, monkeypatch):
    _, cfg = _fake_device(monkeypatch)
    run(intelbras.IntelbrasDriver({"ip": "x"}).configure_door({"passage_mode": "confirmacao", "sensor_type": "NF"}))
    assert cfg["table.AccessControl[0].SensorType"] == "0"
    _fake_device(monkeypatch, accept=False)
    r = run(intelbras.IntelbrasDriver({"ip": "x"}).configure_door({"passage_mode": "confirmacao"}))
    assert not r["ok"] and "SensorEnable" in r["detail"]


def _face_body(status, utc):
    return (b"--myboundary\r\nContent-Type: text/plain\r\n\r\n" +
            json.dumps({"Events": [{"Code": "AccessControl", "Data": {"UserID": "7", "Method": 15, "Status": status,
                                                                     "Type": "Entry", "UTC": utc}}]}).encode()
            + b"\r\n--myboundary--\r\n")


def test_double_notification_of_same_read_creates_one_pending(env):
    db, ctrl, sent = env
    run(db.device_uids.insert_one({"_id": "p1", "uid": 7}))
    now = int(datetime.now(timezone.utc).timestamp())
    r1 = run(intelbras_ingest.handle_notification(ctrl, _face_body(0, now), ""))
    r2 = run(intelbras_ingest.handle_notification(ctrl, _face_body(1, now + 1), ""))
    assert r1["auth"] == "true" and r2 == r1
    assert run(db.access_events.count_documents({"person_id": "p1"})) == 1
    assert run(db.passages.count_documents({"status": "pendente"})) == 1
    assert run(passage.on_sensor(ctrl)) == "confirmada"


def test_photo_from_second_notification_fills_event(env):
    db, ctrl, sent = env
    run(db.device_uids.insert_one({"_id": "p1", "uid": 7}))
    now = int(datetime.now(timezone.utc).timestamp())
    run(intelbras_ingest.handle_notification(ctrl, _face_body(0, now), ""))  # sem foto
    jpeg = b"\xff\xd8\xff\xe0FAKE"
    body2 = _face_body(1, now + 1).replace(b"\r\n--myboundary--", b"\r\n--myboundary\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n--myboundary--")
    run(intelbras_ingest.handle_notification(ctrl, body2, ""))
    ev = run(db.access_events.find_one({"person_id": "p1"}, {"_id": 0}))
    assert ev["captured_photo"].startswith("data:image/jpeg;base64,")
    assert any(m["type"] == "access_event_update" and m["data"].get("captured_photo") for m in sent)


def _button_body():
    return (b"--myboundary\r\nContent-Type: text/plain\r\n\r\n" +
            json.dumps({"Events": [{"Code": "AccessControl", "Data": {"UserID": "", "CardNo": "", "Method": 5, "Status": 1,
                                                                     "ErrorCode": 0, "Type": "Entry", "UTC": 1730000000}}]}).encode()
            + b"\r\n--myboundary--\r\n")


def test_exit_button_is_logged_and_next_turn_is_not_unauthorized(env):
    db, ctrl, sent = env
    r = run(intelbras_ingest.handle_notification(ctrl, _button_body(), ""))
    assert r["auth"] == "false"  # o facial já abriu sozinho
    ev = run(db.access_events.find_one({}, {"_id": 0}))
    assert ev["person_name"] == "Botão de saída" and ev["access_result"] == "granted" and ev["credential_type"] == "botao"
    assert ev["person_photo"].startswith("data:image/svg+xml") and ev["captured_photo"] == ""  # selo BT
    assert run(passage.on_sensor(ctrl)) == "remoto"  # giro logo após o botão: sem alarme
    assert run(db.alarms.count_documents({})) == 0


def test_unrecognized_face_reason(env):
    db, ctrl, sent = env
    body = (b"--myboundary\r\nContent-Type: text/plain\r\n\r\n" +
            json.dumps({"Events": [{"Code": "AccessControl", "Data": {"UserID": "", "Method": 15, "Status": 0, "ErrorCode": 16,
                                                                     "UTC": int(datetime.now(timezone.utc).timestamp())}}]}).encode()
            + b"\r\n--myboundary--\r\n")
    run(intelbras_ingest.handle_notification(ctrl, body, ""))
    assert "Rosto não reconhecido" in run(db.access_events.find_one({}, {"_id": 0}))["reason"]


def test_remote_open_is_not_unauthorized(env):
    db, ctrl, sent = env
    run(db.access_points.update_one({"id": "ap1"}, {"$set": {"last_remote_open": datetime.now(timezone.utc).isoformat()}}))
    assert run(passage.on_sensor(ctrl)) == "remoto"
    assert run(db.alarms.count_documents({})) == 0

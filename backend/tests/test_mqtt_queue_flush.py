"""Fila do facial: reenvio um a um com Ack ao voltar online e atualização do histórico."""
import asyncio
import os
from datetime import datetime, timedelta, timezone

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

import beward_ingest
import mqtt_bus
from models import new_id, now_iso

DEV = "TEST_QDEV_991"
_LOOP = asyncio.new_event_loop()
db = AsyncIOMotorClient(os.environ["MONGO_URL"], io_loop=_LOOP)[os.environ["DB_NAME"]]


def run(c):
    return _LOOP.run_until_complete(c)


class FakeDevice:
    """Responde Ack a cada comando publicado, depois de um pequeno atraso (simula o facial)."""
    def __init__(self, bus, fail_ids=(), silent_ids=()):
        self.bus, self.sent, self.fail, self.silent = bus, [], set(fail_ids), set(silent_ids)

    def publish(self, dev, payload):
        mid = str(payload.get("messageId"))
        self.sent.append(mid)
        if mid in self.silent:
            return True
        ack = {"messageId": mid, "code": "200", "info": {"result": "fail" if mid in self.fail else "ok", "detail": "erro foto" if mid in self.fail else ""}}
        self.bus.loop.call_later(0.05, lambda: (self.bus.pending.pop(mid, None) or _dummy()).set_result(ack))
        return True


class _dummy:
    def set_result(self, _):
        pass


@pytest.fixture()
def env(monkeypatch):
    # conexão e loop próprios: não depende do loop deixado por outros arquivos de teste
    monkeypatch.setattr(mqtt_bus, "db", db)
    monkeypatch.setattr(beward_ingest, "db", db)
    loop = _LOOP
    bus = mqtt_bus.MqttBus()
    bus.loop = loop
    ctrl = {"id": new_id(), "name": "TEST_ Facial fila", "beward_device_id": DEV, "device_id": DEV, "brand": "beward_mqtt",
            "model_type": "beward_facial", "last_heartbeat": now_iso()}
    run(db.controllers.insert_one(dict(ctrl)))
    yield bus, ctrl
    run(db.controllers.delete_many({"beward_device_id": DEV}))
    run(db.mqtt_commands.delete_many({"device_id": DEV}))
    run(db.sync_jobs.delete_many({"device_name": {"$regex": "^TEST_"}}))


def _cmd(mid, pid, created=None):
    return {"id": new_id(), "messageId": mid, "device_id": DEV, "operator": "DeletePersons", "status": "queued",
            "created_at": created or now_iso(), "payload": {"operator": "DeletePersons", "messageId": mid, "info": {"customId": [pid]}}}


def test_flush_waits_ack_in_order_and_updates_history(env):
    bus, ctrl = env
    t0 = datetime.now(timezone.utc) - timedelta(days=3)
    cmds = [_cmd(f"TEST-m{i}", f"TEST_p{i}", (t0 + timedelta(seconds=i)).isoformat()) for i in range(3)]
    run(db.mqtt_commands.insert_many([dict(c) for c in cmds]))
    # linha nova (com message_id), linha antiga (sem message_id) e sincroniza\u00e7\u00e3o completa
    run(db.sync_jobs.insert_one({"id": "TEST_j0", "device_name": "TEST_ Visitante: A", "person_id": "TEST_p0", "started_at": cmds[0]["created_at"],
                                 "status": "erro", "success": 0, "devices": [{"controller_id": ctrl["id"], "status": "erro", "error": "facial offline \u2014 comando na fila", "message_id": "TEST-m0"}]}))
    run(db.sync_jobs.insert_one({"id": "TEST_j1", "device_name": "TEST_ Visitante: B", "person_id": "TEST_p1", "started_at": cmds[1]["created_at"],
                                 "status": "erro", "success": 0, "devices": [{"controller_id": ctrl["id"], "status": "erro", "error": "facial offline \u2014 comando na fila"}]}))
    run(db.sync_jobs.insert_one({"id": "TEST_j2", "device_name": "TEST_ Facial fila", "started_at": cmds[2]["created_at"], "status": "erro", "success": 0, "total": 1,
                                 "errors": [{"person_id": "TEST_p2", "name": "C", "error": "sem Ack \u2014 comando na fila", "message_id": "TEST-m2"}]}))
    fake = FakeDevice(bus, fail_ids={"TEST-m1"})
    bus.publish_raw = fake.publish
    res = run(bus.flush_queue(DEV))
    assert fake.sent == ["TEST-m0", "TEST-m1", "TEST-m2"]
    assert res == {"sent": 3, "pending": 0}
    st = {c["messageId"]: c["status"] for c in run(db.mqtt_commands.find({"device_id": DEV}, {"_id": 0}).to_list(10))}
    assert st == {"TEST-m0": "ack", "TEST-m1": "erro", "TEST-m2": "ack"}
    j0, j1, j2 = (run(db.sync_jobs.find_one({"id": i}, {"_id": 0})) for i in ("TEST_j0", "TEST_j1", "TEST_j2"))
    assert j0["status"] == "concluido" and j0["devices"][0]["status"] == "ok"
    assert j1["status"] == "erro" and j1["devices"][0]["error"] == "erro foto"
    assert j2["status"] == "concluido" and j2["errors"] == [] and j2["success"] == 1


def test_flush_stops_without_ack_and_keeps_queue(env, monkeypatch):
    bus, _ = env
    monkeypatch.setitem(mqtt_bus.ACK_TIMEOUT_BY_OP, "DeletePersons", 0.3)
    run(db.mqtt_commands.insert_many([_cmd("TEST-s0", "TEST_x0"), _cmd("TEST-s1", "TEST_x1")]))
    fake = FakeDevice(bus, silent_ids={"TEST-s0"})
    bus.publish_raw = fake.publish
    res = run(bus.flush_queue(DEV))
    assert fake.sent == ["TEST-s0"] and res == {"sent": 0, "pending": 2}
    # na pr\u00f3xima volta (facial respondendo) a fila esvazia
    bus.publish_raw = FakeDevice(bus).publish
    assert run(bus.flush_queue(DEV)) == {"sent": 2, "pending": 0}


def test_offline_command_returns_message_id(env):
    bus, _ = env
    r = run(bus.command(DEV, "DeletePersons", {"customId": ["TEST_z"]}, online=False))
    assert r["queued"] and r["message_id"].startswith("nx-")
    assert run(db.mqtt_commands.count_documents({"messageId": r["message_id"], "status": "queued"})) == 1


def test_old_settime_is_discarded_and_clock_set_after_flush(env, monkeypatch):
    bus, ctrl = env
    old = _cmd("TEST-t0", "x")
    old.update({"operator": "SetSysTime", "payload": {"operator": "SetSysTime", "messageId": "TEST-t0", "info": {"SysTime": "2026-10-11 08:00:00"}}})
    run(db.mqtt_commands.insert_many([old, _cmd("TEST-t1", "TEST_y")]))
    fake = FakeDevice(bus)
    bus.publish_raw = fake.publish
    clock = []

    async def fake_sync(c, force=False):
        clock.append((c["id"], force))
        return {"ok": True}
    monkeypatch.setattr(beward_ingest, "sync_time", fake_sync)
    assert run(bus.flush_queue(DEV)) == {"sent": 1, "pending": 0}
    assert fake.sent == ["TEST-t1"]
    assert run(db.mqtt_commands.find_one({"messageId": "TEST-t0"}))["status"] == "descartado"
    assert clock == [(ctrl["id"], True)]


def test_set_datetime_never_queues(env, monkeypatch):
    from drivers.beward import BewardMqttDriver
    monkeypatch.setattr(mqtt_bus, "bus", env[0])
    drv = BewardMqttDriver({**env[1], "online": False, "last_heartbeat": "2020-01-01T00:00:00+00:00"})
    r = run(drv.set_datetime())
    assert r["ok"] is False and not r.get("queued")
    assert run(db.mqtt_commands.count_documents({"device_id": DEV, "operator": "SetSysTime"})) == 0


def test_failed_time_sync_retries_soon(env, monkeypatch):
    _, ctrl = env

    class Drv:
        async def set_datetime(self):
            return {"ok": False, "detail": "sem Ack do facial em 10 s"}
    import drivers.factory
    monkeypatch.setattr(drivers.factory, "get_driver", lambda c: Drv())
    run(beward_ingest.sync_time(ctrl, force=True))
    c = run(db.controllers.find_one({"id": ctrl["id"]}, {"_id": 0}))
    assert c["time_sync_ok"] is False and "time_synced_at" not in c and c["time_sync_tried_at"]
    assert beward_ingest._age_s(c.get("time_synced_at")) > beward_ingest.TIME_SYNC_HOURS * 3600  # watch_once tenta de novo


def test_door_commands_never_queue_and_old_ones_are_discarded(env, monkeypatch):
    """Abrir porta / deixar liberada / reiniciar não podem ser executados horas depois, quando o facial volta."""
    from drivers.beward import BewardMqttDriver
    bus, ctrl = env
    monkeypatch.setattr(mqtt_bus, "bus", bus)
    drv = BewardMqttDriver({**ctrl, "online": False, "last_heartbeat": "2020-01-01T00:00:00+00:00"})
    for r in (run(drv.open_door("1")), run(drv.set_door_mode("1", "liberada")), run(drv.reboot())):
        assert r["ok"] is False and not r.get("queued")
    assert run(db.mqtt_commands.count_documents({"device_id": DEV})) == 0
    # comandos antigos que ficaram na fila antes desta versão são descartados
    olds = []
    for i, op in enumerate(("Unlock", "SetKeepOpen", "RebootDevice")):
        c = _cmd(f"TEST-d{i}", "x")
        c.update({"operator": op, "payload": {"operator": op, "messageId": f"TEST-d{i}", "info": {}}})
        olds.append(c)
    run(db.mqtt_commands.insert_many(olds + [_cmd("TEST-d9", "TEST_w")]))
    fake = FakeDevice(bus)
    bus.publish_raw = fake.publish
    monkeypatch.setattr(beward_ingest, "sync_time", lambda c, force=False: asyncio.sleep(0, {"ok": True}))
    assert run(bus.flush_queue(DEV)) == {"sent": 1, "pending": 0}
    assert fake.sent == ["TEST-d9"]
    assert run(db.mqtt_commands.count_documents({"device_id": DEV, "status": "descartado"})) == 3


def test_watch_and_reconnect_find_queue_by_beward_device_id(env, monkeypatch):
    """O controlador guarda o ID do facial em beward_device_id (não existe "device_id" no cadastro)."""
    bus, ctrl = env
    run(db.controllers.update_one({"id": ctrl["id"]}, {"$unset": {"device_id": ""}}))
    run(db.mqtt_commands.insert_one(_cmd("TEST-w0", "TEST_q")))
    called = []

    async def fake_flush(dev):
        called.append(dev)
        return {"sent": 0, "pending": 0}
    monkeypatch.setattr(bus, "flush_queue", fake_flush)
    monkeypatch.setattr(beward_ingest, "bus", bus)
    monkeypatch.setattr(beward_ingest, "sync_time", lambda c, force=False: asyncio.sleep(0, {"ok": True}))
    run(db.controllers.update_one({"id": ctrl["id"]}, {"$set": {"time_sync_ok": True, "time_synced_at": now_iso()}}))
    run(beward_ingest.watch_once())
    run(bus.flush_online())
    run(asyncio.sleep(0.05))
    assert called and all(d == DEV for d in called)


def test_set_datetime_uses_iso_t_format(env, monkeypatch):
    """O facial só aplica a hora com "T" (2026-10-25T19:53:00); com espaço responde ok e ignora."""
    import re
    from drivers.beward import BewardMqttDriver
    bus, ctrl = env
    monkeypatch.setattr(mqtt_bus, "bus", bus)
    bus.connected = True
    fake = FakeDevice(bus)
    sent = []
    bus.publish_raw = lambda dev, payload: sent.append(payload) or fake.publish(dev, payload)
    r = run(BewardMqttDriver({**ctrl, "last_heartbeat": now_iso()}).set_datetime())
    assert r["ok"] is True
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", sent[0]["info"]["SysTime"])


def test_delete_person_format_and_ack(env, monkeypatch):
    """Facial 1457460: DeletePersons só apaga com DataBegin/PersonNum/DataEnd; a resposta traz DelErrNum/DelSucNum."""
    from drivers.beward import BewardMqttDriver
    bus, ctrl = env
    monkeypatch.setattr(mqtt_bus, "bus", bus)
    bus.connected = True
    sent = []

    def pub(dev, payload):
        sent.append(payload)
        mid = payload["messageId"]
        ack = {"messageId": mid, "info": {"DelErrNum": "0", "DelSucNum": "1", "DelSucInfo": [{"customId": "TEST_v"}]}}
        bus.loop.call_later(0.05, lambda: (bus.pending.pop(mid, None) or _dummy()).set_result(ack))
        return True
    bus.publish_raw = pub
    r = run(BewardMqttDriver({**ctrl, "last_heartbeat": now_iso()}).delete_person("TEST_v"))
    assert r["ok"] is True
    exp = {"DataBegin": "BeginFlag", "PersonNum": 1, "customId": ["TEST_v"], "DataEnd": "EndFlag"}
    assert {k: sent[0]["info"].get(k) for k in exp} == exp
    ok, _c, _d, _i = mqtt_bus._ack_result({"info": {"DelErrNum": "1", "DelSucNum": "0", "DelErrInfo": [{"customId": "x"}]}})
    assert ok is False


def test_lenient_json_from_device():
    bad = '{\n"messageId":"m1",\n"operator": "DeletePersons-Ack",\n"info": {\n"facesluiceId":"1",\n"result":"fail"\n"detail":"can not find DataBegin",\n}\n}\n'
    d = mqtt_bus.parse_json_lenient(bad)
    assert d["messageId"] == "m1" and d["info"]["result"] == "fail" and d["info"]["detail"] == "can not find DataBegin"


def test_flush_upgrades_old_delete_payload(env, monkeypatch):
    bus, _ = env
    run(db.mqtt_commands.insert_one(_cmd("TEST-old-del", "TEST_old")))  # payload antigo: sem DataBegin
    fake = FakeDevice(bus)
    sent = []
    bus.publish_raw = lambda dev, p: sent.append(p) or fake.publish(dev, p)
    monkeypatch.setattr(beward_ingest, "sync_time", lambda c, force=False: asyncio.sleep(0, {"ok": True}))
    assert run(bus.flush_queue(DEV))["sent"] == 1
    assert sent[0]["info"]["DataBegin"] == "BeginFlag" and sent[0]["info"]["customId"] == ["TEST_old"]


def test_sync_person_sends_no_cpf_or_phone(env, monkeypatch):
    from drivers.beward import BewardMqttDriver
    bus, ctrl = env
    monkeypatch.setattr(mqtt_bus, "bus", bus)
    drv = BewardMqttDriver({**ctrl, "last_heartbeat": now_iso()})
    seen = {}

    async def fake_publish(op, info=None, queue=True):
        seen.update(info or {})
        return {"ok": True}

    async def fake_photo(_):
        return "AAAA"
    monkeypatch.setattr(drv, "_publish", fake_publish)
    monkeypatch.setattr(drv, "_photo_b64", fake_photo)
    run(drv.sync_person({"id": "TEST_p", "name": "Fulano", "document": "11144477735", "phone": "11999990000", "photo": "x"}))
    assert seen["idCard"] == "" and seen["telnum"] == ""

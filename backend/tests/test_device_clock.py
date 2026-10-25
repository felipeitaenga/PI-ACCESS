"""Hora do facial: diferença entre o relógio do equipamento e o do servidor."""
import asyncio
import os
from datetime import datetime, timedelta

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

import beward_ingest
from models import new_id, now_iso

DEV = "TEST_CLKDEV_77"
_LOOP = asyncio.new_event_loop()
db = AsyncIOMotorClient(os.environ["MONGO_URL"], io_loop=_LOOP)[os.environ["DB_NAME"]]


def run(c):
    return _LOOP.run_until_complete(c)


def dev_str(delta_s):
    return (datetime.now(beward_ingest.TZ) + timedelta(seconds=delta_s)).strftime("%Y-%m-%d %H:%M:%S")


@pytest.fixture()
def ctrl(monkeypatch):
    monkeypatch.setattr(beward_ingest, "db", db)
    sent = []
    monkeypatch.setattr(beward_ingest.bus, "publish_raw", lambda d, p: sent.append(p) or True)
    async def no_record(*a, **k):
        return {}
    async def no_stranger(*a, **k):
        return None
    monkeypatch.setattr(beward_ingest, "record", no_record)
    monkeypatch.setattr(beward_ingest, "stranger", no_stranger)
    c = {"id": new_id(), "name": "TEST_ Facial relogio", "beward_device_id": DEV, "device_id": DEV, "brand": "beward_mqtt",
         "model_type": "beward_facial", "online": True, "last_heartbeat": now_iso(), "time_synced_at": now_iso(), "time_sync_ok": True}
    run(db.controllers.insert_one(dict(c)))
    yield c
    run(db.controllers.delete_many({"beward_device_id": DEV}))


def _clock(c):
    return run(db.controllers.find_one({"id": c["id"]}, {"_id": 0}))["device_clock"]


def test_heartbeat_time_records_drift(ctrl):
    run(beward_ingest.on_mqtt("mqtt/face/heartbeat", "HeartBeat", {"info": {"facesluiceId": DEV, "time": dev_str(-3 * 3600)}}, DEV))
    c = _clock(ctrl)
    assert c["source"] == "heartbeat" and abs(c["drift_s"] + 3 * 3600) < 5


def test_realtime_event_records_drift_but_resent_event_does_not(ctrl):
    run(beward_ingest.on_mqtt("mqtt/face/Rec", "RecPush", {"info": {"facesluiceId": DEV, "RecordID": "1", "Sendintime": 1, "time": dev_str(600)}}, DEV))
    assert abs(_clock(ctrl)["drift_s"] - 600) < 5
    # registro antigo reenviado (Sendintime=0) n\u00e3o mexe na leitura
    run(beward_ingest.on_mqtt("mqtt/face/Rec", "RecPush", {"info": {"facesluiceId": DEV, "RecordID": "2", "Sendintime": 0, "time": dev_str(-86400)}}, DEV))
    assert abs(_clock(ctrl)["drift_s"] - 600) < 5


def test_invalid_time_ignored_and_successful_sync_resets(ctrl, monkeypatch):
    assert run(beward_ingest.clock_reading(ctrl, "lixo", "evento")) is None

    class Drv:
        async def set_datetime(self):
            return {"ok": True}
    import drivers.factory
    monkeypatch.setattr(drivers.factory, "get_driver", lambda c: Drv())
    run(beward_ingest.clock_reading(ctrl, dev_str(-7200), "evento"))
    run(beward_ingest.sync_time(ctrl, force=True))
    c = _clock(ctrl)
    assert c["drift_s"] == 0 and c["source"] == "acerto"

"""Testes para BewardMqttDriver._photo_b64 e sync_person (bug: foto não chegava ao facial).

Comportamentos verificados:
- _photo_b64 baixa URL https e devolve base64 não vazio e < 270000 chars
- _photo_b64 aceita data URL e devolve base64 puro
- _photo_b64('') => ''
- sync_person em pessoa SEM foto => {ok:False, detail contém 'sem foto'}
- sync_person em pessoa COM foto (controller TEST999, sem heartbeat) =>
  {queued:True} e doc em mqtt_commands tem payload.info.pic começando com 'data:image/jpeg;base64,'
- Limpa mqtt_commands com device_id TEST999 no fim.
"""
import asyncio
import os
import sys
import base64
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

# conftest já carregou /app/backend/.env

# Loop único (motor liga ao primeiro loop) — precisa ser setado ANTES de importar database
_LOOP = asyncio.new_event_loop()
asyncio.set_event_loop(_LOOP)


def _run(coro):
    return _LOOP.run_until_complete(coro)


from drivers.beward import BewardMqttDriver  # noqa: E402
from database import db  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _bind_loop():
    asyncio.set_event_loop(_LOOP)
    yield


# PNG 1x1 vermelho — base64 válido
_TINY_PNG_B64 = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4"
                 "nGP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")


class TestPhotoB64:
    def setup_method(self):
        self.drv = BewardMqttDriver({"beward_device_id": "TEST999"})

    def test_empty_returns_empty(self):
        out = _run(self.drv._photo_b64(""))
        assert out == ""

    def test_data_url_returns_b64(self):
        data_url = f"data:image/png;base64,{_TINY_PNG_B64}"
        out = _run(self.drv._photo_b64(data_url))
        assert isinstance(out, str) and len(out) > 0
        # Deve ser base64 decodificável
        base64.b64decode(out)

    def test_https_url_downloads(self):
        out = _run(self.drv._photo_b64("https://i.pravatar.cc/200?img=5"))
        assert isinstance(out, str)
        assert len(out) > 100, f"expected non-empty b64, got len={len(out)}"
        assert len(out) < 270000, f"base64 too large: {len(out)}"
        base64.b64decode(out)


class TestSyncPerson:
    def setup_method(self):
        # Controller TEST999 sem last_heartbeat => offline => comando enfileirado
        self.drv = BewardMqttDriver({"beward_device_id": "TEST999"})

    def teardown_method(self):
        _run(db.mqtt_commands.delete_many({"device_id": "TEST999"}))

    def test_person_without_photo_returns_sem_foto(self):
        person = {"id": "TEST_pid_1", "name": "Sem Foto", "photo": ""}
        res = _run(self.drv.sync_person(person))
        assert res.get("ok") is False
        assert "sem foto" in (res.get("detail") or "").lower()

    def test_person_with_photo_queues_with_pic_prefix(self):
        person = {"id": "TEST_pid_2", "name": "Com Foto",
                  "photo": f"data:image/png;base64,{_TINY_PNG_B64}"}
        res = _run(self.drv.sync_person(person))
        # offline => queued
        assert res.get("queued") is True, f"expected queued=True, got {res}"
        # verifica mqtt_commands
        doc = _run(db.mqtt_commands.find_one({"device_id": "TEST999", "operator": "EditPerson"},
                                             {"_id": 0}, sort=[("created_at", -1)]))
        assert doc is not None, "no mqtt_commands doc inserted for TEST999"
        pic = doc["payload"]["info"].get("pic", "")
        assert pic.startswith("data:image/jpeg;base64,"), f"pic prefix wrong: {pic[:40]}"
        assert len(pic) > len("data:image/jpeg;base64,")


def teardown_module(module):
    # Limpeza final garantida
    try:
        _run(db.mqtt_commands.delete_many({"device_id": "TEST999"}))
    except Exception:
        pass

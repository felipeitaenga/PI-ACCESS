"""Liberação manual pelo operador: a partir de um evento negado ou direto no ponto."""
import asyncio
from datetime import datetime, timedelta, timezone

import mongomock_motor
import pytest
from fastapi import HTTPException

import access_service
import manual_release
import passage
import scope
import visits_core

_LOOP = asyncio.new_event_loop()
OP = {"id": "u1", "name": "Carlos Portaria", "role": "reception"}
ADMIN = {"id": "u0", "name": "Admin", "role": "admin"}


def run(c):
    return _LOOP.run_until_complete(c)


@pytest.fixture()
def env(monkeypatch):
    db = mongomock_motor.AsyncMongoMockClient()["t_manual"]
    for m in (access_service, manual_release, passage, scope, visits_core):
        monkeypatch.setattr(m, "db", db)
    sent, audit = [], []

    async def _bc(msg):
        sent.append(msg)

    async def _audit(*a, **k):
        audit.append(a)
    monkeypatch.setattr(manual_release.manager, "broadcast", _bc)
    monkeypatch.setattr(passage.manager, "broadcast", _bc)
    monkeypatch.setattr(manual_release, "log_audit", _audit)
    run(db.controllers.insert_one({"id": "c1", "name": "Catraca", "brand": "simulado", "deleted": False}))
    run(db.access_points.insert_one({"id": "ap1", "controller_id": "c1", "description": "Catraca 1", "direction": "entrada",
                                     "origin_area_id": "ext", "dest_area_id": "int", "deleted": False}))
    run(db.areas.insert_many([{"id": "int", "description": "Interna", "current_occupancy": 0},
                              {"id": "ext", "description": "Externa", "is_exterior": True}]))
    run(db.people.insert_one({"id": "p1", "name": "Mariana Costa", "status": "ativo", "person_type": "funcionario",
                              "photo_thumb": "data:image/jpeg;base64,AAA", "company_name": "Alfa"}))
    return db, sent, audit


def _denied(db, reason="Fora da faixa horária", minutes_ago=0, person="p1"):
    ev = {"id": f"ev-{reason[:5]}-{minutes_ago}", "timestamp": (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat(),
          "access_point_id": "ap1", "door_id": "ap1", "person_id": person, "person_name": "Mariana Costa", "person_type": "funcionario",
          "person_photo": "data:image/jpeg;base64,AAA", "captured_photo": "data:image/jpeg;base64,CAP",
          "access_result": "denied", "reason": reason}
    run(db.access_events.insert_one(dict(ev)))
    return ev


def test_release_denied_event_logs_person_photo_and_operator(env):
    db, sent, audit = env
    ev = _denied(db)
    r = run(manual_release.release(OP, None, "Esqueceu o crachá, conferido pelo RG", event_id=ev["id"]))
    new = r["event"]
    assert new["access_result"] == "granted" and new["manual"] and new["operator_name"] == "Carlos Portaria"
    assert new["person_id"] == "p1" and new["captured_photo"].endswith("CAP") and new["person_photo"].endswith("AAA")
    assert new["override_of"] == ev["id"] and new["original_reason"] == "Fora da faixa horária"
    orig = run(db.access_events.find_one({"id": ev["id"]}))
    assert orig["released_by_name"] == "Carlos Portaria" and orig["released_by_event"] == new["id"]
    assert run(db.people.find_one({"id": "p1"}))["current_area_id"] == "int"  # conta a entrada
    assert audit and "Esqueceu o crachá" in audit[0][4]
    assert any(m["type"] == "access_event_update" for m in sent)


def test_reason_required_and_no_double_release(env):
    db, *_ = env
    ev = _denied(db)
    with pytest.raises(HTTPException) as e:
        run(manual_release.release(OP, None, " ", event_id=ev["id"]))
    assert e.value.status_code == 422
    run(manual_release.release(OP, None, "ok liberado", event_id=ev["id"]))
    with pytest.raises(HTTPException) as e:
        run(manual_release.release(OP, None, "de novo", event_id=ev["id"]))
    assert e.value.status_code == 409 and "Carlos" in e.value.detail


def test_old_event_cannot_be_released(env):
    db, *_ = env
    ev = _denied(db, minutes_ago=30)
    with pytest.raises(HTTPException) as e:
        run(manual_release.release(OP, None, "atrasado", event_id=ev["id"]))
    assert e.value.status_code == 409


def test_impeditive_only_admin(env):
    db, *_ = env
    ev = _denied(db, reason="Categoria impeditiva")
    with pytest.raises(HTTPException) as e:
        run(manual_release.release(OP, None, "insistiu", event_id=ev["id"]))
    assert e.value.status_code == 403
    assert run(manual_release.release(ADMIN, None, "autorizado pela gerência", event_id=ev["id"]))["event"]["operator_name"] == "Admin"


def test_point_release_with_and_without_person(env):
    db, *_ = env
    r = run(manual_release.release(OP, "ap1", "Entrega de material", subject_kind="person", subject_id="p1"))
    assert r["event"]["person_name"] == "Mariana Costa" and r["event"]["person_photo"].endswith("AAA")
    r = run(manual_release.release(OP, "ap1", "Manutenção da catraca"))
    assert r["event"]["person_name"] == "Não identificado" and r["event"]["person_id"] is None
    assert run(db.access_points.find_one({"id": "ap1"}))["last_remote_open"]  # giro seguinte não vira alarme


def test_confirm_mode_point_waits_for_turn(env):
    db, *_ = env
    run(db.access_points.update_one({"id": "ap1"}, {"$set": {"passage_mode": "confirmacao"}}))
    ev = _denied(db)
    r = run(manual_release.release(OP, None, "liberado na portaria", event_id=ev["id"]))
    assert r["event"]["passage"] == "pendente"
    assert run(db.passages.count_documents({"event_id": r["event"]["id"]})) == 1
    assert run(db.people.find_one({"id": "p1"})).get("current_area_id") is None

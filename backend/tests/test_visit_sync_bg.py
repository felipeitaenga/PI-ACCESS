"""Envio da visita aos faciais em segundo plano (a portaria não espera o equipamento)."""
import asyncio

import mongomock_motor

import scope
from routers import visits

_LOOP = asyncio.new_event_loop()


def test_background_sync_updates_visit_and_notifies(monkeypatch):
    db = mongomock_motor.AsyncMongoMockClient()["t_vbg"]
    monkeypatch.setattr(visits, "db", db)
    sent = []

    async def _bc(m):
        sent.append(m)

    async def _sync(subject, label):
        return [{"controller_id": "c1", "name": "Facial", "status": "ok", "error": ""}]
    monkeypatch.setattr(visits.manager, "broadcast", _bc)
    monkeypatch.setattr(visits, "sync_to_devices", _sync)
    monkeypatch.setattr(visits, "visit_subject", lambda v, vi: {"id": v["id"]})
    _LOOP.run_until_complete(db.visits.insert_one({"id": "v1", "host_company_id": "co1"}))
    _LOOP.run_until_complete(visits._sync_visit_bg({"id": "x", "name": "Ana"}, {"id": "v1", "host_company_id": "co1"}))
    assert _LOOP.run_until_complete(db.visits.find_one({"id": "v1"}))["sync"][0]["status"] == "ok"
    m = sent[0]
    assert m["type"] == "visit_sync" and m["data"]["visit_id"] == "v1" and m["data"]["company_id"] == "co1"
    mgr = {"role": "company_manager", "company_ids": ["co1"]}
    assert scope.ws_visible(mgr, m) in (True, False)  # não quebra para gestor

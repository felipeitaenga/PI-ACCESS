"""Sincronização completa tira do facial cadastros que não deveriam estar lá (fixo excluído/inativo, visitante sem visita ativa)."""
import asyncio

import mongomock_motor

from routers import equipment

_LOOP = asyncio.new_event_loop()


def run(c):
    return _LOOP.run_until_complete(c)


class Drv:
    def __init__(self):
        self.deleted = []

    async def delete_person(self, ids):
        self.deleted.extend(ids)
        return {"ok": False, "info": {"DelErrNum": "1"}}  # facial respondeu (ex.: alguns não existiam): não é erro


def test_remove_stale(monkeypatch):
    db = mongomock_motor.AsyncMongoMockClient()["t_clean"]
    monkeypatch.setattr(equipment, "db", db)
    run(db.people.insert_many([{"id": "ativo", "status": "ativo"}, {"id": "excluido", "status": "inativo", "deleted": True},
                               {"id": "inativo", "status": "inativo"}]))
    run(db.visitors.insert_many([{"id": "vis_ativo"}, {"id": "vis_antigo"}]))
    run(db.visits.insert_many([{"id": "a", "visitor_id": "vis_ativo", "status": "presente"},
                               {"id": "b", "visitor_id": "vis_antigo", "status": "encerrada"}]))
    drv, job = Drv(), {"errors": []}
    n = run(equipment._remove_stale(drv, {"ativo", "vis_ativo"}, job))
    assert n == 3 and sorted(drv.deleted) == ["excluido", "inativo", "vis_antigo"]
    assert job["errors"] == []

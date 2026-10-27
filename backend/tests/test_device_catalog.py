"""Catálogo fabricante/modelo no cadastro de controladoras."""
import asyncio

import mongomock_motor
import pytest
from fastapi import HTTPException

import device_catalog as catalog
from routers import equipment

_LOOP = asyncio.new_event_loop()


def run(c):
    return _LOOP.run_until_complete(c)


@pytest.fixture(autouse=True)
def mem_db(monkeypatch):
    monkeypatch.setattr(equipment, "db", mongomock_motor.AsyncMongoMockClient()["t_cat"])


def test_catalog_shape():
    c = catalog.catalog()
    ids = {m["id"] for m in c["models"]}
    assert len(ids) == len(c["models"])  # ids únicos
    mans = {m["id"] for m in c["manufacturers"]}
    for m in c["models"]:
        assert m["manufacturer"] in mans and m["family"] in equipment.MODEL_TYPES
        assert m["status"] in ("homologado", "em_teste", "em_breve")
    for fam, mid in catalog.DEFAULT_BY_FAMILY.items():
        assert catalog.BY_ID[mid]["family"] == fam


def test_new_beward_by_catalog():
    d = run(equipment._ctrl_enrich({"id": "c1", "name": "Porta", "catalog_model": "beward_face", "transport": "mqtt"}))
    assert d["model_type"] == "beward_facial" and d["manufacturer"] == "beward" and d["brand"] == "beward_mqtt"
    assert d["model"] == "Beward Facial (Face Server)" and d["num_access_points"] == 1


def test_old_record_without_catalog_gets_default():
    d = run(equipment._ctrl_enrich({"id": "c2", "name": "Antigo", "model_type": "beward_facial", "transport": "http"}))
    assert d["catalog_model"] == "beward_face" and d["brand"] == "beward_http"


def test_em_breve_cannot_be_saved():
    with pytest.raises(HTTPException) as e:
        run(equipment._ctrl_enrich({"id": "c3", "name": "X", "catalog_model": "intelbras_ss3532mfw"}))
    assert e.value.status_code == 422 and "Intelbras SS 3532 MF W" in e.value.detail


def test_unknown_model_rejected():
    with pytest.raises(HTTPException):
        run(equipment._ctrl_enrich({"id": "c4", "name": "X", "catalog_model": "nao_existe"}))

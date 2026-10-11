"""Visitas: fim pela duração do tipo, validação de CPF/RG e expiração automática."""
import asyncio
import os
import sys
from datetime import datetime, timezone, timedelta

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from visits_core import (compute_end, type_hours, validate_doc, card_decimal, norm_plate,  # noqa: E402
                         device_dt, visits_tick, DEFAULT_SETTINGS)


def test_end_from_type_duration():
    start = "2026-10-11T10:00:00-03:00"
    assert compute_end(start, type_hours({"default_hours": 4}, DEFAULT_SETTINGS)).isoformat() == "2026-10-11T14:00:00-03:00"
    assert compute_end(start, type_hours({"default_hours": 0.5}, DEFAULT_SETTINGS)).isoformat() == "2026-10-11T10:30:00-03:00"
    assert compute_end(start, type_hours({}, {"default_hours": 8})).isoformat() == "2026-10-11T18:00:00-03:00"
    assert type_hours(None, {"default_hours": 6}) == 6


def test_cpf_validation():
    s = {"validate_cpf": True}
    assert validate_doc("cpf", "529.982.247-25", s) == ("529.982.247-25", None)
    assert validate_doc("cpf", "52998224725", s)[0] == "529.982.247-25"
    assert validate_doc("cpf", "529.982.247-24", s)[1] == "CPF inválido"
    assert validate_doc("cpf", "111.111.111-11", s)[1] == "CPF inválido"
    assert validate_doc("cpf", "123", {"validate_cpf": False})[1] is None


def test_rg_passport_other():
    assert validate_doc("rg", "abc", {"validate_rg": False})[1] is None
    assert validate_doc("rg", "12.345.678-X", {"validate_rg": True}) == ("12345678X", None)
    assert validate_doc("rg", "12A4", {"validate_rg": True})[1]
    assert validate_doc("passaporte", "fp123456", {})[0] == "FP123456"
    assert validate_doc("outro", "qualquer coisa", {})[1] is None


def test_card_plate_device_format():
    assert card_decimal("0x1A") == "26" and card_decimal("1A") == "26" and card_decimal("123") == "123"
    assert norm_plate("abc1d23") == ("ABC1D23", None)
    assert norm_plate("ABC1234") == ("ABC-1234", None)
    assert norm_plate("AB12")[1]
    assert device_dt("2026-10-11T13:00:00+00:00") == "2026-10-11 10:00:00"


@pytest.fixture
def db():
    from database import db as _db
    return _db


def test_auto_expiration(db):
    async def run():
        now = datetime.now(timezone.utc)
        vid, visit_id = "TEST_VISITOR_EXP", "TEST_VISIT_EXP"
        await db.visitors.insert_one({"id": vid, "name": "TEST_ Expira", "deleted": False})
        await db.visits.insert_one({"id": visit_id, "visitor_id": vid, "visitor_name": "TEST_ Expira", "status": "presente",
                                    "start_at": (now - timedelta(hours=2)).isoformat(),
                                    "end_at": (now - timedelta(minutes=1)).isoformat(), "deleted": False})
        try:
            await visits_tick()
            v = await db.visits.find_one({"id": visit_id})
            h = await db.visit_history.find_one({"visit_id": visit_id})
            assert v["status"] == "expirada" and h and h["action"] == "expirada"
        finally:
            await db.visits.delete_many({"id": visit_id})
            await db.visitors.delete_many({"id": vid})
            await db.visit_history.delete_many({"visit_id": visit_id})
            await db.sync_jobs.delete_many({"person_id": vid})
    asyncio.run(run())

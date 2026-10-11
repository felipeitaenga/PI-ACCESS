"""Testes unitários do driver BEWARD (conversões puras e mapeamentos)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from drivers.beward_common import (time_range_to_strategy, strategy_id_for, map_verify, dedup_key)  # noqa


def _tr():
    return {"id": "tr-abc", "description": "Comercial", "weekdays": [1, 2, 3, 4, 5],
            "valid_on_holidays": False, "intervals": [{"start": "07:00", "end": "18:00"}]}


def test_strategy_id_stable():
    assert strategy_id_for("tr-abc") == strategy_id_for("tr-abc")
    assert strategy_id_for("tr-abc") != strategy_id_for("tr-xyz")
    assert 0 <= strategy_id_for("tr-abc") < 2 ** 31


def test_strategy_includes_only_active_days():
    s = time_range_to_strategy(_tr())
    assert "monday" in s and "friday" in s
    assert "sunday" not in s and "saturday" not in s  # dias sem acesso não enviados
    assert s["monday"][0] == {"startTime": "07:00:00", "endTime": "18:00:00"}
    assert s["strategyName"] == "Comercial"


def test_strategy_holiday_empty_when_not_valid():
    hols = [{"date": "2026-09-07", "enabled": True}]
    s = time_range_to_strategy(_tr(), hols)
    assert s["holidayInfo"][0]["holidayPeriod"] == [{"startTime": "00:00:00", "endTime": "00:00:00"}]


def test_strategy_holiday_uses_intervals_when_valid():
    tr = {**_tr(), "valid_on_holidays": True}
    hols = [{"date": "2026-09-07", "enabled": True}]
    s = time_range_to_strategy(tr, hols)
    assert s["holidayInfo"][0]["holidayPeriod"] == [{"startTime": "07:00:00", "endTime": "18:00:00"}]


def test_map_verify_statuses():
    assert map_verify(1, 1)["access_result"] == "granted"
    assert map_verify(2, 21)["access_result"] == "denied"
    assert map_verify(3, 1)["reason"] == "Não cadastrado"
    assert map_verify(24, 1)["reason"] == "Fora da política de horário"


def test_map_verify_types():
    assert map_verify(1, 1)["verify_type"] == "facial"
    assert map_verify(1, 21)["verify_type"] == "cartao_rfid"
    assert map_verify(1, 24)["verify_type"] == "wiegand"
    assert map_verify(1, 27)["verify_type"] == "remoto_http"


def test_retroactive_flag():
    assert map_verify(1, 1, sendintime=0)["retroactive"] is True   # reenvio offline
    assert map_verify(1, 27, sendintime=1)["retroactive"] is True  # abertura remota HTTP
    assert map_verify(1, 1, sendintime=1)["retroactive"] is False


def test_dedup_key():
    assert dedup_key("D1", "2026-01-01T10:00:00", "P1") == "D1:2026-01-01T10:00:00:P1"
    assert dedup_key("D1", "t", "P1") != dedup_key("D1", "t", "P2")

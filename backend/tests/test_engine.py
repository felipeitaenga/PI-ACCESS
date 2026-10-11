"""Testes unitários do motor de decisão de acesso."""
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine import decide, time_range_valid, is_holiday  # noqa: E402

SP = ZoneInfo("America/Sao_Paulo")
TR_LIVRE = {"id": "tr_livre", "enabled": True, "weekdays": [0, 1, 2, 3, 4, 5, 6],
            "valid_on_holidays": True, "intervals": [{"start": "00:00", "end": "23:59"}]}
TR_COM = {"id": "tr_com", "enabled": True, "weekdays": [1, 2, 3, 4, 5],
          "valid_on_holidays": False, "intervals": [{"start": "07:00", "end": "18:00"}]}
TR_BY = {"tr_livre": TR_LIVRE, "tr_com": TR_COM}

AREA_INT = {"id": "a_int", "description": "Interna", "anti_double_entry": False, "max_occupancy": 0, "current_occupancy": 0}
AREA_EXT_P = {"id": "a_ext_p", "description": "Externa Pedestre", "is_exterior": False}
AP = {"id": "ap1", "origin_area_id": "a_ext_p", "dest_area_id": "a_int", "direction": "entrada", "site_id": "s1"}

WED_10H = datetime(2026, 6, 10, 10, 0, tzinfo=SP)   # quarta 10h
SUN_10H = datetime(2026, 6, 14, 10, 0, tzinfo=SP)   # domingo 10h
WED_22H = datetime(2026, 6, 10, 22, 0, tzinfo=SP)   # quarta 22h


def _person(**kw):
    base = {"id": "p1", "status": "ativo", "current_area_id": "a_ext_p", "category_ids": []}
    base.update(kw)
    return base


def _cat(**kw):
    base = {"id": "c1", "code": "CAT", "enabled": True, "impeditive": False,
            "control_origin": False, "control_anti_double": False,
            "require_escort_unconditional": False, "reentry_timed": False, "reentry_minutes": 0,
            "access_areas": [{"area_id": "a_int", "time_range_id": "tr_livre", "require_escort": False}]}
    base.update(kw)
    return base


def test_grant_basic():
    r = decide(_person(), AP, AREA_INT, AREA_EXT_P, [_cat()], TR_BY, [], WED_10H, site_id="s1")
    assert r["granted"] is True
    assert r["reason"] == "Acesso liberado"


def test_deny_inactive_person():
    r = decide(_person(status="bloqueado"), AP, AREA_INT, AREA_EXT_P, [_cat()], TR_BY, [], WED_10H)
    assert r["granted"] is False
    assert r["reason"] == "Pessoa inativa/bloqueada"


def test_deny_impeditive_prevails():
    cats = [_cat(), _cat(id="c2", code="BLACK", impeditive=True)]
    r = decide(_person(), AP, AREA_INT, AREA_EXT_P, cats, TR_BY, [], WED_10H)
    assert r["granted"] is False
    assert r["reason"] == "Categoria impeditiva"


def test_deny_out_of_time_range():
    cat = _cat(access_areas=[{"area_id": "a_int", "time_range_id": "tr_com", "require_escort": False}])
    r = decide(_person(), AP, AREA_INT, AREA_EXT_P, [cat], TR_BY, [], WED_22H, site_id="s1")
    assert r["granted"] is False
    assert r["reason"] == "Fora da faixa horária"


def test_deny_no_permission_for_area():
    cat = _cat(access_areas=[{"area_id": "outra", "time_range_id": "tr_livre"}])
    r = decide(_person(), AP, AREA_INT, AREA_EXT_P, [cat], TR_BY, [], WED_10H)
    assert r["granted"] is False
    assert r["reason"] == "Sem permissão para a área"


def test_deny_invalid_origin():
    cat = _cat(control_origin=True)
    r = decide(_person(current_area_id="outra_area"), AP, AREA_INT, AREA_EXT_P, [cat], TR_BY, [], WED_10H, site_id="s1")
    assert r["granted"] is False
    assert r["reason"] == "Origem inválida"


def test_deny_anti_double_entry():
    cat = _cat(control_anti_double=True)
    r = decide(_person(current_area_id="a_int"), AP, AREA_INT, AREA_EXT_P, [cat], TR_BY, [], WED_10H, site_id="s1")
    assert r["granted"] is False
    assert r["reason"] == "Anti-dupla entrada"


def test_deny_max_occupancy():
    area = {**AREA_INT, "max_occupancy": 5, "current_occupancy": 5}
    r = decide(_person(), AP, area, AREA_EXT_P, [_cat()], TR_BY, [], WED_10H, site_id="s1")
    assert r["granted"] is False
    assert r["reason"] == "Lotação máxima"


def test_holiday_blocks_commercial():
    holidays = [{"date": "2026-06-10", "enabled": True, "scope": "all", "recurring_annual": False}]
    cat = _cat(access_areas=[{"area_id": "a_int", "time_range_id": "tr_com"}])
    r = decide(_person(), AP, AREA_INT, AREA_EXT_P, [cat], TR_BY, holidays, WED_10H, site_id="s1")
    assert r["granted"] is False  # comercial não vale em feriado


def test_livre_works_on_holiday():
    holidays = [{"date": "2026-06-10", "enabled": True, "scope": "all", "recurring_annual": False}]
    r = decide(_person(), AP, AREA_INT, AREA_EXT_P, [_cat()], TR_BY, holidays, WED_10H, site_id="s1")
    assert r["granted"] is True


def test_time_range_weekday():
    assert time_range_valid(TR_COM, 3, "10:00", False) is True   # quarta
    assert time_range_valid(TR_COM, 0, "10:00", False) is False  # domingo
    assert time_range_valid(TR_COM, 3, "19:00", False) is False  # fora do horário


def test_is_holiday_recurring():
    hols = [{"date": "2000-09-07", "enabled": True, "scope": "all", "recurring_annual": True}]
    assert is_holiday(datetime(2026, 9, 7).date(), "s1", hols) is True
    assert is_holiday(datetime(2026, 9, 8).date(), "s1", hols) is False

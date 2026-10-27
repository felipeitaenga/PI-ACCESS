"""Cria a estrutura padrão de controle de acesso (idempotente).

No container:  docker exec -it scarvel_<cliente> python -m app.bootstrap ["Nome do local"]

Cria somente o que ainda não existe (compara por nome/código/data):
  - Local (site) .......... usa o nome informado ou CLIENTE_NOME
  - Faixas horárias ....... Livre, Comercial (seg–sex), Sábado manhã
  - Feriados nacionais .... datas fixas (recorrentes) + Sexta-feira Santa do ano atual e do próximo
  - Áreas ................. EXTERIOR, Externa/Interna Pedestre, Veículos, Caminhões, Interna Portaria
  - Categorias ............ ACESSO FULL, PEDESTRE, VEÍCULO, CAMINHÃO, VISITANTE, BLOQUEADO (impeditiva)
  - Departamentos ......... os mais comuns (Administrativo, Financeiro, RH...)
Rodar de novo não duplica nada. Em sistema novo (banco sem áreas e sem categorias) roda sozinho ao iniciar.
"""
import asyncio
import logging
import os
import sys
from datetime import date, timedelta

from database import db
from models import new_id, now_iso

# 0 = domingo ... 6 = sábado (mesmo padrão das faixas horárias do sistema)
FAIXAS = [
    ("Livre", [0, 1, 2, 3, 4, 5, 6], True, [("00:00", "23:59")]),
    ("Comercial (seg–sex 07:00–18:00)", [1, 2, 3, 4, 5], False, [("07:00", "18:00")]),
    ("Sábado manhã (07:00–12:00)", [6], False, [("07:00", "12:00")]),
]

FERIADOS_FIXOS = [
    ("01-01", "Confraternização Universal"),
    ("04-21", "Tiradentes"),
    ("05-01", "Dia do Trabalho"),
    ("09-07", "Independência do Brasil"),
    ("10-12", "Nossa Senhora Aparecida"),
    ("11-02", "Finados"),
    ("11-15", "Proclamação da República"),
    ("11-20", "Dia Nacional de Zumbi e da Consciência Negra"),
    ("12-25", "Natal"),
]

# (descrição, é exterior, anti-dupla entrada, lotação máxima)
AREAS = [
    ("EXTERIOR", True, False, 0),
    ("Área Externa Pedestre", False, False, 0),
    ("Área Interna Pedestre", False, True, 0),
    ("Área Interna Portaria", False, False, 0),
    ("Área Externa Veículos", False, False, 0),
    ("Área Interna Veículos", False, False, 0),
    ("Área Externa Caminhões", False, False, 0),
    ("Área Interna Caminhões", False, False, 0),
]


DEPARTAMENTOS = ["Administrativo", "Financeiro", "Recursos Humanos", "Comercial", "Compras", "TI", "Produção",
                 "Logística", "Manutenção", "Qualidade", "Segurança", "Portaria", "Diretoria", "Jurídico"]


def _doc(extra):
    return {"id": new_id(), "enabled": True, "deleted": False, "created_at": now_iso(), **extra}


def _pascoa(ano):
    a, b, c = ano % 19, ano // 100, ano % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes = (h + l - 7 * m + 114) // 31
    dia = ((h + l - 7 * m + 114) % 31) + 1
    return date(ano, mes, dia)


async def _ativo(col, filtro):
    return await db[col].find_one({**filtro, "deleted": {"$ne": True}}, {"_id": 0})


async def main(args):
    criados = {"local": 0, "faixas": 0, "feriados": 0, "areas": 0, "categorias": 0, "departamentos": 0}
    nome_local = (args[0] if args else os.environ.get("CLIENTE_NOME") or os.environ.get("CLIENTE") or "Sede").strip()

    # ---- Local ----
    site = await _ativo("sites", {"name": nome_local})
    if not site:
        existente = await _ativo("sites", {})
        if existente and not args:
            site = existente
        else:
            site = _doc({"name": nome_local, "address": "", "timezone": "America/Sao_Paulo"})
            await db.sites.insert_one(dict(site))
            criados["local"] += 1
    sid, sname = site["id"], site["name"]

    # ---- Faixas horárias ----
    faixas = {}
    for desc, dias, feriado, intervalos in FAIXAS:
        tr = await _ativo("time_ranges", {"description": desc})
        if not tr:
            tr = _doc({"description": desc, "weekdays": dias, "valid_on_holidays": feriado,
                       "intervals": [{"start": s, "end": e} for s, e in intervalos]})
            await db.time_ranges.insert_one(dict(tr))
            criados["faixas"] += 1
        faixas[desc] = tr
    livre = faixas["Livre"]
    comercial = faixas["Comercial (seg–sex 07:00–18:00)"]

    # ---- Feriados ----
    ano = date.today().year
    for md, desc in FERIADOS_FIXOS:
        d = f"{ano}-{md}"
        if not await _ativo("holidays", {"description": desc}):
            await db.holidays.insert_one(dict(_doc({"date": d, "description": desc,
                                                    "recurring_annual": True, "scope": "all"})))
            criados["feriados"] += 1
    for a in (ano, ano + 1):
        d = (_pascoa(a) - timedelta(days=2)).isoformat()
        if not await _ativo("holidays", {"date": d}):
            await db.holidays.insert_one(dict(_doc({"date": d, "description": f"Sexta-feira Santa {a}",
                                                    "recurring_annual": False, "scope": "all"})))
            criados["feriados"] += 1

    # ---- Áreas ----
    areas = {}
    for desc, ext, anti, maxo in AREAS:
        ar = await _ativo("areas", {"description": desc, "site_id": sid})
        if not ar:
            ar = _doc({"description": desc, "site_id": sid, "site_name": sname, "anti_double_entry": anti,
                       "max_occupancy": maxo, "current_occupancy": 0, "is_exterior": ext})
            await db.areas.insert_one(dict(ar))
            criados["areas"] += 1
        areas[desc] = ar

    def aa(desc, tr, escort=False):
        return {"area_id": areas[desc]["id"], "time_range_id": tr["id"], "require_escort": escort}

    # ---- Categorias ----
    base = {"control_origin": False, "control_anti_double": False, "require_escort_unconditional": False,
            "reentry_timed": False, "reentry_minutes": 0, "impeditive": False,
            "use_contingency": True, "always_verify_offline": False}
    categorias = [
        ("ACESSO FULL", "Acesso completo a todas as áreas, 24h",
         [aa(d, livre) for d, ext, *_ in AREAS if not ext], {}),
        ("PEDESTRE", "Pedestres em horário comercial",
         [aa("Área Interna Pedestre", comercial), aa("Área Interna Portaria", comercial),
          aa("Área Externa Pedestre", livre)], {"control_origin": True}),
        ("VEÍCULO", "Veículos leves em horário comercial",
         [aa("Área Interna Veículos", comercial), aa("Área Externa Veículos", livre)], {"control_origin": True}),
        ("CAMINHÃO", "Caminhões em horário comercial",
         [aa("Área Interna Caminhões", comercial), aa("Área Externa Caminhões", livre)], {"control_origin": True}),
        ("VISITANTE", "Visitantes em horário comercial",
         [aa("Área Interna Pedestre", comercial), aa("Área Interna Portaria", comercial),
          aa("Área Externa Pedestre", livre)], {}),
        ("BLOQUEADO", "Categoria impeditiva: nega qualquer acesso", [], {"impeditive": True}),
    ]
    for code, desc, access_areas, flags in categorias:
        if not await _ativo("categories", {"code": code}):
            await db.categories.insert_one(dict(_doc({"code": code, "description": desc,
                                                      "access_areas": access_areas, **base, **flags})))
            criados["categorias"] += 1

    # ---- Departamentos ----
    for nome in DEPARTAMENTOS:
        if not await _ativo("departments", {"name": nome}):
            await db.departments.insert_one(dict(_doc({"name": nome, "company_id": None})))
            criados["departamentos"] += 1
    return criados, sname


async def auto():
    """Sistema novo: cria a estrutura padrão uma única vez."""
    if await db.settings.find_one({"id": "bootstrap"}):
        return
    if not await db.areas.count_documents({}) and not await db.categories.count_documents({}):
        criados, _ = await main([])
        logging.getLogger("bootstrap").info(f"Estrutura padrão criada: {criados}")
    await db.settings.update_one({"id": "bootstrap"}, {"$set": {"id": "bootstrap", "done": True}}, upsert=True)


async def cli(args):
    criados, sname = await main(args)
    print(f"Estrutura padrão — local: {sname}")
    for k, v in criados.items():
        print(f"  {k:<11} {v} criado(s)")
    if not any(criados.values()):
        print("  Nada novo: a estrutura padrão já existia.")


if __name__ == "__main__":
    asyncio.run(cli(sys.argv[1:]))

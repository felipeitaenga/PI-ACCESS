import random
import logging
from datetime import datetime, timezone, timedelta
from database import db
from models import new_id, now_iso

logger = logging.getLogger(__name__)

FIRST = ["Ana", "Bruno", "Carla", "Daniel", "Eduarda", "Felipe", "Gabriela", "Henrique",
         "Isabela", "João", "Larissa", "Marcos", "Natália", "Otávio", "Patrícia", "Rafael",
         "Sabrina", "Thiago", "Vanessa", "William", "Camila", "Diego", "Fernanda", "Gustavo",
         "Juliana", "Leonardo", "Mariana", "Pedro", "Renata", "Lucas", "Aline", "Bernardo",
         "Clara", "Davi", "Elaine", "Fábio", "Giovana", "Hugo", "Ingrid", "Jorge"]
LAST = ["Silva", "Santos", "Oliveira", "Souza", "Lima", "Pereira", "Costa", "Rodrigues",
        "Almeida", "Nascimento", "Carvalho", "Gomes", "Martins", "Araújo", "Ribeiro", "Barbosa"]
DEPTS = ["TI", "RH", "Operações", "Logística", "Financeiro"]
ROLES = ["Analista", "Coordenador", "Gerente", "Assistente", "Técnico", "Motorista", "Operador"]
SEED_FLAG = "seed_v4"
VISIT_ORIGINS = ["Acme Consultoria", "Delta Engenharia", "Omega Telecom", "Fornecedor Sigma"]


def gen_cpf():
    n = [random.randint(0, 9) for _ in range(9)]
    for i in (9, 10):
        s = sum(n[k] * ((i + 1) - k) for k in range(i))
        n.append((s * 10 % 11) % 10)
    d = "".join(map(str, n))
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}", d


def day(n):
    return (datetime.now(timezone.utc) + timedelta(days=n)).strftime("%Y-%m-%d")


async def already_seeded():
    return await db.settings.find_one({"id": SEED_FLAG}) is not None


def _doc(extra):
    return {"id": new_id(), "enabled": True, "deleted": False, "created_at": now_iso(), **extra}


async def generate_seed():
    if await already_seeded():
        return {"skipped": True}

    for c in ["sites", "areas", "doors", "devices", "controllers", "access_points",
              "time_ranges", "holidays", "categories", "companies", "company_groups",
              "departments", "people", "identifiers", "vehicles", "visitors", "visits",
              "access_events", "alarms", "credentials", "sync_jobs", "person_documents"]:
        await db[c].delete_many({})

    site = _doc({"name": "Sede Corporativa São Paulo", "address": "Av. Paulista, 1000 - São Paulo/SP",
                 "timezone": "America/Sao_Paulo"})
    await db.sites.insert_one(dict(site))
    sid = site["id"]

    # Áreas (7 + EXTERIOR)
    def area(desc, anti=False, maxo=0, ext=False):
        return _doc({"description": desc, "site_id": sid, "site_name": site["name"],
                     "anti_double_entry": anti, "max_occupancy": maxo, "current_occupancy": 0,
                     "is_exterior": ext})
    a_ext = area("EXTERIOR", ext=True)
    a_ped_e = area("Área Externa Pedestre")
    a_ped_i = area("Área Interna Pedestre", anti=True, maxo=300)
    a_port = area("Área Interna Portaria", maxo=40)
    a_vei_e = area("Área Externa Veículos")
    a_vei_i = area("Área Interna Veículos", maxo=80)
    a_cam_e = area("Área Externa Caminhões")
    a_cam_i = area("Área Interna Caminhões", maxo=20)
    areas = [a_ext, a_ped_e, a_ped_i, a_port, a_vei_e, a_vei_i, a_cam_e, a_cam_i]
    for a in areas:
        await db.areas.insert_one(dict(a))

    # Faixas horárias
    tr_livre = _doc({"description": "Livre", "weekdays": [0, 1, 2, 3, 4, 5, 6],
                     "valid_on_holidays": True, "intervals": [{"start": "00:00", "end": "23:59"}]})
    tr_com = _doc({"description": "Comercial (seg–sex 07:00–18:00)", "weekdays": [1, 2, 3, 4, 5],
                   "valid_on_holidays": False, "intervals": [{"start": "07:00", "end": "18:00"}]})
    await db.time_ranges.insert_one(dict(tr_livre))
    await db.time_ranges.insert_one(dict(tr_com))

    # Feriados
    await db.holidays.insert_one(dict(_doc({"date": "2026-09-07", "description": "Independência",
                                            "recurring_annual": True, "scope": "all"})))
    await db.holidays.insert_one(dict(_doc({"date": "2026-12-25", "description": "Natal",
                                            "recurring_annual": True, "scope": "all"})))

    # Categorias
    def cat(code, desc, access_areas, **flags):
        base = {"code": code, "description": desc, "access_areas": access_areas,
                "control_origin": False, "control_anti_double": False,
                "require_escort_unconditional": False, "reentry_timed": False,
                "reentry_minutes": 0, "impeditive": False, "use_contingency": True,
                "always_verify_offline": False}
        base.update(flags)
        return _doc(base)

    def aa(a, tr, escort=False):
        return {"area_id": a["id"], "time_range_id": tr["id"], "require_escort": escort}

    cat_full = cat("ACESSO FULL", "Acesso total, 24h",
                   [aa(a_ped_i, tr_livre), aa(a_port, tr_livre), aa(a_vei_i, tr_livre),
                    aa(a_cam_i, tr_livre)])
    cat_ped = cat("PEDESTRE", "Pedestres (comercial)",
                  [aa(a_ped_i, tr_com), aa(a_port, tr_com)],
                  control_origin=True, control_anti_double=True)
    cat_vei = cat("VEÍCULO", "Veículos leves", [aa(a_vei_i, tr_com)], control_origin=True)
    cat_cam = cat("CAMINHÃO", "Caminhões", [aa(a_cam_i, tr_com)], control_origin=True)
    cat_vis = cat("VISITANTE", "Visitantes com escort",
                  [aa(a_ped_i, tr_com, True), aa(a_port, tr_com)],
                  require_escort_unconditional=False)
    cat_tx = cat("TRANSPORTADORA X – G14", "Transportadora X - grupo G14",
                 [aa(a_cam_i, tr_com), aa(a_cam_e, tr_livre)], control_origin=True)
    cats = [cat_full, cat_ped, cat_vei, cat_cam, cat_vis, cat_tx]
    for c in cats:
        await db.categories.insert_one(dict(c))

    # Controladoras + Pontos de acesso
    def ctrl(name, model, readers, relays):
        return _doc({"name": name, "brand": "simulado", "model": model, "ip": f"192.168.1.{random.randint(10,99)}",
                     "port": 80, "username": "admin", "password_enc": "", "site_id": sid, "site_name": site["name"],
                     "driver": "simulado", "num_readers": readers, "num_relays": relays, "num_inputs": readers,
                     "online": True, "firmware": "SIM-1.4.2", "last_heartbeat": now_iso()})
    c_ped = ctrl("Controladora Pedestre (Catraca)", "NX-SIM Turnstile", 2, 2)
    c_vei = ctrl("Controladora Veículos (Cancela)", "NX-SIM Barrier", 4, 4)
    await db.controllers.insert_one(dict(c_ped))
    await db.controllers.insert_one(dict(c_vei))

    def ap(ctrlr, desc, reader, relay, origin, dest, direction, ptype):
        return _doc({"controller_id": ctrlr["id"], "controller_name": ctrlr["name"], "site_id": sid,
                     "site_name": site["name"], "description": desc, "reader": reader, "relay": relay,
                     "door_sensor": True, "button": True, "origin_area_id": origin["id"],
                     "origin_area_name": origin["description"], "dest_area_id": dest["id"],
                     "dest_area_name": dest["description"], "direction": direction, "type": ptype,
                     "relay_time": 5, "door_open_time": 20, "camera_id": None, "mode": "normal"})
    aps = [
        ap(c_ped, "Catraca Pedestre - Entrada", 1, 1, a_ped_e, a_ped_i, "entrada", "catraca"),
        ap(c_ped, "Catraca Pedestre - Saída", 2, 2, a_ped_i, a_ped_e, "saida", "catraca"),
        ap(c_vei, "Cancela Veículos - Entrada", 1, 1, a_vei_e, a_vei_i, "entrada", "cancela"),
        ap(c_vei, "Cancela Veículos - Saída", 2, 2, a_vei_i, a_vei_e, "saida", "cancela"),
        ap(c_vei, "Cancela Caminhões - Entrada", 3, 3, a_cam_e, a_cam_i, "entrada", "cancela"),
        ap(c_vei, "Cancela Caminhões - Saída", 4, 4, a_cam_i, a_cam_e, "saida", "cancela"),
    ]
    for p in aps:
        await db.access_points.insert_one(dict(p))

    # Empresas / grupos / departamentos
    grp = _doc({"name": "Grupo NX"})
    grp_srv = _doc({"name": "Grupo Serviços Integrados"})
    await db.company_groups.insert_one(dict(grp))
    await db.company_groups.insert_one(dict(grp_srv))

    def comp(name, cnpj, trade, ctype, group, valid, default_cat):
        return _doc({"name": name, "cnpj": cnpj, "trade_name": trade, "type": ctype,
                     "group_id": group["id"] if group else None, "contract_valid_until": valid,
                     "default_category_id": default_cat["id"]})
    comp_own = comp("NX Corp", "12.345.678/0001-90", "NX Corp Ltda", "propria", grp, None, cat_ped)
    comp_alfa = comp("Prestadora Alfa", "11.222.333/0001-44", "Alfa Serviços", "terceirizada", grp_srv, day(400), cat_ped)
    comp_beta = comp("Beta Manutenção", "55.666.777/0001-88", "Beta Manutenção Industrial", "terceirizada", grp_srv, day(200), cat_ped)
    comp_gama = comp("Gama Limpeza", "22.333.444/0001-55", "Gama Facilities", "terceirizada", None, day(5), cat_ped)
    comp_tx = comp("Transportadora X", "98.765.432/0001-10", "Transp. X S.A.", "transportadora", None, day(500), cat_tx)
    comp_rs = comp("Rodo Sul Logística", "33.444.555/0001-66", "Rodo Sul", "transportadora", None, day(300), cat_cam)
    for c in [comp_own, comp_alfa, comp_beta, comp_gama, comp_tx, comp_rs]:
        await db.companies.insert_one(dict(c))
    depts = []
    for dn in DEPTS:
        d = _doc({"name": dn, "company_id": comp_own["id"]})
        depts.append(d)
        await db.departments.insert_one(dict(d))

    # Pessoas
    async def person(name, ptype, company, dept, cat_ids, valid_until=None, current_area=None,
                     matricula="", status="ativo", valid_from=None, docs=(), plate=None):
        idx = random.randint(1, 70)
        cpf, cpf_d = gen_cpf()
        photo = f"https://i.pravatar.cc/200?img={idx}"
        p = _doc({"name": name, "matricula": matricula, "cpf": cpf, "cpf_digits": cpf_d,
                  "rg": str(random.randint(1000000, 9999999)), "document": "", "photo_thumb": photo,
                  "admission_date": day(-random.randint(60, 3000)) if ptype == "funcionario" else None,
                  "function": random.choice(ROLES) if ptype == "terceiro" else "",
                  "contract_manager": "Marcos Lima" if ptype == "terceiro" else "", "notes": "",
                  "birth": f"19{random.randint(70,99)}-{random.randint(1,12):02d}-{random.randint(1,28):02d}",
                  "phone": f"(11) 9{random.randint(1000,9999)}-{random.randint(1000,9999)}",
                  "email": f"{name.split()[0].lower()}@exemplo.com",
                  "photo": photo, "person_type": ptype,
                  "company_id": company["id"], "company_name": company["name"],
                  "company_group_id": company.get("group_id"), "department_id": dept["id"] if dept else None,
                  "department": dept["name"] if dept else "", "role_title": random.choice(ROLES),
                  "manager": "Ana Souza" if ptype == "funcionario" else "", "valid_from": valid_from,
                  "valid_until": valid_until, "category_ids": cat_ids,
                  "current_area_id": (current_area or a_ped_e)["id"], "status": status,
                  "status_reason": "Documento vencido: ASO" if status == "vencido" else "", "consent": True})
        await db.people.insert_one(dict(p))
        if p["current_area_id"] not in (a_ped_e["id"], a_cam_e["id"], a_vei_e["id"]) and status == "ativo":
            await db.areas.update_one({"id": p["current_area_id"]}, {"$inc": {"current_occupancy": 1}})
        for dtype, dval in docs:
            await db.person_documents.insert_one({"id": new_id(), "person_id": p["id"], "type": dtype,
                                                  "valid_until": dval, "file": "", "file_name": "",
                                                  "deleted": False, "created_at": now_iso()})
        if plate:
            await db.vehicles.insert_one(dict(_doc({"person_id": p["id"], "plate": plate,
                                                    "model": random.choice(["Scania R450", "Volvo FH", "VW Constellation"]),
                                                    "color": random.choice(["Branco", "Prata", "Vermelho"])})))
        card = random.randint(1000000, 9999999)
        await db.identifiers.insert_one(dict(_doc({"person_id": p["id"], "type": "facial", "value": "template",
                                                   "active": True, "valid_until": valid_until})))
        await db.identifiers.insert_one(dict(_doc({"person_id": p["id"], "type": "cartao", "value": str(card),
                                                   "hex": format(card, "X"), "format": "Wiegand 26",
                                                   "active": True, "valid_until": valid_until})))
        return p

    def nm():
        return f"{random.choice(FIRST)} {random.choice(LAST)}"

    people = []
    for i in range(30):
        ids = [cat_ped["id"]]
        if i % 7 == 0:
            ids = [cat_full["id"]]
        elif i % 5 == 0:
            ids.append(cat_vei["id"])
        st = "bloqueado" if i == 29 else ("inativo" if i == 28 else "ativo")
        people.append(await person(nm(), "funcionario", comp_own, random.choice(depts), ids,
                                   current_area=a_ped_i if i % 3 == 0 else a_ped_e,
                                   matricula=f"F{1001 + i}", status=st))
    for comp_t in [comp_alfa, comp_beta, comp_gama]:
        for i in range(5):
            expired = comp_t is comp_alfa and i == 0
            docs = [("ASO", day(-3) if expired else day(180)), ("Integração", day(300))]
            if comp_t is comp_beta:
                docs.append(("NR-10", day(4) if i == 1 else day(200)))
            people.append(await person(nm(), "terceiro", comp_t, None, [cat_ped["id"]],
                                       valid_until=day(90), valid_from=day(-30), docs=docs,
                                       current_area=a_ped_i if i == 2 else a_ped_e,
                                       status="vencido" if expired else "ativo"))
    for comp_t, cats_t in [(comp_tx, [cat_tx["id"], cat_cam["id"]]), (comp_rs, [cat_cam["id"]])]:
        for i in range(3):
            plate = f"{random.choice(['ABC', 'RSX', 'TXK', 'FGH'])}{random.randint(1, 9)}{random.choice('ABCDEFGHJ')}{random.randint(10, 99)}"
            people.append(await person(nm(), "terceiro", comp_t, None, cats_t, valid_until=day(60),
                                       valid_from=day(-10), docs=[("CNH", day(365))], current_area=a_cam_e,
                                       plate=plate))

    # Visitantes (10, 4 empresas de origem, 3 presentes agora, 1 em lista negra)
    hosts = [p for p in people if p["person_type"] == "funcionario" and p["status"] == "ativo"]
    now_dt = datetime.now(timezone.utc)
    plan = ["presente"] * 3 + ["agendado"] * 3 + ["finalizado"] * 4
    for i in range(10):
        cpf, cpf_d = gen_cpf()
        rg = f"{random.randint(10, 99)}.{random.randint(100, 999)}.{random.randint(100, 999)}-{random.randint(0, 9)}"
        black = i == 9
        v = _doc({"name": nm(), "document": rg, "document_digits": "".join(c for c in rg if c.isdigit()),
                  "cpf": cpf, "cpf_digits": cpf_d, "phone": f"(11) 9{random.randint(1000,9999)}-{random.randint(1000,9999)}",
                  "email": "", "origin_company": VISIT_ORIGINS[i % 4],
                  "photo": f"https://i.pravatar.cc/200?img={i+40}", "photo_thumb": f"https://i.pravatar.cc/200?img={i+40}",
                  "blacklist": black, "blacklist_reason": "Comportamento inadequado em visita anterior" if black else "",
                  "notes": ""})
        await db.visitors.insert_one(dict(v))
        host = random.choice(hosts)
        st = plan[i]
        if st == "presente":
            start, end = now_dt - timedelta(hours=1), now_dt + timedelta(hours=3)
        elif st == "agendado":
            start, end = now_dt + timedelta(hours=1 + i), now_dt + timedelta(hours=3 + i)
        else:
            start, end = now_dt - timedelta(days=i), now_dt - timedelta(days=i) + timedelta(hours=2)
        await db.visits.insert_one(dict(_doc({
            "visitor_id": v["id"], "visitor_name": v["name"], "visitor_document": rg,
            "origin_company": v["origin_company"], "host_id": host["id"], "host_name": host["name"],
            "reason": random.choice(["Reunião comercial", "Manutenção", "Entrevista", "Entrega técnica"]),
            "expected_start": start.isoformat(), "expected_end": end.isoformat(),
            "category_id": cat_vis["id"], "require_escort": True, "credential_type": "qrcode",
            "credential_value": f"NXV-{random.randint(100000, 999999)}", "vehicle_plate": "", "status": st,
            "checkin_at": start.isoformat() if st in ("presente", "finalizado") else None,
            "checkout_at": end.isoformat() if st == "finalizado" else None})))

    # Eventos dos últimos 7 dias
    active = [p for p in people if p["status"] == "ativo"]
    reasons = ["Fora da faixa horária", "Sem permissão para a área", "Origem inválida",
               "Anti-dupla entrada", "Categoria impeditiva", "Lotação máxima"]
    cred = ["facial", "cartao", "qrcode", "pin"]
    events = []
    now = datetime.now(timezone.utc)
    for dn in range(7):
        base = now - timedelta(days=dn)
        for _ in range(random.randint(120, 180)):
            p = random.choice(active)
            point = random.choice(aps)
            hour = random.choices(range(24), weights=[1,1,1,1,1,2,4,8,9,7,6,7,8,7,6,7,8,9,6,3,2,2,1,1])[0]
            ts = base.replace(hour=hour, minute=random.randint(0, 59), second=random.randint(0, 59))
            granted = random.random() > 0.15
            events.append({"id": new_id(), "timestamp": ts.isoformat(), "site_id": sid, "site_name": site["name"],
                           "area_id": point["dest_area_id"], "area_name": point["dest_area_name"],
                           "origin_area_id": point["origin_area_id"], "origin_area_name": point["origin_area_name"],
                           "door_id": point["id"], "door_name": point["description"],
                           "access_point_id": point["id"], "controller_id": point["controller_id"],
                           "device_id": point["controller_id"], "device_name": point["controller_name"],
                           "person_id": p["id"], "person_name": p["name"], "person_photo": p["photo"],
                           "person_type": p["person_type"], "company_name": p["company_name"],
                           "captured_photo": p["photo"], "credential_type": random.choice(cred),
                           "direction": point["direction"], "access_result": "granted" if granted else "denied",
                           "reason": "" if granted else random.choice(reasons),
                           "match_score": round(random.uniform(92, 99.8), 1) if granted else round(random.uniform(10, 60), 1)})
    if events:
        await db.access_events.insert_many(events)

    # Alarmes
    for _ in range(4):
        point = random.choice(aps)
        await db.alarms.insert_one({"id": new_id(), "timestamp": (now - timedelta(hours=random.randint(1, 48))).isoformat(),
                                    "type": random.choice(["porta_forcada", "porta_aberta", "dispositivo_offline", "tentativas_negadas"]),
                                    "message": "Evento de alarme detectado", "priority": random.choice(["alta", "media", "baixa"]),
                                    "site_id": sid, "site_name": site["name"], "door_id": point["id"],
                                    "door_name": point["description"], "acknowledged": False, "ack_by": None, "comment": ""})

    await db.settings.update_one({"id": "global"}, {"$set": {"id": "global", "retention_days": 90,
                                 "photo_retention_days": 180, "timezone": "America/Sao_Paulo"}}, upsert=True)
    await db.settings.insert_one({"id": SEED_FLAG, "at": now_iso()})
    return {"ok": True, "people": len(people), "events": len(events), "areas": len(areas),
            "controllers": 2, "access_points": len(aps), "categories": len(cats)}

import random
from datetime import datetime, timezone, timedelta
from database import db
from models import new_id, now_iso

FIRST = ["Ana", "Bruno", "Carla", "Daniel", "Eduarda", "Felipe", "Gabriela", "Henrique",
         "Isabela", "João", "Larissa", "Marcos", "Natália", "Otávio", "Patrícia", "Rafael",
         "Sabrina", "Thiago", "Vanessa", "William", "Camila", "Diego", "Fernanda", "Gustavo",
         "Juliana", "Leonardo", "Mariana", "Pedro", "Renata", "Lucas"]
LAST = ["Silva", "Santos", "Oliveira", "Souza", "Lima", "Pereira", "Costa", "Rodrigues",
        "Almeida", "Nascimento", "Carvalho", "Gomes", "Martins", "Araújo", "Ribeiro", "Barbosa"]
DEPARTMENTS = ["TI", "Financeiro", "RH", "Operações", "Comercial", "Logística", "Diretoria"]
COMPANIES = ["NX Corp", "Contratada Alfa", "Contratada Beta"]
ROLES = ["Analista", "Coordenador", "Gerente", "Assistente", "Técnico", "Diretor", "Estagiário"]


async def already_seeded():
    return await db.settings.find_one({"id": "seed_done"}) is not None


async def generate_seed():
    if await already_seeded():
        return {"skipped": True}

    # Site
    site = {"id": new_id(), "name": "Sede Corporativa São Paulo",
            "address": "Av. Paulista, 1000 - São Paulo/SP", "timezone": "America/Sao_Paulo",
            "created_at": now_iso()}
    await db.sites.insert_one(dict(site))

    # Áreas
    area_defs = [
        {"name": "Recepção / Lobby", "max_occupancy": 50, "anti_passback": "none"},
        {"name": "Escritórios", "max_occupancy": 200, "anti_passback": "soft"},
        {"name": "Data Center", "max_occupancy": 10, "anti_passback": "hard"},
    ]
    areas = []
    for a in area_defs:
        area = {"id": new_id(), "site_id": site["id"], "site_name": site["name"],
                "name": a["name"], "max_occupancy": a["max_occupancy"],
                "anti_passback": a["anti_passback"], "created_at": now_iso()}
        areas.append(area)
        await db.areas.insert_one(dict(area))

    # Portas (6)
    door_defs = [
        ("Entrada Principal", 0), ("Catraca Lobby", 0),
        ("Porta Escritório 2º Andar", 1), ("Porta Escritório 3º Andar", 1),
        ("Acesso Data Center", 2), ("Sala de Servidores", 2),
    ]
    doors = []
    for name, ai in door_defs:
        area = areas[ai]
        door = {"id": new_id(), "site_id": site["id"], "site_name": site["name"],
                "area_id": area["id"], "area_name": area["name"], "name": name,
                "description": "", "mode": "normal", "state": "fechada", "created_at": now_iso()}
        doors.append(door)
        await db.doors.insert_one(dict(door))

    # Dispositivos (4 simulados) ligados às portas
    dev_defs = [
        ("Leitora Facial Entrada", "NX-SIM Face", doors[0]),
        ("Catraca Controladora", "NX-SIM Turnstile", doors[1]),
        ("Leitora Cartão 2º Andar", "NX-SIM Card", doors[2]),
        ("Leitora Data Center", "NX-SIM Bio", doors[4]),
    ]
    for name, model, door in dev_defs:
        dev = {"id": new_id(), "site_id": site["id"], "site_name": site["name"],
               "area_id": door["area_id"], "door_id": door["id"], "name": name,
               "brand": "simulado", "model": model, "ip": f"192.168.1.{random.randint(10,99)}",
               "port": 80, "username": "admin", "password_enc": "",
               "connection_mode": "direct", "reader_type": "entrada",
               "online": True, "firmware": "SIM-1.4.2", "last_heartbeat": now_iso(),
               "created_at": now_iso()}
        await db.devices.insert_one(dict(dev))

    # Pessoas (50)
    people = []
    used = set()
    for i in range(50):
        name = f"{random.choice(FIRST)} {random.choice(LAST)}"
        ptype = "colaborador" if random.random() > 0.25 else "terceiro"
        avatar = f"https://i.pravatar.cc/200?img={(i % 70) + 1}"
        matricula = f"{10000 + i}"
        person = {"id": new_id(), "name": name, "matricula": matricula,
                  "document": f"{random.randint(100,999)}.{random.randint(100,999)}.{random.randint(100,999)}-{random.randint(10,99)}",
                  "company": random.choice(COMPANIES) if ptype == "terceiro" else "NX Corp",
                  "department": random.choice(DEPARTMENTS), "role_title": random.choice(ROLES),
                  "photo": avatar, "person_type": ptype,
                  "valid_until": None, "status": random.choices(["ativo", "inativo", "bloqueado"], [0.85, 0.1, 0.05])[0],
                  "consent": True, "created_at": now_iso()}
        people.append(person)
        await db.people.insert_one(dict(person))
        # Credencial facial + cartão
        await db.credentials.insert_one({"id": new_id(), "person_id": person["id"],
                                         "type": "facial", "value": "template", "active": True,
                                         "created_at": now_iso()})
        card_dec = random.randint(1000000, 9999999)
        await db.credentials.insert_one({"id": new_id(), "person_id": person["id"],
                                        "type": "cartao", "value": str(card_dec),
                                        "hex": format(card_dec, "X"), "format": "Wiegand 26",
                                        "active": True, "created_at": now_iso()})

    # Níveis de acesso (2)
    await db.access_levels.insert_one({"id": new_id(), "name": "Colaborador Padrão",
                                       "door_ids": [d["id"] for d in doors[:4]], "time_zone": "Comercial",
                                       "created_at": now_iso()})
    await db.access_levels.insert_one({"id": new_id(), "name": "Acesso Total",
                                       "door_ids": [d["id"] for d in doors], "time_zone": "24h",
                                       "created_at": now_iso()})

    # Zonas de tempo + feriado
    await db.time_zones.insert_one({"id": new_id(), "name": "Comercial",
                                   "ranges": [{"days": [1, 2, 3, 4, 5], "start": "08:00", "end": "18:00"}],
                                   "created_at": now_iso()})
    await db.time_zones.insert_one({"id": new_id(), "name": "24h",
                                   "ranges": [{"days": [0, 1, 2, 3, 4, 5, 6], "start": "00:00", "end": "23:59"}],
                                   "created_at": now_iso()})
    await db.holidays.insert_one({"id": new_id(), "name": "Independência", "date": "2026-09-07",
                                 "created_at": now_iso()})

    # Eventos dos últimos 7 dias
    active_people = [p for p in people if p["status"] == "ativo"]
    reasons = ["Fora do horário permitido", "Credencial não reconhecida", "Acesso expirado",
               "Sem nível de acesso", "Pessoa bloqueada"]
    cred_types = ["facial", "cartao", "pin", "qrcode"]
    events = []
    now = datetime.now(timezone.utc)
    for day in range(7):
        base = now - timedelta(days=day)
        n = random.randint(120, 200)
        for _ in range(n):
            person = random.choice(active_people)
            door = random.choice(doors)
            hour = random.choices(range(24), weights=[1,1,1,1,1,2,4,8,9,7,6,7,8,7,6,7,8,9,6,3,2,2,1,1])[0]
            ts = base.replace(hour=hour, minute=random.randint(0, 59), second=random.randint(0, 59))
            result = "granted" if random.random() > 0.15 else "denied"
            direction = random.choice(["entrada", "saida"])
            events.append({
                "id": new_id(), "timestamp": ts.isoformat(),
                "site_id": site["id"], "site_name": site["name"],
                "area_id": door["area_id"], "area_name": door["area_name"],
                "door_id": door["id"], "door_name": door["name"],
                "device_id": None, "device_name": "",
                "person_id": person["id"], "person_name": person["name"],
                "person_photo": person["photo"], "captured_photo": person["photo"],
                "credential_type": random.choice(cred_types), "direction": direction,
                "access_result": result,
                "reason": "" if result == "granted" else random.choice(reasons),
                "match_score": round(random.uniform(92, 99.8), 1) if result == "granted" else round(random.uniform(10, 60), 1),
            })
    if events:
        await db.access_events.insert_many(events)

    # Alguns alarmes
    for _ in range(4):
        door = random.choice(doors)
        await db.alarms.insert_one({
            "id": new_id(), "timestamp": (now - timedelta(hours=random.randint(1, 48))).isoformat(),
            "type": random.choice(["porta_forcada", "porta_aberta", "dispositivo_offline", "tentativas_negadas"]),
            "message": "Evento de alarme detectado", "priority": random.choice(["alta", "media", "baixa"]),
            "site_id": site["id"], "site_name": site["name"],
            "door_id": door["id"], "door_name": door["name"],
            "acknowledged": False, "ack_by": None, "comment": ""})

    await db.settings.update_one({"id": "global"},
                                 {"$set": {"id": "global", "retention_days": 90, "photo_retention_days": 180,
                                           "timezone": "America/Sao_Paulo"}}, upsert=True)
    await db.settings.insert_one({"id": "seed_done", "at": now_iso()})
    return {"ok": True, "people": len(people), "events": len(events)}

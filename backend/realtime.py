import asyncio
import json
import random
import logging
from datetime import datetime, timezone, timedelta

from database import db, clean
from models import new_id, now_iso

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        self.active: list = []

    async def connect(self, websocket):
        await websocket.accept()
        self.active.append(websocket)

    def disconnect(self, websocket):
        if websocket in self.active:
            self.active.remove(websocket)

    async def broadcast(self, message: dict):
        dead = []
        data = json.dumps(message, default=str)
        for ws in list(self.active):
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()

DENY_REASONS = [
    "Fora do horário permitido",
    "Credencial não reconhecida",
    "Acesso expirado",
    "Sem nível de acesso para a porta",
    "Pessoa bloqueada",
    "Anti-passback",
]
CREDENTIAL_TYPES = ["facial", "cartao", "pin", "qrcode", "placa"]


async def _build_event(person, door, device, result, direction):
    reason = "" if result == "granted" else random.choice(DENY_REASONS)
    match_score = round(random.uniform(92.0, 99.8), 1) if result == "granted" else round(random.uniform(10.0, 60.0), 1)
    captured = person.get("photo", "") if result == "granted" and random.random() > 0.2 else person.get("photo", "")
    return {
        "id": new_id(),
        "timestamp": now_iso(),
        "site_id": door.get("site_id"),
        "site_name": door.get("site_name", ""),
        "area_id": door.get("area_id"),
        "area_name": door.get("area_name", ""),
        "door_id": door.get("id"),
        "door_name": door.get("name"),
        "device_id": device.get("id") if device else None,
        "device_name": device.get("name") if device else "",
        "person_id": person.get("id"),
        "person_name": person.get("name"),
        "person_photo": person.get("photo", ""),
        "captured_photo": captured,
        "credential_type": random.choice(CREDENTIAL_TYPES),
        "direction": direction,
        "access_result": result,
        "reason": reason,
        "match_score": match_score,
    }


async def generate_event(persist=True, broadcast=True):
    """Gera um evento de acesso aleatório a partir dos dados existentes."""
    doors = await db.doors.find({}, {"_id": 0}).to_list(100)
    people = await db.people.find({"status": "ativo"}, {"_id": 0}).to_list(500)
    if not doors or not people:
        return None
    door = random.choice(doors)
    person = random.choice(people)
    device = await db.devices.find_one({"door_id": door.get("id")}, {"_id": 0})
    result = "granted" if random.random() > 0.18 else "denied"
    direction = random.choice(["entrada", "saida"])
    event = await _build_event(person, door, device, result, direction)
    if persist:
        await db.access_events.insert_one(dict(event))
        clean(event)
    if broadcast:
        await manager.broadcast({"type": "access_event", "data": event})
    # Alarme aleatório ocasional (porta forçada)
    if random.random() < 0.03:
        await _raise_alarm(door, "porta_forcada", "Porta forçada detectada", "alta")
    return event


async def _raise_alarm(door, alarm_type, message, priority):
    alarm = {
        "id": new_id(),
        "timestamp": now_iso(),
        "type": alarm_type,
        "message": message,
        "priority": priority,
        "site_id": door.get("site_id"),
        "site_name": door.get("site_name", ""),
        "door_id": door.get("id"),
        "door_name": door.get("name"),
        "acknowledged": False,
        "ack_by": None,
        "comment": "",
    }
    await db.alarms.insert_one(dict(alarm))
    clean(alarm)
    await manager.broadcast({"type": "alarm", "data": alarm})


_sim_task = None


async def simulator_loop():
    logger.info("Simulador de eventos iniciado")
    while True:
        try:
            await asyncio.sleep(random.uniform(4, 9))
            await generate_event()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Erro no simulador: {e}")
            await asyncio.sleep(5)


def start_simulator():
    global _sim_task
    if _sim_task is None or _sim_task.done():
        _sim_task = asyncio.create_task(simulator_loop())
    return _sim_task


def stop_simulator():
    global _sim_task
    if _sim_task and not _sim_task.done():
        _sim_task.cancel()

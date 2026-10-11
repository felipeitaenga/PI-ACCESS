import asyncio
import json
import random
import logging
from datetime import datetime, timezone

from database import db
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


async def generate_event(persist=True, broadcast=True):
    """Gera um evento rodando o motor de decisão real sobre um ponto de acesso aleatório."""
    from access_service import evaluate  # import tardio evita ciclo
    aps = await db.access_points.find({"deleted": {"$ne": True}, "enabled": True}, {"_id": 0}).to_list(200)
    people = await db.people.find({"status": "ativo", "deleted": {"$ne": True}}, {"_id": 0}).to_list(800)
    if not aps or not people:
        return None
    ap = random.choice(aps)
    person = random.choice(people)
    visits = await db.visits.find({"status": "presente", "deleted": {"$ne": True}}, {"_id": 0}).to_list(200)
    if visits and random.random() < 0.3:
        vi = random.choice(visits)
        v = await db.visitors.find_one({"id": vi["visitor_id"]}, {"_id": 0, "photo": 1}) or {}
        person = {"id": vi["visitor_id"], "name": vi["visitor_name"], "photo": v.get("photo", ""),
                  "status": "ativo", "person_type": "visitante", "origin_company": vi.get("origin_company", ""),
                  "category_ids": [vi["category_id"]] if vi.get("category_id") else [],
                  "valid_from": vi.get("expected_start"), "valid_until": vi.get("expected_end"),
                  "current_area_id": vi.get("current_area_id")}
    res = await evaluate(person, ap, persist=persist)
    event = res["event"]
    if broadcast:
        await manager.broadcast({"type": "access_event", "data": event})
    if res["granted"] and random.random() < 0.03:
        await _raise_alarm(ap, "porta_forcada", "Porta forçada detectada", "alta")
    return event


async def _raise_alarm(ap, alarm_type, message, priority):
    alarm = {"id": new_id(), "timestamp": now_iso(), "type": alarm_type, "message": message,
             "priority": priority, "site_id": ap.get("site_id"), "site_name": ap.get("site_name", ""),
             "door_id": ap.get("id"), "door_name": ap.get("description"),
             "acknowledged": False, "ack_by": None, "comment": ""}
    await db.alarms.insert_one(dict(alarm))
    alarm.pop("_id", None)
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

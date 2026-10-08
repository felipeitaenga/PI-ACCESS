import random
from datetime import datetime, timezone
from .base import AccessControlDriver


class SimulatedDriver(AccessControlDriver):
    """Driver SIMULADO: gera eventos fictícios para testes e demonstração
    sem necessidade de equipamento físico."""

    brand = "simulado"

    async def connect(self) -> bool:
        return True

    async def get_status(self) -> dict:
        return {"online": True, "uptime": random.randint(1000, 999999),
                "firmware": "SIM-1.4.2", "ts": datetime.now(timezone.utc).isoformat()}

    async def get_device_info(self) -> dict:
        return {
            "brand": "simulado",
            "model": self.device.get("model") or "NX-SIM-1000",
            "firmware": "SIM-1.4.2",
            "serial": "SIM" + str(self.device.get("id", ""))[:8].upper(),
            "capacity": 10000,
        }

    async def open_door(self, door_id: str, seconds: int = 5) -> dict:
        return {"ok": True, "door_id": door_id, "action": "open", "seconds": seconds}

    async def set_door_mode(self, door_id: str, mode: str) -> dict:
        return {"ok": True, "door_id": door_id, "mode": mode}

    async def sync_person(self, person: dict) -> dict:
        return {"ok": True, "person_id": person.get("id")}

    async def delete_person(self, person_id: str) -> dict:
        return {"ok": True, "person_id": person_id}

    async def sync_face(self, person_id: str, photo: str) -> dict:
        return {"ok": True, "person_id": person_id, "face": bool(photo)}

    async def sync_card(self, person_id: str, card: dict) -> dict:
        return {"ok": True, "person_id": person_id, "card": card.get("number")}

    async def sync_access_rules(self) -> dict:
        return {"ok": True, "rules_synced": True}

    async def get_events(self, since: str = None) -> list:
        return []

    async def set_datetime(self) -> dict:
        return {"ok": True, "datetime": datetime.now(timezone.utc).isoformat()}

    async def reboot(self) -> dict:
        return {"ok": True, "rebooting": True}

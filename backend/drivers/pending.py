from .base import AccessControlDriver

LABELS = {"hikvision": "Facial Hikvision (ISAPI)", "controlid": "Facial Control iD", "ct300": "CT300-2L"}


class PendingDriver(AccessControlDriver):
    """Driver reservado: modelo cadastrável, integração (API/SDK) ainda não implementada."""

    brand = "pending"

    def _err(self):
        b = (self.device.get("brand") or "").lower()
        return {"ok": False, "error": f"Driver {LABELS.get(b, b)} ainda não implementado"}

    async def connect(self) -> bool:
        return False

    async def get_status(self) -> dict:
        return {"online": False, **self._err()}

    async def get_device_info(self) -> dict:
        return {"firmware": "", **self._err()}

    async def open_door(self, door_id: str, seconds: int = 5) -> dict:
        return self._err()

    async def set_door_mode(self, door_id: str, mode: str) -> dict:
        return self._err()

    async def sync_person(self, person: dict) -> dict:
        return self._err()

    async def delete_person(self, person_id: str) -> dict:
        return self._err()

    async def sync_face(self, person_id: str, photo: str) -> dict:
        return self._err()

    async def sync_card(self, person_id: str, card: dict) -> dict:
        return self._err()

    async def sync_access_rules(self) -> dict:
        return self._err()

    async def get_events(self, since: str = None) -> list:
        return []

    async def set_datetime(self) -> dict:
        return self._err()

    async def reboot(self) -> dict:
        return self._err()

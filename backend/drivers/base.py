from abc import ABC, abstractmethod


class AccessControlDriver(ABC):
    """Interface comum (padrão Adapter) para todos os equipamentos de controle de acesso.

    Novos fabricantes implementam esta interface e se registram no factory, sem
    necessidade de alterar o núcleo do sistema.
    """

    brand = "base"

    def __init__(self, device: dict):
        self.device = device

    # --- Conexão / status ---
    @abstractmethod
    async def connect(self) -> bool: ...

    @abstractmethod
    async def get_status(self) -> dict: ...

    @abstractmethod
    async def get_device_info(self) -> dict: ...

    # --- Controle de porta ---
    @abstractmethod
    async def open_door(self, door_id: str, seconds: int = 5) -> dict: ...

    @abstractmethod
    async def set_door_mode(self, door_id: str, mode: str) -> dict: ...

    # --- Sincronização de dados ---
    @abstractmethod
    async def sync_person(self, person: dict) -> dict: ...

    @abstractmethod
    async def delete_person(self, person_id: str) -> dict: ...

    @abstractmethod
    async def sync_face(self, person_id: str, photo: str) -> dict: ...

    @abstractmethod
    async def sync_card(self, person_id: str, card: dict) -> dict: ...

    @abstractmethod
    async def sync_access_rules(self) -> dict: ...

    # --- Eventos ---
    @abstractmethod
    async def get_events(self, since: str = None) -> list: ...

    async def subscribe_events(self, callback):
        """Opcional: push de eventos. Padrão não implementado (usar polling)."""
        return None

    # --- Operações ---
    @abstractmethod
    async def set_datetime(self) -> dict: ...

    @abstractmethod
    async def reboot(self) -> dict: ...

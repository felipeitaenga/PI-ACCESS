from .simulated import SimulatedDriver
from .beward import BewardHttpDriver, BewardMqttDriver
from .pending import PendingDriver
from .intelbras import IntelbrasDriver

# Registro de drivers. Para adicionar uma nova marca, importe a classe e registre
# aqui — nenhuma alteração no núcleo é necessária.
_REGISTRY = {
    "simulado": SimulatedDriver,
    "beward_http": BewardHttpDriver,
    "beward_mqtt": BewardMqttDriver,
    "beward": BewardHttpDriver,
    "hikvision": PendingDriver,
    "controlid": PendingDriver,
    "intelbras": IntelbrasDriver,
    "ct300": PendingDriver,
}


def register_driver(brand: str, cls):
    _REGISTRY[brand] = cls


def available_brands():
    return list(_REGISTRY.keys())


def get_driver(device: dict):
    brand = (device.get("brand") or "simulado").lower()
    cls = _REGISTRY.get(brand, SimulatedDriver)
    return cls(device)

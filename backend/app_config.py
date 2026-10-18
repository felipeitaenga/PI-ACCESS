"""Configuração da instância (um cliente por container), lida só de variáveis de ambiente."""
import os

APP_VERSION = os.environ.get("APP_VERSION") or "dev"
CLIENTE = os.environ["CLIENTE"].strip().lower()
CLIENTE_NOME = os.environ.get("CLIENTE_NOME") or CLIENTE
PUBLIC_URL = (os.environ.get("PUBLIC_URL") or "").rstrip("/")
SEED_DEMO = (os.environ.get("SEED_DEMO") or "false").lower() == "true"
DATA_DIR = os.environ["DATA_DIR"]
STATIC_DIR = os.environ.get("STATIC_DIR") or ""

SMTP_HOST = os.environ.get("SMTP_HOST") or ""
SMTP_PORT = int(os.environ.get("SMTP_PORT") or 587)
SMTP_USER = os.environ.get("SMTP_USER") or ""
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD") or ""
SMTP_FROM = os.environ.get("SMTP_FROM") or SMTP_USER
VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY") or ""
VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY") or ""
VAPID_SUBJECT = os.environ.get("VAPID_SUBJECT") or (f"mailto:{SMTP_FROM}" if SMTP_FROM else PUBLIC_URL)
EMAIL_ENABLED = bool(SMTP_HOST)

FIXED_TOPICS = ("mqtt/face/heartbeat", "mqtt/face/basic")


def _bool(v):
    return (v or "").strip().lower() in ("1", "true", "yes", "sim")


def mqtt_env():
    """Config MQTT vinda do ambiente (None se MQTT_HOST não definido => config pela tela)."""
    host = os.environ.get("MQTT_HOST")
    if not host:
        return None
    prefix = (os.environ.get("MQTT_PREFIX") or f"piaccess/{CLIENTE}").strip().strip("/")
    return {"host": host, "port": int(os.environ.get("MQTT_PORT") or 1883),
            "username": os.environ.get("MQTT_USER") or "", "password": os.environ.get("MQTT_PASSWORD") or "",
            "tls": _bool(os.environ.get("MQTT_TLS")), "client_id": f"piaccess-{CLIENTE}",
            "topic_base": f"{prefix}/face", "enabled": True}

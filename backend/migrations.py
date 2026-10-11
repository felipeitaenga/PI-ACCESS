"""Migrações de esquema versionadas e idempotentes (executadas no startup)."""
import logging
from datetime import datetime, timezone
from database import db

logger = logging.getLogger("migrations")


async def m0001_users_defaults():
    await db.users.update_many({"token_version": {"$exists": False}}, {"$set": {"token_version": 0}})
    await db.users.update_many({"active": {"$exists": False}}, {"$set": {"active": True}})


async def m0002_settings_mqtt_prefix():
    await db.settings.update_many({"id": "mqtt", "topic_prefix": {"$exists": False}}, {"$set": {"topic_prefix": "mqtt/face"}})


MIGRATIONS = [
    ("0001_users_defaults", m0001_users_defaults),
    ("0002_settings_mqtt_prefix", m0002_settings_mqtt_prefix),
]


async def run_migrations():
    done = {d["_id"] async for d in db.schema_migrations.find({}, {"_id": 1})}
    for mid, fn in MIGRATIONS:
        if mid in done:
            continue
        await fn()
        await db.schema_migrations.update_one({"_id": mid}, {"$set": {"applied_at": datetime.now(timezone.utc).isoformat()}}, upsert=True)
        logger.info(f"Migração aplicada: {mid}")

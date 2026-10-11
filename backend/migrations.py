"""Migrações de esquema versionadas e idempotentes (executadas no startup)."""
import logging
from datetime import datetime, timezone
from database import db
from models import new_id

logger = logging.getLogger("migrations")


async def m0001_users_defaults():
    await db.users.update_many({"token_version": {"$exists": False}}, {"$set": {"token_version": 0}})
    await db.users.update_many({"active": {"$exists": False}}, {"$set": {"active": True}})


async def m0002_settings_mqtt_prefix():
    await db.settings.update_many({"id": "mqtt", "topic_prefix": {"$exists": False}}, {"$set": {"topic_prefix": "mqtt/face"}})


async def m0003_visitors_defaults():
    if not await db.settings.find_one({"id": "visitors"}):
        await db.settings.insert_one({"id": "visitors", "validate_cpf": True, "validate_rg": False, "default_hours": 8})
    if not await db.visit_types.find_one({"name": "Visita padrão", "deleted": {"$ne": True}}):
        cat = await db.categories.find_one({"code": "VISITANTE", "deleted": {"$ne": True}}, {"_id": 0, "id": 1})
        if not cat:
            cat = {"id": new_id()}
            await db.categories.insert_one({"id": cat["id"], "code": "VISITANTE", "description": "Visitantes",
                                            "enabled": True, "deleted": False, "time_range_ids": [], "area_ids": [],
                                            "created_at": datetime.now(timezone.utc).isoformat()})
        await db.visit_types.insert_one({"id": new_id(), "name": "Visita padrão", "category_ids": [cat["id"]],
                                         "default_hours": 8, "require_escort": False, "require_photo": False,
                                         "active": True, "deleted": False,
                                         "created_at": datetime.now(timezone.utc).isoformat()})


async def m0004_people_doc_type():
    await db.people.update_many({"can_authorize_visits": {"$exists": False}}, {"$set": {"can_authorize_visits": True}})
    async for p in db.people.find({"doc_type": {"$exists": False}}, {"_id": 1, "cpf": 1, "cpf_digits": 1, "rg": 1}):
        if p.get("cpf_digits"):
            s = {"doc_type": "cpf", "doc_number": p.get("cpf") or p["cpf_digits"], "doc_key": p["cpf_digits"]}
        elif p.get("rg"):
            s = {"doc_type": "rg", "doc_number": p["rg"], "doc_key": p["rg"].replace(".", "").replace("-", "").upper()}
        else:
            s = {"doc_type": "cpf", "doc_number": "", "doc_key": ""}
        await db.people.update_one({"_id": p["_id"]}, {"$set": s})


MIGRATIONS = [
    ("0001_users_defaults", m0001_users_defaults),
    ("0002_settings_mqtt_prefix", m0002_settings_mqtt_prefix),
    ("0003_visitors_defaults", m0003_visitors_defaults),
    ("0004_people_doc_type", m0004_people_doc_type),
]


async def run_migrations():
    done = {d["_id"] async for d in db.schema_migrations.find({}, {"_id": 1})}
    for mid, fn in MIGRATIONS:
        if mid in done:
            continue
        await fn()
        await db.schema_migrations.update_one({"_id": mid}, {"$set": {"applied_at": datetime.now(timezone.utc).isoformat()}}, upsert=True)
        logger.info(f"Migração aplicada: {mid}")

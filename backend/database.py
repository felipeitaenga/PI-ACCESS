import os
from motor.motor_asyncio import AsyncIOMotorClient

mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]


def clean(doc):
    """Remove MongoDB _id so documents are JSON serializable."""
    if not doc:
        return doc
    doc.pop("_id", None)
    return doc


async def create_indexes():
    # Auth
    await db.users.create_index("email", unique=True)
    await db.password_reset_tokens.create_index("expires_at", expireAfterSeconds=0)
    await db.password_reset_tokens.create_index("token_hash", unique=True)
    await db.login_attempts.create_index("email")
    await db.login_attempts.create_index("identifier")
    await db.password_reset_requests.create_index("email")
    await db.password_reset_requests.create_index("created_at", expireAfterSeconds=900)
    # Domain
    await db.access_events.create_index([("timestamp", -1)])
    await db.access_events.create_index("site_id")
    await db.access_events.create_index("door_id")
    await db.access_events.create_index("person_id")
    await db.access_events.create_index("access_result")
    await db.people.create_index("id", unique=True)
    await db.people.create_index("matricula")
    await db.devices.create_index("id", unique=True)
    await db.doors.create_index("id", unique=True)
    await db.areas.create_index("id", unique=True)
    await db.sites.create_index("id", unique=True)
    await db.alarms.create_index([("timestamp", -1)])
    await db.audit_logs.create_index([("timestamp", -1)])
    # Novo modelo de acesso
    for c in ["controllers", "access_points", "time_ranges", "holidays", "categories",
              "companies", "company_groups", "departments", "identifiers", "vehicles",
              "visitors", "visits"]:
        await db[c].create_index("id")
        await db[c].create_index("deleted")
    await db.identifiers.create_index("person_id")
    await db.people.create_index("category_ids")
    await db.access_events.create_index("access_point_id")
    await db.beward_dedup.create_index("at", expireAfterSeconds=86400)
    # Autocadastro
    await db.rate_hits.create_index("at", expireAfterSeconds=86400)
    await db.rate_hits.create_index("key")
    await db.selfreg_otps.create_index("expires_at", expireAfterSeconds=0)
    await db.selfreg_otps.create_index("id")
    await db.selfreg_verifications.create_index("expires_at", expireAfterSeconds=0)
    await db.selfreg_verifications.create_index("token_hash")
    for f in ("id", "status", "host_company_id", "status_token_hash", "decision_token_hash"):
        await db.self_registrations.create_index(f)
    await db.selfreg_invites.create_index("id")
    await db.selfreg_invites.create_index("token_hash")
    await db.companies.create_index("selfreg_code")
    await db.visitors.create_index("email")
    await db.notifications.create_index([("at", -1)])

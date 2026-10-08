from datetime import datetime, timezone
from database import db
from models import new_id


async def log_audit(user, action, entity_type="", entity_id="", details="", ip=""):
    await db.audit_logs.insert_one({
        "id": new_id(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user_id": str(user.get("_id") or user.get("id")) if user else None,
        "user_name": user.get("name", "") if user else "sistema",
        "user_email": user.get("email", "") if user else "",
        "action": action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "details": details,
        "ip": ip,
    })


def client_ip(request):
    return request.client.host if request and request.client else "unknown"

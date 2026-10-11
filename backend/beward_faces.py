import os
import jwt
from datetime import datetime, timezone, timedelta

ALGO = "HS256"


def make_face_token(person_id: str, minutes: int = 5) -> str:
    payload = {"pid": person_id, "exp": datetime.now(timezone.utc) + timedelta(minutes=minutes), "t": "face"}
    return jwt.encode(payload, os.environ["JWT_SECRET"], algorithm=ALGO)


def decode_face_token(token: str):
    try:
        p = jwt.decode(token, os.environ["JWT_SECRET"], algorithms=[ALGO])
        return p.get("pid") if p.get("t") == "face" else None
    except Exception:
        return None

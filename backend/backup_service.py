"""Backup/restauração do banco do cliente em arquivo .json.gz (JSON estendido, uma linha por documento)."""
import asyncio
import gzip
import json
import logging
import os
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from bson import json_util
from bson.json_util import CANONICAL_JSON_OPTIONS

import app_config as cfg
from database import db

logger = logging.getLogger("backup")
BACKUP_DIR = os.path.join(cfg.DATA_DIR, "backups")
NAME_RE = re.compile(r"^piaccess_[a-z0-9_-]+_\d{8}_\d{6}_[a-z]+\.json\.gz$")
DEFAULTS = {"id": "backup", "enabled": True, "time": "03:00", "keep": 7}
TZ = ZoneInfo(os.environ.get("TZ") or "America/Sao_Paulo")
lock = asyncio.Lock()


def path_of(name):
    if not NAME_RE.match(name or ""):
        raise ValueError("Nome de backup inválido")
    return os.path.join(BACKUP_DIR, name)


def new_name(origin):
    ts = datetime.now(TZ).strftime("%Y%m%d_%H%M%S")
    return f"piaccess_{cfg.CLIENTE}_{ts}_{origin}.json.gz"


async def get_settings():
    s = await db.settings.find_one({"id": "backup"}, {"_id": 0}) or {}
    return {**DEFAULTS, **s}


def list_backups():
    os.makedirs(BACKUP_DIR, exist_ok=True)
    out = []
    for n in sorted(os.listdir(BACKUP_DIR), reverse=True):
        if not NAME_RE.match(n):
            continue
        p = os.path.join(BACKUP_DIR, n)
        meta = {}
        if os.path.exists(p + ".meta"):
            with open(p + ".meta") as f:
                meta = json.load(f)
        out.append({"name": n, "size": os.path.getsize(p), "origin": n.rsplit("_", 1)[1].split(".")[0],
                    "created_at": meta.get("created_at") or datetime.fromtimestamp(os.path.getmtime(p), timezone.utc).isoformat(),
                    "collections": meta.get("collections"), "documents": meta.get("documents"), "by": meta.get("by"),
                    "version": meta.get("version")})
    return out


async def create_backup(origin="manual", by="sistema"):
    os.makedirs(BACKUP_DIR, exist_ok=True)
    name = new_name(origin)
    p = path_of(name)
    total, colls = 0, 0
    async with lock:
        with gzip.open(p + ".part", "wt", encoding="utf-8") as f:
            f.write(json.dumps({"pi_access_backup": 1, "version": cfg.APP_VERSION, "cliente": cfg.CLIENTE,
                                "created_at": datetime.now(timezone.utc).isoformat()}) + "\n")
            for c in sorted(await db.list_collection_names()):
                if c.startswith("system."):
                    continue
                colls += 1
                f.write(json.dumps({"collection": c}) + "\n")
                async for doc in db[c].find({}):
                    f.write(json_util.dumps({"c": c, "d": doc}, json_options=CANONICAL_JSON_OPTIONS) + "\n")
                    total += 1
        os.replace(p + ".part", p)
    meta = {"created_at": datetime.now(timezone.utc).isoformat(), "collections": colls, "documents": total,
            "by": by, "version": cfg.APP_VERSION}
    with open(p + ".meta", "w") as f:
        json.dump(meta, f)
    return {"name": name, **meta, "size": os.path.getsize(p)}


def delete_backup(name):
    p = path_of(name)
    for x in (p, p + ".meta"):
        if os.path.exists(x):
            os.remove(x)


async def prune(keep):
    autos = [b for b in list_backups() if b["origin"] == "auto"]
    for b in autos[int(keep):]:
        delete_backup(b["name"])


def validate_file(p):
    with gzip.open(p, "rt", encoding="utf-8") as f:
        head = json.loads(f.readline() or "{}")
    if head.get("pi_access_backup") != 1:
        raise ValueError("Arquivo não é um backup do PI-ACCESS")
    return head


async def restore_backup(name):
    """Substitui as coleções presentes no arquivo pelos dados do backup."""
    p = path_of(name)
    validate_file(p)
    counts = {}
    async with lock:
        batch, current = [], None
        with gzip.open(p, "rt", encoding="utf-8") as f:
            f.readline()
            for line in f:
                row = json_util.loads(line)
                if "collection" in row:
                    if batch:
                        await db[current].insert_many(batch, ordered=False)
                    batch, current = [], row["collection"]
                    await db[current].delete_many({})
                    counts[current] = 0
                    continue
                batch.append(row["d"])
                counts[row["c"]] += 1
                if len(batch) >= 500:
                    await db[current].insert_many(batch, ordered=False)
                    batch = []
            if batch:
                await db[current].insert_many(batch, ordered=False)
    return counts


async def backup_loop():
    """Backup automático diário no horário configurado; mantém as últimas N cópias."""
    last_day = None
    while True:
        try:
            s = await get_settings()
            now = datetime.now(TZ)
            if s.get("enabled") and now.strftime("%H:%M") >= s.get("time", "03:00") and last_day != now.date():
                if not any(b["origin"] == "auto" and b["name"].split("_")[-3] == now.strftime("%Y%m%d") for b in list_backups()):
                    await create_backup("auto", "agendado")
                    await prune(s.get("keep", 7))
                    logger.info("Backup automático gerado")
                last_day = now.date()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"backup_loop: {e}")
        await asyncio.sleep(60)

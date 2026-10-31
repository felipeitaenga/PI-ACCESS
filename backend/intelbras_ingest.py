"""Modo Online Intelbras (Bio-T): o facial envia cada acesso ao SCARVEL, que decide e devolve
{"message": <texto na tela>, "code": "200", "auth": "true"|"false"}.

- Keepalive: GET periódico no caminho configurado; 200 = facial fica "Online".
- Sem resposta/timeout: o facial fica "Offline" e LIBERA TODOS os cadastrados 24h (comportamento
  do equipamento) — por isso o SCARVEL alarma quando o keepalive para.
- Eventos guardados durante o offline chegam depois: são registrados como retroativos (sem decidir).
"""
import asyncio
import base64
import json
import logging
import re
from datetime import datetime, timezone

from database import db
from models import new_id, now_iso
from realtime import manager
from scope import stamp_event
from access_service import evaluate
from beward_ingest import access_point_of, raise_alarm
from drivers.intelbras import subject_for_uid

logger = logging.getLogger("intelbras_ingest")
OFFLINE_AFTER = 45     # s sem keepalive => offline (keepalive configurado em 10 s)
RETRO_AFTER = 90       # evento com UTC mais antigo que isso = guardado no offline
TIME_SYNC_EVERY = 6 * 3600  # acerta o relógio do facial a cada 6 h (sem bateria ele volta para 01/01/2000)
MSG_MAX = 48
OFFLINE_MSG = ("Facial Intelbras sem comunicação com o SCARVEL. No Modo Online, sem servidor o facial "
               "libera TODOS os cadastrados — verifique a rede/VPN.")


def _reply(auth: bool, message: str):
    return {"message": (message or "")[:MSG_MAX], "code": "200", "auth": "true" if auth else "false"}


# ---------- parser multipart ----------
def _boundary(content_type: str):
    m = re.search(r'boundary="?([^";]+)"?', content_type or "", re.I)
    return m.group(1) if m else "myboundary"


def _parse_text(txt: str):
    txt = txt.strip()
    i = txt.find("{")
    if i >= 0:
        try:
            return json.loads(txt[i:txt.rfind("}") + 1])
        except ValueError:
            pass
    return None


def parse_notification(body: bytes, content_type: str = ""):
    """Retorna (dados_json | None, jpeg_bytes | None)."""
    data, jpeg = None, None
    if b"--" not in body[:200] and body.strip()[:1] == b"{":
        return _parse_text(body.decode("utf-8", "replace")), None
    sep = b"--" + _boundary(content_type).encode()
    for part in body.split(sep):
        if b"\r\n\r\n" in part:
            head, payload = part.split(b"\r\n\r\n", 1)
        elif b"\n\n" in part:
            head, payload = part.split(b"\n\n", 1)
        else:
            continue
        payload = payload.rstrip(b"\r\n-")
        h = head.decode("latin-1").lower()
        if "image/jpeg" in h or payload[:3] == b"\xff\xd8\xff":
            jpeg = jpeg or payload
        elif data is None:
            data = _parse_text(payload.decode("utf-8", "replace"))
    if data is None:
        data = _parse_text(body.decode("utf-8", "replace"))
    return data, jpeg


BUTTON_METHOD = "5"  # testado no aparelho: botão de saída (BOT+GND) → Method 5, Status 1, sem UserID
FACE_METHOD = "15"
ECHO_S = 6  # SS 3532 MF W (testado): cada leitura chega 2x no Modo Online (Status 0 e depois Status 1)


async def _echo(ctrl, d):
    """Segunda notificação da mesma leitura (mesmo UserID em poucos segundos): devolve a mesma decisão
    sem criar outro evento/passagem pendente."""
    uid = d.get("UserID") or d.get("CardNo")
    if not uid:
        return None
    last = await db.intelbras_last.find_one({"_id": f"{ctrl['id']}:{uid}"})
    if last and (datetime.now(timezone.utc) - last["at"].replace(tzinfo=timezone.utc)).total_seconds() < ECHO_S:
        return _reply(last["auth"], last.get("message", ""))
    return None


async def _remember(ctrl, d, reply):
    uid = d.get("UserID") or d.get("CardNo")
    if uid:
        await db.intelbras_last.update_one({"_id": f"{ctrl['id']}:{uid}"},
                                           {"$set": {"at": datetime.now(timezone.utc), "auth": reply["auth"] == "true",
                                                     "message": reply["message"]}}, upsert=True)
    return reply


def is_exit_button(d: dict):
    return not d.get("UserID") and not d.get("CardNo") and str(d.get("Method", "")) == BUTTON_METHOD


async def _exit_button(ctrl, d, pic):
    """Abertura pelo botão de saída: registra (sem pessoa) e libera o próximo giro sem alarme."""
    ap = await access_point_of(ctrl)
    if ap:
        await db.access_points.update_one({"id": ap["id"]}, {"$set": {"last_remote_open": now_iso()}})
    ev = await _base_event(ctrl, ap, d, None, pic, True, "Abertura pelo botão de saída", False)
    ev.update({"person_name": "Botão de saída", "credential_type": "botao", "stranger": False})
    await db.access_events.insert_one(dict(await stamp_event(ev)))
    ev.pop("_id", None)
    await manager.broadcast({"type": "access_event", "data": ev})
    return _reply(False, "")  # o facial já abriu; auth=true acionaria o relé de novo


def credential_of(d: dict):
    if d.get("CardNo"):
        return "cartao"
    m = str(d.get("Method", ""))
    return {"1": "cartao", "4": "senha", "6": "digital", "15": "facial"}.get(m, "facial")


def _utc_age(d: dict):
    try:
        return datetime.now(timezone.utc).timestamp() - float(d.get("UTC"))
    except (TypeError, ValueError):
        return 0.0


async def _person(subject_id):
    if not subject_id:
        return None
    p = await db.people.find_one({"id": subject_id, "deleted": {"$ne": True}}, {"_id": 0})
    if p:
        return p
    from visits_core import visitor_person
    return await visitor_person(subject_id)


async def sync_time(ctrl):
    """Acerta data/hora do facial (a validade dos visitantes é conferida pelo relógio dele)."""
    from drivers.factory import get_driver
    try:
        r = await asyncio.wait_for(get_driver(ctrl).set_datetime(), 15)
    except Exception as e:  # noqa: BLE001
        r = {"ok": False, "detail": str(e)[:120] or "timeout"}
    upd = {"time_sync_tried_at": now_iso(), "time_sync_ok": bool(r.get("ok")), "time_sync_detail": r.get("detail", "")}
    if r.get("ok"):
        upd["time_synced_at"] = now_iso()
    await db.controllers.update_one({"id": ctrl["id"]}, {"$set": upd})
    return {"ok": bool(r.get("ok")), "detail": r.get("detail", "")}


def _age(iso):
    try:
        return (datetime.now(timezone.utc) - datetime.fromisoformat(iso)).total_seconds()
    except (TypeError, ValueError):
        return 1e12


async def heartbeat(ctrl, ip=None):
    upd = {"online": True, "last_heartbeat": now_iso(), "online_mode": True}
    if not ctrl.get("online"):
        upd["online_since"] = now_iso()
    if not ctrl.get("online") or _age(ctrl.get("time_synced_at")) > TIME_SYNC_EVERY:
        if _age(ctrl.get("time_sync_tried_at")) > 300:  # não insiste mais que a cada 5 min
            asyncio.create_task(sync_time({**ctrl, **upd}))
    if ip:
        upd["device_ip"] = ip
    await db.controllers.update_one({"id": ctrl["id"]}, {"$set": upd})


async def _base_event(ctrl, ap, d, person, pic, granted, reason, retro):
    return {"id": new_id(), "timestamp": now_iso(), "site_id": ctrl.get("site_id"), "site_name": ctrl.get("site_name", ""),
            "area_id": (ap or {}).get("dest_area_id"), "area_name": (ap or {}).get("dest_area_name", ""),
            "door_id": (ap or {}).get("id"), "door_name": (ap or {}).get("description") or ctrl.get("name"),
            "access_point_id": (ap or {}).get("id"), "controller_id": ctrl["id"], "device_id": ctrl["id"],
            "person_id": (person or {}).get("id"), "person_name": (person or {}).get("name") or d.get("CardName") or "Desconhecido",
            "person_type": (person or {}).get("person_type", ""), "company_name": (person or {}).get("company_name", ""),
            "person_photo": (person or {}).get("photo_thumb") or (person or {}).get("photo", ""), "captured_photo": pic,
            "credential_type": credential_of(d), "direction": (ap or {}).get("direction", "entrada"),
            "access_result": "granted" if granted else "denied", "reason": reason + (" (retroativo)" if retro else ""),
            "match_score": 0, "via": "intelbras", "stranger": not person}


async def handle_access(ctrl, d: dict, jpeg: bytes = None):
    pic = f"data:image/jpeg;base64,{base64.b64encode(jpeg).decode()}" if jpeg else ""
    key = f"intelbras:{ctrl['id']}:{d.get('UTC')}:{d.get('UserID')}:{d.get('CardNo')}"
    if await db.beward_dedup.find_one({"_id": key}):
        return _reply(False, "")
    await db.beward_dedup.insert_one({"_id": key, "at": datetime.now(timezone.utc)})
    await db.controllers.update_one({"id": ctrl["id"]}, {"$set": {"last_event_at": now_iso()}})
    if is_exit_button(d):
        # SS 3532 MF W (fw 20250403, testado): botão de saída (BOT) chega como AccessControl Method 5, sem pessoa
        return await _exit_button(ctrl, d, pic)
    if _utc_age(d) <= RETRO_AFTER:
        echo = await _echo(ctrl, d)
        if echo:
            return echo
    return await _remember(ctrl, d, await _decide(ctrl, d, pic))


async def _decide(ctrl, d, pic):
    ap = await access_point_of(ctrl)
    person = await _person(await subject_for_uid(d.get("UserID")))
    retro = _utc_age(d) > RETRO_AFTER
    if retro or not person or not ap:
        if retro:
            granted, reason = str(d.get("Status")) == "1", "Decidido pelo facial (sem servidor)"
        elif not person and not d.get("UserID") and str(d.get("Method", "")) == FACE_METHOD:
            granted, reason = False, "Rosto não reconhecido (não cadastrado no facial)"
        elif not person:
            granted, reason = False, "Não cadastrado no SCARVEL"
        else:
            granted, reason = False, "Ponto de acesso do facial não configurado"
        ev = await _base_event(ctrl, ap, d, person, pic, granted, reason, retro)
        await db.access_events.insert_one(dict(await stamp_event(ev)))
        ev.pop("_id", None)
        await manager.broadcast({"type": "access_event", "data": ev})
        return _reply(False, "Acesso negado: " + reason if not retro else "")
    res = await evaluate(person, ap, persist=True)
    ev = res["event"]
    extra = {"captured_photo": pic, "controller_id": ctrl["id"], "via": "intelbras",
             "credential_type": credential_of(d), "match_score": 0}
    await db.access_events.update_one({"id": ev["id"]}, {"$set": extra})
    ev.update(extra)
    await manager.broadcast({"type": "access_event", "data": ev})
    first = (person.get("name") or "").split(" ")[0]
    if res["granted"]:
        return _reply(True, f"Bem-vindo(a), {first}!")
    return _reply(False, f"Acesso negado: {res.get('reason') or ''}")


async def handle_notification(ctrl, body: bytes, content_type: str):
    await heartbeat(ctrl)
    data, jpeg = parse_notification(body, content_type)
    events = (data or {}).get("Events") or []
    if not events:
        logger.info(f"intelbras {ctrl.get('name')}: notificação sem Events ({body[:200]!r})")
        return _reply(False, "")
    reply = _reply(False, "")
    for e in events:
        code, d = e.get("Code"), e.get("Data") or {}
        if code == "AccessControl":
            reply = await handle_access(ctrl, d, jpeg)
        elif code == "DoorStatus" and str(d.get("Status", "")).lower() in ("open", "1", "true"):
            import passage
            await passage.on_sensor(ctrl)  # giro da catraca / porta aberta
        elif code == "BreakIn":
            ap = await access_point_of(ctrl)
            await raise_alarm(ctrl, "porta_forcada", f"Porta forçada — {ctrl.get('name')}", "alta", ap)
    return reply


# ---------- offline ----------
async def watch_once():
    now = datetime.now(timezone.utc)
    for c in await db.controllers.find({"deleted": {"$ne": True}, "brand": "intelbras", "online_mode": True},
                                       {"_id": 0}).to_list(500):
        hb = c.get("last_heartbeat")
        if not hb:
            continue
        stale = (now - datetime.fromisoformat(hb)).total_seconds() > OFFLINE_AFTER
        if stale and c.get("online"):
            await db.controllers.update_one({"id": c["id"]}, {"$set": {"online": False}})
            await raise_alarm(c, "facial_offline", OFFLINE_MSG, "alta", await access_point_of(c))


async def watch_loop():
    while True:
        try:
            await watch_once()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"intelbras watch: {e}")
        await asyncio.sleep(15)

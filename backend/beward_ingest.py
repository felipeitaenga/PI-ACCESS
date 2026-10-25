"""Processamento comum dos eventos Beward (MQTT direto ou HTTP via agente local)."""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from database import db
from scope import stamp_event
from models import new_id, now_iso
from realtime import manager
from access_service import evaluate
from drivers.beward_common import map_verify, dedup_key
from mqtt_bus import bus, ONLINE_WINDOW

logger = logging.getLogger("beward_ingest")
TZ = ZoneInfo("America/Sao_Paulo")
DEFAULT_HOURS = {"days": [1, 2, 3, 4, 5], "start": "07:00", "end": "19:00"}
TIME_SYNC_HOURS = 24          # acerta o relógio do facial uma vez por dia
TIME_SYNC_MIN_GAP = 600      # e ao voltar online, no máx. a cada 10 min
STRANGER_GAP = 15            # s entre eventos de "rosto desconhecido" do mesmo facial
NO_EVENT_MSG = "Facial online sem eventos de acesso: verifique 'Evento de Identificação = enviar com imagem' no painel do equipamento."


def norm_direction(v):
    s = str(v if v is not None else "").strip().lower()
    if s in ("1", "in", "entr", "entry", "entrada", "enter"):
        return "entrada"
    if s in ("2", "out", "exit", "saida", "saída", "sair"):
        return "saida"
    return None


async def controller_by_device(dev):
    return await db.controllers.find_one({"deleted": {"$ne": True}, "beward_device_id": {"$in": [str(dev), dev]}}, {"_id": 0})


async def access_point_of(ctrl):
    return await db.access_points.find_one({"controller_id": ctrl["id"], "deleted": {"$ne": True}}, {"_id": 0}, sort=[("reader", 1)])


async def raise_alarm(ctrl, atype, message, priority="baixa", ap=None):
    alarm = {"id": new_id(), "timestamp": now_iso(), "type": atype, "message": message, "priority": priority,
             "site_id": ctrl.get("site_id"), "site_name": ctrl.get("site_name", ""),
             "door_id": (ap or {}).get("id") or ctrl["id"], "door_name": (ap or {}).get("description") or ctrl.get("name"),
             "controller_id": ctrl["id"], "acknowledged": False, "ack_by": None, "comment": ""}
    await db.alarms.insert_one(dict(alarm))
    await manager.broadcast({"type": "alarm", "data": alarm})


def _age_s(iso):
    try:
        return (datetime.now(timezone.utc) - datetime.fromisoformat(iso)).total_seconds()
    except (TypeError, ValueError):
        return 1e12


async def sync_time(ctrl, force=False):
    """Acerta data/hora do facial (validade de visitantes depende do relógio do equipamento)."""
    if not force and _age_s(ctrl.get("time_synced_at")) < TIME_SYNC_MIN_GAP:
        return {"ok": True, "skipped": True}
    from drivers.factory import get_driver
    await db.controllers.update_one({"id": ctrl["id"]}, {"$set": {"time_synced_at": now_iso()}})
    try:
        r = await asyncio.wait_for(get_driver(ctrl).set_datetime(), 20)
    except Exception as e:  # noqa: BLE001
        r = {"ok": False, "detail": str(e)[:120] or "timeout"}
    await db.controllers.update_one({"id": ctrl["id"]}, {"$set": {"time_sync_ok": bool(r.get("ok")),
                                                                 "time_sync_detail": str(r.get("detail") or "")[:200]}})
    if not r.get("ok"):
        logger.warning(f"SetSysTime {ctrl.get('name')}: {r}")
    return r


async def heartbeat(dev, online=True, ip=None):
    ctrl = await controller_by_device(dev)
    if not ctrl:
        return None
    was_online = ctrl.get("online") and ctrl.get("last_heartbeat") and \
        (datetime.now(timezone.utc) - datetime.fromisoformat(ctrl["last_heartbeat"])).total_seconds() < ONLINE_WINDOW
    upd = {"online": online}
    if online:
        upd["last_heartbeat"] = now_iso()
        if not was_online:
            upd["online_since"] = now_iso()
    if ip:
        upd["device_ip"] = ip
    await db.controllers.update_one({"id": ctrl["id"]}, {"$set": upd})
    if online and not was_online and ctrl.get("brand") == "beward_mqtt":
        asyncio.create_task(bus.flush_queue(dev))
        asyncio.create_task(sync_time(ctrl))
    return ctrl


async def stranger(ctrl, info):
    """Rosto não reconhecido (StrSnapPush) vira evento negado, com a foto capturada."""
    if _age_s(ctrl.get("last_stranger_at")) < STRANGER_GAP:
        return None
    key = dedup_key(ctrl.get("beward_device_id"), f"snap-{info.get('SnapID') or info.get('time')}", "stranger")
    if await db.beward_dedup.find_one({"_id": key}):
        return None
    await db.beward_dedup.insert_one({"_id": key, "at": datetime.now(timezone.utc)})
    await db.controllers.update_one({"id": ctrl["id"]}, {"$set": {"last_stranger_at": now_iso(), "last_event_at": now_iso(),
                                                                 "no_event_alerted": False}})
    ap = await access_point_of(ctrl)
    pic = info.get("pic") or ""
    if pic and not pic.startswith("data:") and not pic.startswith("http"):
        pic = f"data:image/jpeg;base64,{pic}"
    dev_dir = norm_direction(info.get("direction"))
    ev = {"id": new_id(), "timestamp": now_iso(), "site_id": ctrl.get("site_id"), "site_name": ctrl.get("site_name", ""),
          "area_id": (ap or {}).get("dest_area_id"), "area_name": (ap or {}).get("dest_area_name", ""),
          "door_id": (ap or {}).get("id"), "door_name": (ap or {}).get("description") or ctrl.get("name"),
          "controller_id": ctrl["id"], "device_id": ctrl["id"], "person_id": None, "person_name": "Desconhecido",
          "person_type": "", "company_name": "", "person_photo": "", "captured_photo": pic, "credential_type": "facial",
          "direction": dev_dir or (ap or {}).get("direction", "entrada"), "access_result": "denied",
          "reason": "Rosto não reconhecido (não cadastrado no facial ou foto incompatível)",
          "match_score": 0, "via": "mqtt", "stranger": True, "company_id": None}
    await db.access_events.insert_one(dict(ev))
    await manager.broadcast({"type": "access_event", "data": ev})
    return ev


async def _check_direction(ctrl, ap, dev_dir):
    if not (ap and dev_dir and ap.get("direction")):
        return False
    if dev_dir == ap["direction"]:
        if ctrl.get("direction_mismatch"):
            await db.controllers.update_one({"id": ctrl["id"]}, {"$set": {"direction_mismatch": None}})
        return False
    if not ctrl.get("direction_mismatch"):
        await raise_alarm(ctrl, "sentido_divergente",
                          f"Sentido divergente: o facial '{ctrl['name']}' está como {dev_dir.upper()} mas o ponto "
                          f"'{ap['description']}' está cadastrado como {ap['direction'].upper()}. Ajuste 'Entrada ou Saída' no facial ou o ponto.",
                          "baixa", ap)
    await db.controllers.update_one({"id": ctrl["id"]}, {"$set": {"direction_mismatch": {
        "device": dev_dir, "point": ap["direction"], "at": now_iso()}}})
    return True


async def record(ctrl, r, via):
    """r: person_ref, name, verify_status, verify_type, sendintime, direction, record_id, time, pic, similarity.
    Retorna {granted, decided_online, show} — decided_online indica decisão do motor."""
    key = dedup_key(ctrl.get("beward_device_id"), r.get("record_id") or r.get("time"), r.get("person_ref"))
    if await db.beward_dedup.find_one({"_id": key}):
        return {"duplicate": True, "decided_online": False}
    await db.beward_dedup.insert_one({"_id": key, "at": datetime.now(timezone.utc)})
    ap = await access_point_of(ctrl)
    m = map_verify(r.get("verify_status"), r.get("verify_type"), r.get("sendintime", 1))
    dev_dir = norm_direction(r.get("direction"))
    mismatch = await _check_direction(ctrl, ap, dev_dir)
    person = await db.people.find_one({"id": str(r.get("person_ref") or "")}, {"_id": 0}) if r.get("person_ref") else None
    if not person and r.get("person_ref"):
        from visits_core import visitor_person
        person = await visitor_person(str(r["person_ref"]))
    pic = r.get("pic") or ""
    if pic and not pic.startswith("data:") and not pic.startswith("http"):
        pic = f"data:image/jpeg;base64,{pic}"
    await db.controllers.update_one({"id": ctrl["id"]}, {"$set": {"last_event_at": now_iso(), "no_event_alerted": False}})
    wants_online = ctrl.get("decision_mode", "servidor") == "servidor" and not m["retroactive"] and person and ap
    if via == "mqtt":
        wants_online = wants_online and int(r.get("verify_status") or 0) == 22
    if wants_online:
        res = await evaluate(person, ap, persist=True)
        ev = res["event"]
        extra = {"captured_photo": pic, "controller_id": ctrl["id"], "direction_mismatch": mismatch,
                 "match_score": r.get("similarity", 0), "via": via}
        await db.access_events.update_one({"id": ev["id"]}, {"$set": extra})
        ev.update(extra)
        await manager.broadcast({"type": "access_event", "data": ev})
        show = (f"{person.get('name')}, acesso liberado" if res["granted"] else f"Acesso negado: {res['reason']}")[:64]
        return {"decided_online": True, "granted": res["granted"], "show": show}
    ev = {"id": new_id(), "timestamp": now_iso(), "site_id": ctrl.get("site_id"), "site_name": ctrl.get("site_name", ""),
          "area_id": (ap or {}).get("dest_area_id"), "area_name": (ap or {}).get("dest_area_name", ""),
          "door_id": (ap or {}).get("id"), "door_name": (ap or {}).get("description") or ctrl.get("name"),
          "controller_id": ctrl["id"], "device_id": ctrl["id"], "person_id": (person or {}).get("id") or r.get("person_ref"),
          "person_name": (person or {}).get("name") or r.get("name") or "Desconhecido",
          "person_type": (person or {}).get("person_type", ""), "company_name": (person or {}).get("company_name", ""),
          "person_photo": (person or {}).get("photo_thumb") or (person or {}).get("photo", ""), "captured_photo": pic,
          "credential_type": m["verify_type"], "direction": dev_dir or (ap or {}).get("direction", "entrada"),
          "access_result": m["access_result"], "reason": m["reason"] + (" (retroativo)" if m["retroactive"] else ""),
          "match_score": r.get("similarity", 0), "direction_mismatch": mismatch, "via": via}
    await db.access_events.insert_one(dict(await stamp_event(ev)))
    await manager.broadcast({"type": "access_event", "data": ev})
    return {"decided_online": False, "granted": m["access_result"] == "granted"}


def _rec_from_mqtt(info):
    return {"person_ref": info.get("customId") or info.get("personId") or info.get("PersonUUID"),
            "name": info.get("persionName") or info.get("personName") or info.get("name"),
            "verify_status": info.get("VerifyStatus"), "verify_type": info.get("VerfyType") or info.get("otype") or 1,
            "sendintime": info.get("Sendintime", 1), "direction": info.get("direction"),
            "record_id": info.get("RecordID"), "time": info.get("time"), "pic": info.get("pic"),
            "similarity": info.get("similarity1", 0)}


async def on_mqtt(topic, op, data, dev):
    info = data.get("info") or {}
    if op in ("HeartBeat", "Online") or topic.endswith("/heartbeat"):
        await heartbeat(dev, True, info.get("ip"))
        if op == "Online" and dev and await controller_by_device(dev):
            # protocolo Beward: o facial reenvia "Online" até receber Online-Ack
            bus.publish_raw(dev, {"operator": "Online-Ack", "info": {"facesluiceId": str(dev), "result": "ok"}})
        return
    if op == "Offline":
        await heartbeat(dev, False, info.get("ip"))
        return
    if op in ("RecPush", "StrSnapPush"):
        rid = info.get("RecordID") if op == "RecPush" else info.get("SnapID")
        bus.publish_raw(dev, {"operator": "PushAck", "messageId": f"ack-{rid}",
                              "info": {"facesluiceId": str(dev), "PushAckType": "2" if op == "RecPush" else "1",
                                       "SnapOrRecordID": str(rid or "")}})
        ctrl = await heartbeat(dev, True)
        if not ctrl:
            return
        if op == "StrSnapPush":
            await stranger(ctrl, info)
            return
        res = await record(ctrl, _rec_from_mqtt(info), "mqtt")
        if res.get("decided_online"):
            bus.publish_raw(dev, {"operator": "Unlock", "messageId": f"unl-{rid}",
                                  "info": {"facesluiceId": str(dev), "openDoor": "1" if res["granted"] else "0",
                                           "showInfo": res["show"]}})


def business_minutes(since, until, hours):
    h = hours or DEFAULT_HOURS
    sh, sm = map(int, h.get("start", "07:00").split(":"))
    eh, em = map(int, h.get("end", "19:00").split(":"))
    days = set(h.get("days", [1, 2, 3, 4, 5]))
    a, b = since.astimezone(TZ), until.astimezone(TZ)
    total, d = 0.0, a.date()
    while d <= b.date():
        if d.isoweekday() in days:
            ws = datetime(d.year, d.month, d.day, sh, sm, tzinfo=TZ)
            we = datetime(d.year, d.month, d.day, eh, em, tzinfo=TZ)
            s, e = max(ws, a), min(we, b)
            if e > s:
                total += (e - s).total_seconds() / 60
        d += timedelta(days=1)
    return total


def in_business_hours(now, hours):
    return business_minutes(now - timedelta(minutes=1), now, hours) > 0


async def watch_once():
    now = datetime.now(timezone.utc)
    sites = {s["id"]: s for s in await db.sites.find({}, {"_id": 0}).to_list(200)}
    for c in await db.controllers.find({"deleted": {"$ne": True}, "model_type": "beward_facial"}, {"_id": 0}).to_list(500):
        hb = c.get("last_heartbeat")
        online = bool(hb) and (now - datetime.fromisoformat(hb)).total_seconds() < ONLINE_WINDOW
        if c.get("online") != online and hb:
            await db.controllers.update_one({"id": c["id"]}, {"$set": {"online": online}})
        if online and c.get("brand") == "beward_mqtt" and _age_s(c.get("time_synced_at")) > TIME_SYNC_HOURS * 3600:
            await sync_time(c)
        if online and c.get("brand") == "beward_mqtt" and c.get("device_id") and \
                await db.mqtt_commands.count_documents({"device_id": str(c["device_id"]), "status": "queued"}, limit=1):
            asyncio.create_task(bus.flush_queue(c["device_id"]))
        hours = (sites.get(c.get("site_id")) or {}).get("business_hours") or DEFAULT_HOURS
        if not online or c.get("no_event_alerted") or not in_business_hours(now, hours):
            continue
        ref = max([x for x in (c.get("last_event_at"), c.get("online_since")) if x] or [hb])
        mins = business_minutes(datetime.fromisoformat(ref), now, hours)
        if mins >= int(c.get("no_event_alert_minutes") or 120):
            await raise_alarm(c, "sem_eventos", NO_EVENT_MSG, "baixa")
            await db.controllers.update_one({"id": c["id"]}, {"$set": {"no_event_alerted": True}})


async def watch_loop():
    while True:
        try:
            await watch_once()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"watch_loop: {e}")
        await asyncio.sleep(300)


bus.handler = on_mqtt

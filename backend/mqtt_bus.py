"""Cliente MQTT do servidor (saída) — assina <prefixo>/#, publica comandos e aguarda Ack."""
import asyncio
import json
import logging
import time
from collections import deque
from database import db
from models import new_id, now_iso
from security import decrypt_secret
from app_config import mqtt_env, FIXED_TOPICS

logger = logging.getLogger("mqtt_bus")
DEFAULT_PREFIX = "mqtt/face"
ACK_TIMEOUT = 10
# Comandos com foto/lote: o facial extrai o rosto antes de responder (pode passar de 10 s)
ACK_TIMEOUT_BY_OP = {"EditPerson": 40, "EditPersonsNew": 90, "DeletePersons": 20, "DeleteAllPerson": 60}
ONLINE_WINDOW = 180  # s sem heartbeat => offline


class MqttBus:
    def __init__(self):
        self.client = None
        self.loop = None
        self.connected = False
        self.cfg = {}
        self.pending = {}
        self.log = deque(maxlen=80)
        self.stats = {"messages": 0, "last_message_at": None, "last_error": "", "connected_at": None}
        self.handler = None  # async (topic, operator, data) -> None
        self.managed = False
        self.flushing = set()

    @property
    def prefix(self):
        if self.managed:
            return self.cfg["topic_base"]
        return normalize_prefix(self.cfg.get("topic_prefix"))

    def topics(self):
        base = self.prefix
        return [f"{base}/#"] + [t for t in FIXED_TOPICS if not t.startswith(base + "/")]

    async def load_cfg(self):
        env = mqtt_env()
        self.managed = env is not None
        if env:
            return env
        s = await db.settings.find_one({"id": "mqtt"}, {"_id": 0}) or {}
        s["password"] = decrypt_secret(s.get("password_enc", ""))
        return s

    async def start(self):
        self.loop = asyncio.get_running_loop()
        await self.stop()
        self.cfg = await self.load_cfg()
        if not self.cfg.get("enabled") or not self.cfg.get("host"):
            logger.info("MQTT desabilitado")
            return
        import paho.mqtt.client as mqtt
        cid = self.cfg.get("client_id") or "pi-access-server"
        try:
            cli = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=cid, clean_session=False)
        except AttributeError:
            cli = mqtt.Client(client_id=cid, clean_session=False)
        if self.cfg.get("username"):
            cli.username_pw_set(self.cfg["username"], self.cfg.get("password") or None)
        if self.cfg.get("tls"):
            cli.tls_set()
        cli.reconnect_delay_set(min_delay=2, max_delay=60)
        cli.on_connect = self._on_connect
        cli.on_disconnect = self._on_disconnect
        cli.on_message = self._on_message
        self.client = cli
        try:
            cli.connect_async(self.cfg["host"], int(self.cfg.get("port") or 1883), keepalive=30)
            cli.loop_start()
            logger.info(f"MQTT conectando em {self.cfg['host']}:{self.cfg.get('port')}")
        except Exception as e:  # noqa: BLE001
            self.stats["last_error"] = str(e)

    async def stop(self):
        if self.client:
            try:
                self.client.loop_stop()
                self.client.disconnect()
            except Exception:  # noqa: BLE001
                pass
        self.client = None
        self.connected = False

    def _on_connect(self, cli, userdata, flags, rc, props=None):
        ok = (getattr(rc, "value", rc) == 0)
        self.connected = ok
        if ok:
            self.stats["connected_at"] = now_iso()
            self.stats["last_error"] = ""
            for t in self.topics():
                cli.subscribe(t, qos=1)
            logger.info(f"MQTT conectado como {self.cfg.get('client_id')}; assinado {', '.join(self.topics())}")
            if self.loop:
                asyncio.run_coroutine_threadsafe(self.flush_online(), self.loop)
        else:
            self.stats["last_error"] = f"CONNACK {rc}"

    def _on_disconnect(self, cli, userdata, *args):
        self.connected = False

    def _on_message(self, cli, userdata, msg):
        try:
            data = json.loads(msg.payload.decode("utf-8", errors="ignore") or "{}")
        except Exception:  # noqa: BLE001
            data = {}
        op = data.get("operator", "")
        info = data.get("info") or {}
        dev = str(info.get("facesluiceId") or info.get("DeviceID") or _device_from_topic(msg.topic, self.prefix) or "")
        if self.loop:
            asyncio.run_coroutine_threadsafe(self._dispatch(msg.topic, op, data, dev), self.loop)

    async def _dispatch(self, topic, op, data, dev):
        if not topic.startswith(self.prefix + "/"):
            # tópicos fixos compartilhados: só dispositivos cadastrados neste cliente
            from beward_ingest import controller_by_device
            if not dev or not await controller_by_device(dev):
                return
        self.stats["messages"] += 1
        self.stats["last_message_at"] = now_iso()
        self.log.appendleft({"at": now_iso(), "topic": topic, "operator": op, "device_id": dev,
                             "summary": _summary(op, data.get("info") or {}, data)})
        if topic.endswith("/Ack") or op.endswith("-Ack"):
            fut = self.pending.pop(str(data.get("messageId")), None)
            if fut and not fut.done():
                fut.set_result(data)
            await db.mqtt_commands.update_one({"messageId": str(data.get("messageId"))},
                                              {"$set": {"status": "ack", "ack": _strip(data), "ack_at": now_iso()}})
            return
        if self.handler:
            try:
                await self.handler(topic, op, data, dev)
            except Exception as e:  # noqa: BLE001
                logger.exception(f"handler MQTT: {e}")

    def publish_raw(self, device_id, payload: dict):
        if not (self.client and self.connected):
            return False
        self.client.publish(f"{self.prefix}/{device_id}", json.dumps(payload), qos=1)
        return True

    async def command(self, device_id, operator, info=None, online=True, queue=True):
        """Publica comando com messageId; espera Ack (10 s). Offline => fila (se queue)."""
        if not queue and not (self.connected and online):
            return {"ok": False, "detail": "broker MQTT desconectado" if not self.connected else "facial offline"}
        mid = f"nx-{int(time.time() * 1000)}-{new_id()[:6]}"
        msg = {"operator": operator, "messageId": mid, "info": {"facesluiceId": str(device_id), **(info or {})}}
        rec = {"id": new_id(), "messageId": mid, "device_id": str(device_id), "operator": operator,
               "payload": msg, "created_at": now_iso(), "status": "queued"}
        if not (self.connected and online):
            await db.mqtt_commands.insert_one(rec)
            why = "broker MQTT desconectado" if not self.connected else "facial offline"
            return {"ok": False, "queued": True, "message_id": mid, "detail": f"{why} — comando na fila"}
        rec["status"] = "sent"
        rec["sent_at"] = now_iso()
        await db.mqtt_commands.insert_one(rec)
        fut = self.loop.create_future()
        self.pending[mid] = fut
        self.publish_raw(device_id, msg)
        try:
            ack = await asyncio.wait_for(fut, ACK_TIMEOUT_BY_OP.get(operator, ACK_TIMEOUT))
        except asyncio.TimeoutError:
            self.pending.pop(mid, None)
            t = ACK_TIMEOUT_BY_OP.get(operator, ACK_TIMEOUT)
            await db.mqtt_commands.update_one({"messageId": mid}, {"$set": {"status": "queued" if queue else "sem_ack",
                                                                         "detail": "sem Ack"}})
            if not queue:
                return {"ok": False, "detail": f"sem Ack do facial em {t} s"}
            return {"ok": False, "queued": True, "message_id": mid, "detail": f"sem Ack do facial em {t} s — comando na fila"}
        ok, code, detail, ainfo = _ack_result(ack)
        return {"ok": ok, "code": code, "detail": detail, "info": _strip(ainfo)}

    async def flush_queue(self, device_id):
        """Reenvia, na ordem, os comandos parados na fila quando o facial (ou o broker) volta.
        Espera o Ack de cada um e atualiza o histórico de sincronizações; sem Ack, para e tenta de novo depois."""
        dev = str(device_id)
        if dev in self.flushing:
            return {"sent": 0, "pending": None}
        self.flushing.add(dev)
        sent = 0
        try:
            q = await db.mqtt_commands.find({"device_id": dev, "status": "queued"}, {"_id": 0}).sort("created_at", 1).to_list(500)
            for c in q:
                mid = str(c["messageId"])
                if c.get("operator") == "SetSysTime":  # hora antiga: nunca reenviar
                    await db.mqtt_commands.update_one({"id": c["id"]}, {"$set": {"status": "descartado", "detail": "hora desatualizada"}})
                    continue
                fut = self.loop.create_future()
                self.pending[mid] = fut
                if not self.publish_raw(dev, c["payload"]):
                    self.pending.pop(mid, None)
                    break
                await db.mqtt_commands.update_one({"id": c["id"]}, {"$set": {"status": "sent", "sent_at": now_iso()}})
                t = ACK_TIMEOUT_BY_OP.get(c.get("operator"), ACK_TIMEOUT)
                try:
                    ack = await asyncio.wait_for(fut, t)
                except asyncio.TimeoutError:
                    self.pending.pop(mid, None)
                    await db.mqtt_commands.update_one({"id": c["id"]}, {"$set": {"status": "queued", "detail": "sem Ack no reenvio"}})
                    break
                ok, _code, detail, _ = _ack_result(ack)
                await db.mqtt_commands.update_one({"id": c["id"]}, {"$set": {"status": "ack" if ok else "erro", "detail": detail}})
                await mark_job(c, ok, detail)
                sent += 1
        finally:
            self.flushing.discard(dev)
        if sent:
            logger.info(f"Fila do facial {dev}: {sent} comando(s) reenviado(s)")
            from beward_ingest import controller_by_device, sync_time
            ctrl = await controller_by_device(dev)
            if ctrl:
                await sync_time(ctrl, force=True)
        return {"sent": sent, "pending": await db.mqtt_commands.count_documents({"device_id": dev, "status": "queued"})}

    async def flush_online(self):
        """Após reconectar ao broker: esvazia a fila dos faciais que estão online."""
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        for c in await db.controllers.find({"deleted": {"$ne": True}, "brand": "beward_mqtt"}, {"_id": 0}).to_list(500):
            hb, dev = c.get("last_heartbeat"), str(c.get("device_id") or "")
            if dev and hb and (now - datetime.fromisoformat(hb)).total_seconds() < ONLINE_WINDOW:
                asyncio.create_task(self.flush_queue(dev))

    def status(self):
        return {"connected": self.connected, "host": self.cfg.get("host"), "port": self.cfg.get("port"),
                "enabled": bool(self.cfg.get("enabled")), "topic_prefix": self.prefix, "topics": self.topics(),
                "managed": self.managed, "client_id": self.cfg.get("client_id"), "tls": bool(self.cfg.get("tls")),
                **self.stats}


def normalize_prefix(p):
    return (p or "").strip().strip("/").replace("#", "").replace("+", "") or DEFAULT_PREFIX


def _ack_result(ack):
    code = str(ack.get("code", "200"))
    ainfo = ack.get("info") or {}
    ok = code == "200" and str(ainfo.get("result", "ok")).lower() in ("ok", "success", "")
    detail = ainfo.get("detail") or ainfo.get("Detail") or ""
    if "get pic" in detail.lower():
        detail = f"Facial não conseguiu obter a foto ({detail})"
    return ok, code, detail, ainfo


def _job_status(job):
    devs = job.get("devices") or []
    success = sum(1 for d in devs if d.get("status") == "ok")
    return {"success": success, "status": "concluido" if devs and success == len(devs) else "erro",
            "errors": [d for d in devs if d.get("status") == "erro"]}


async def mark_job(cmd, ok, detail):
    """Atualiza a linha do histórico (sync_jobs) que ficou "comando na fila" com o resultado do reenvio."""
    from beward_ingest import controller_by_device
    mid = str(cmd["messageId"])
    full = await db.sync_jobs.find_one({"errors.message_id": mid}, {"_id": 0})
    if full:  # sincronização completa: a pessoa sai da lista de erros quando o facial confirma
        errs = [e for e in full["errors"] if e.get("message_id") != mid]
        if not ok:
            errs.append({**next(e for e in full["errors"] if e.get("message_id") == mid), "error": detail or "falha no reenvio", "message_id": None})
        upd = {"errors": errs, "status": "erro" if errs else "concluido", "success": full.get("success", 0) + (1 if ok else 0)}
        await db.sync_jobs.update_one({"id": full["id"]}, {"$set": upd})
        return
    job = await db.sync_jobs.find_one({"devices.message_id": mid}, {"_id": 0})
    if not job:
        # registros antigos (sem message_id): mesma pessoa, mesmo facial, criado junto com o comando
        ctrl = await controller_by_device(cmd["device_id"])
        ids = (cmd.get("payload") or {}).get("info", {}).get("customId")
        pid = (ids[0] if isinstance(ids, list) and len(ids) == 1 else ids) if ids else None
        if not ctrl or not isinstance(pid, str):
            return
        from datetime import datetime, timedelta
        t = datetime.fromisoformat(cmd["created_at"])
        job = await db.sync_jobs.find_one({"person_id": pid, "started_at": {"$gte": (t - timedelta(seconds=60)).isoformat(), "$lte": (t + timedelta(seconds=60)).isoformat()},
                                           "devices": {"$elemMatch": {"controller_id": ctrl["id"], "error": {"$regex": "na fila"}}}}, {"_id": 0})
        if not job:
            return
    for d in job.get("devices") or []:
        if d.get("message_id") == mid or (not d.get("message_id") and "na fila" in (d.get("error") or "")):
            d.update({"status": "ok" if ok else "erro", "error": "" if ok else (detail or "falha no reenvio"), "resent_at": now_iso()})
            break
    await db.sync_jobs.update_one({"id": job["id"]}, {"$set": {"devices": job["devices"], **_job_status(job)}})


def _device_from_topic(topic, prefix):
    if not topic.startswith(prefix + "/"):
        return ""
    seg = topic[len(prefix) + 1:].split("/")[0]
    return seg if seg not in ("heartbeat", "basic", "Ack") else ""


def _strip(d):
    return {k: (v if not (isinstance(v, str) and len(v) > 300) else f"<{len(v)} bytes>") for k, v in (d or {}).items()}


def _summary(op, info, data):
    if op == "RecPush":
        return f"{info.get('persionName') or info.get('personName') or '—'} · status {info.get('VerifyStatus')}"
    if op in ("HeartBeat", "Online", "Offline"):
        return f"{op} {info.get('ip', '')}".strip()
    return str(data.get("code", ""))[:40]


async def probe(host, port, username="", password="", seconds=5, tls=False):
    """Teste isolado de conexão ao broker."""
    import paho.mqtt.client as mqtt
    res = {"ok": False, "detail": ""}
    loop = asyncio.get_running_loop()
    done = loop.create_future()

    def on_connect(c, u, f, rc, p=None):
        v = getattr(rc, "value", rc)
        if not done.done():
            loop.call_soon_threadsafe(done.set_result, v)
    try:
        cli = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"pi-access-probe-{new_id()[:6]}")
    except AttributeError:
        cli = mqtt.Client(client_id=f"pi-access-probe-{new_id()[:6]}")
    if username:
        cli.username_pw_set(username, password or None)
    if tls:
        cli.tls_set()
    cli.on_connect = on_connect
    t0 = time.time()
    try:
        await loop.run_in_executor(None, lambda: cli.connect(host, int(port), keepalive=10))
        cli.loop_start()
        rc = await asyncio.wait_for(done, seconds)
        res = {"ok": rc == 0, "detail": "Conectado" if rc == 0 else f"Recusado (CONNACK {rc})",
               "latency_ms": int((time.time() - t0) * 1000)}
    except Exception as e:  # noqa: BLE001
        res = {"ok": False, "detail": f"Falha: {e}"}
    finally:
        try:
            cli.loop_stop()
            cli.disconnect()
        except Exception:  # noqa: BLE001
            pass
    return res


bus = MqttBus()

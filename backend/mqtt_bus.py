"""Cliente MQTT do servidor (saída) — assina <prefixo>/#, publica comandos e aguarda Ack."""
import asyncio
import json
import logging
import time
from collections import deque
from database import db
from models import new_id, now_iso
from security import decrypt_secret

logger = logging.getLogger("mqtt_bus")
DEFAULT_PREFIX = "mqtt/face"
ACK_TIMEOUT = 10
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

    @property
    def prefix(self):
        return normalize_prefix(self.cfg.get("topic_prefix"))

    async def load_cfg(self):
        s = await db.settings.find_one({"id": "mqtt"}, {"_id": 0}) or {}
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
            cli.username_pw_set(self.cfg["username"], decrypt_secret(self.cfg.get("password_enc", "")) or None)
        cli.reconnect_delay_set(min_delay=2, max_delay=30)
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
            cli.subscribe(f"{self.prefix}/#", qos=1)
            logger.info(f"MQTT conectado; assinado {self.prefix}/#")
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
        self.stats["messages"] += 1
        self.stats["last_message_at"] = now_iso()
        self.log.appendleft({"at": now_iso(), "topic": msg.topic, "operator": op, "device_id": dev,
                             "summary": _summary(op, info, data)})
        if self.loop:
            asyncio.run_coroutine_threadsafe(self._dispatch(msg.topic, op, data, dev), self.loop)

    async def _dispatch(self, topic, op, data, dev):
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

    async def command(self, device_id, operator, info=None, online=True):
        """Publica comando com messageId; espera Ack (10 s). Offline => fila."""
        mid = f"nx-{int(time.time() * 1000)}-{new_id()[:6]}"
        msg = {"operator": operator, "messageId": mid, "info": {"facesluiceId": str(device_id), **(info or {})}}
        rec = {"id": new_id(), "messageId": mid, "device_id": str(device_id), "operator": operator,
               "payload": msg, "created_at": now_iso(), "status": "queued"}
        if not (self.connected and online):
            await db.mqtt_commands.insert_one(rec)
            why = "broker MQTT desconectado" if not self.connected else "facial offline"
            return {"ok": False, "queued": True, "detail": f"{why} — comando na fila"}
        rec["status"] = "sent"
        rec["sent_at"] = now_iso()
        await db.mqtt_commands.insert_one(rec)
        fut = self.loop.create_future()
        self.pending[mid] = fut
        self.publish_raw(device_id, msg)
        try:
            ack = await asyncio.wait_for(fut, ACK_TIMEOUT)
        except asyncio.TimeoutError:
            self.pending.pop(mid, None)
            await db.mqtt_commands.update_one({"messageId": mid}, {"$set": {"status": "queued", "detail": "sem Ack"}})
            return {"ok": False, "queued": True, "detail": "sem Ack do facial em 10 s — comando na fila"}
        code = str(ack.get("code", "200"))
        ainfo = ack.get("info") or {}
        ok = code == "200" and str(ainfo.get("result", "ok")).lower() in ("ok", "success", "")
        detail = ainfo.get("detail") or ainfo.get("Detail") or ""
        if "get pic" in detail.lower():
            detail = f"Facial não conseguiu obter a foto ({detail})"
        return {"ok": ok, "code": code, "detail": detail, "info": _strip(ainfo)}

    async def flush_queue(self, device_id):
        """Reenvia comandos pendentes quando o facial volta online."""
        q = await db.mqtt_commands.find({"device_id": str(device_id), "status": "queued"}, {"_id": 0}).sort("created_at", 1).to_list(200)
        for c in q:
            if not self.publish_raw(device_id, c["payload"]):
                return
            await db.mqtt_commands.update_one({"id": c["id"]}, {"$set": {"status": "sent", "sent_at": now_iso()}})
            await asyncio.sleep(0.3)

    def status(self):
        return {"connected": self.connected, "host": self.cfg.get("host"), "port": self.cfg.get("port"),
                "enabled": bool(self.cfg.get("enabled")), "topic_prefix": self.prefix, **self.stats}


def normalize_prefix(p):
    return (p or "").strip().strip("/").replace("#", "").replace("+", "") or DEFAULT_PREFIX


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


async def probe(host, port, username="", password="", seconds=5):
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

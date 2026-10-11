#!/usr/bin/env python3
"""pi-access-agent — ponte local entre faciais Beward (HTTP, rede local) e o servidor PI-ACCESS (HTTPS).

- Escuta HTTP simples na porta 5011 os caminhos padrão do facial (/Subscribe/Verify, /Subscribe/heartbeat, ...).
- Identifica o equipamento pelo DeviceID do JSON, responde {"code":200,"desc":"OK"} em até 10 s
  (com openDoor/showInfo quando o servidor decide) e repassa ao servidor central.
- Fila SQLite: se a internet cair, guarda os eventos e reenvia depois.
- Executa os comandos do servidor no facial: POST http://<ip>/action/<Operator> com Basic Auth.
Somente biblioteca padrão do Python 3.8+.  Uso:  python3 pi_access_agent.py agent.json
"""
import base64
import json
import logging
import sqlite3
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [agent] %(message)s")
log = logging.getLogger()
CFG = json.load(open(sys.argv[1] if len(sys.argv) > 1 else "agent.json", encoding="utf-8"))
SERVER = CFG["server"].rstrip("/") + "/api"
TOKEN = CFG["token"]
PORT = int(CFG.get("port", 5011))
PATHS = {"/subscribe/verify": "verify", "/subscribe/heartbeat": "heartbeat", "/subscribe/snap": "snap",
         "/subscribe/qrcode": "qrcode", "/subscribe/idcard": "idcard", "/subscribe/card": "card",
         "/subscribe/alarm": "alarm"}
OK = {"code": 200, "desc": "OK"}
DB = sqlite3.connect(CFG.get("queue_db", "nx_agent_queue.db"), check_same_thread=False)
DB.execute("CREATE TABLE IF NOT EXISTS q (id INTEGER PRIMARY KEY, kind TEXT, device TEXT, payload TEXT, at REAL)")
LOCK = threading.Lock()
DEVICES = {}


def server_call(method, path, body=None, timeout=10):
    req = urllib.request.Request(SERVER + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read() or b"{}")


def device_call(dev, operator, info=None, timeout=10):
    body = json.dumps({"operator": operator, "info": info or {}}).encode()
    auth = base64.b64encode(f"{dev.get('username', 'admin')}:{dev.get('password', '')}".encode()).decode()
    req = urllib.request.Request(f"http://{dev['ip']}:{dev.get('port', 80)}/action/{operator}", data=body, method="POST",
                                 headers={"Content-Type": "application/json", "Authorization": f"Basic {auth}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return {"http_status": r.status, "body": json.loads(r.read() or b"{}")}
    except urllib.error.HTTPError as e:
        return {"http_status": e.code, "error": str(e)}
    except Exception as e:  # noqa: BLE001
        return {"http_status": 0, "error": str(e)}


def enqueue(kind, device, payload):
    with LOCK:
        DB.execute("INSERT INTO q (kind, device, payload, at) VALUES (?,?,?,?)", (kind, device, json.dumps(payload), time.time()))
        DB.commit()


def flush_loop():
    while True:
        with LOCK:
            rows = DB.execute("SELECT id, kind, device, payload FROM q ORDER BY id LIMIT 50").fetchall()
        for rid, kind, device, payload in rows:
            try:
                server_call("POST", f"/agent/events/{kind}", {"device_id": device, "payload": json.loads(payload), "queued": True})
                with LOCK:
                    DB.execute("DELETE FROM q WHERE id=?", (rid,))
                    DB.commit()
            except Exception as e:  # noqa: BLE001
                log.warning(f"fila: servidor indisponível ({e}); {len(rows)} pendente(s)")
                break
        time.sleep(5)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _reply(self, obj):
        data = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        kind = PATHS.get(self.path.split("?")[0].lower())
        raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        try:
            payload = json.loads(raw or b"{}")
        except ValueError:
            payload = {}
        info = payload.get("info") if isinstance(payload.get("info"), dict) else payload
        device = str(info.get("DeviceID") or info.get("facesluiceId") or "")
        if not kind:
            return self._reply(OK)
        log.info(f"{kind} de {device or '?'} ({self.client_address[0]})")
        if kind in ("verify",):
            try:
                return self._reply(server_call("POST", f"/agent/events/{kind}", {"device_id": device, "payload": payload}, timeout=8))
            except Exception as e:  # noqa: BLE001
                log.warning(f"verify sem servidor ({e}) — enfileirado, decisão local")
                enqueue(kind, device, payload)
                return self._reply(OK)
        self._reply(OK)
        threading.Thread(target=self._forward, args=(kind, device, payload), daemon=True).start()

    @staticmethod
    def _forward(kind, device, payload):
        try:
            server_call("POST", f"/agent/events/{kind}", {"device_id": device, "payload": payload})
        except Exception:  # noqa: BLE001
            enqueue(kind, device, payload)


def subscribe_all():
    addr = CFG.get("advertise_ip")
    for dev in DEVICES.values():
        info = {"DeviceID": dev["device_id"], "Num": 2,
                "Topics": ["Snap", "VerifyWithSnap", "Card", "Alarm", "QRCode", "IDCard"],
                "SubscribeAddr": f"http://{addr}:{PORT}",
                "SubscribeUrl": {"Snap": "/Subscribe/Snap", "Verify": "/Subscribe/Verify", "HeartBeat": "/Subscribe/heartbeat",
                                 "Card": "/Subscribe/Card", "Alarm": "/Subscribe/Alarm", "QRCode": "/Subscribe/QRCode",
                                 "IDCard": "/Subscribe/IDCard"},
                "BeatInterval": 30, "ResumefromBreakpoint": 1, "Auth": "none"}
        r = device_call(dev, "Subscribe", info)
        log.info(f"Subscribe {dev['name']} ({dev['ip']}): {r.get('http_status')} {r.get('body') or r.get('error')}")


def config_loop():
    last_sub = 0
    while True:
        try:
            cfg = server_call("GET", "/agent/config")
            DEVICES.clear()
            DEVICES.update({str(d["device_id"]): d for d in cfg["devices"] if d.get("device_id")})
            if time.time() - last_sub > 1800:
                subscribe_all()
                last_sub = time.time()
        except Exception as e:  # noqa: BLE001
            log.warning(f"config: {e}")
        time.sleep(60)


def command_loop():
    while True:
        try:
            for c in server_call("GET", "/agent/commands?wait=20", timeout=35):
                dev = next((d for d in DEVICES.values() if d["controller_id"] == c["controller_id"]), None) or \
                    {"ip": c["ip"], "port": c["port"]}
                r = device_call(dev, c["operator"], c.get("info"))
                log.info(f"comando {c['operator']} -> {dev.get('ip')}: {r.get('http_status')}")
                server_call("POST", f"/agent/commands/{c['id']}/result", r)
        except Exception as e:  # noqa: BLE001
            log.warning(f"comandos: {e}")
            time.sleep(5)


if __name__ == "__main__":
    if not CFG.get("advertise_ip"):
        sys.exit("Defina advertise_ip (IP deste PC na rede do facial) no agent.json")
    for fn in (config_loop, command_loop, flush_loop):
        threading.Thread(target=fn, daemon=True).start()
    log.info(f"pi-access-agent escutando http://0.0.0.0:{PORT}/Subscribe/... servidor {SERVER}")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()

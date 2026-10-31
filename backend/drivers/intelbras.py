"""Driver Intelbras linha Bio-T (SS 3532 MF W e afins) — API CGI HTTP com autenticação Digest.

Servidor → facial: cadastro de usuários/faces/cartões, abrir porta, relógio, Modo Online.
Facial → servidor (Modo Online): ver intelbras_ingest.py (POST /notification + keepalive).

UserID no facial é um número curto (o facial não aceita o uuid do SCARVEL): o mapa uuid ↔ UserID
fica na coleção device_uids (vale para todos os faciais Intelbras do cliente).
LGPD: CPF (CitizenIDNo) e telefone NÃO são enviados ao facial.
"""
import json
import logging
from datetime import datetime
from urllib.parse import quote
from zoneinfo import ZoneInfo

import httpx
from pymongo import ReturnDocument

from database import db
from security import decrypt_secret
from .base import AccessControlDriver
from .beward_common import prepare_photo

logger = logging.getLogger(__name__)
TZ = ZoneInfo("America/Sao_Paulo")
TIMEOUT = 8
FOREVER = ("2020-01-01 00:00:00", "2037-12-31 23:59:59")
FACE_MAX_BYTES = 200_000  # foto de face: JPEG pequeno (o facial recusa imagens grandes)


# ---------- mapa uuid ↔ UserID ----------
async def uid_for(subject_id: str, create=True):
    doc = await db.device_uids.find_one({"_id": str(subject_id)})
    if doc or not create:
        return str(doc["uid"]) if doc else None
    seq = await db.device_uids.find_one_and_update({"_id": "__seq__"}, {"$inc": {"n": 1}}, upsert=True,
                                                    return_document=ReturnDocument.AFTER)
    uid = int(seq["n"])
    try:
        await db.device_uids.insert_one({"_id": str(subject_id), "uid": uid})
    except Exception:  # noqa: BLE001 — corrida: outro processo criou antes
        doc = await db.device_uids.find_one({"_id": str(subject_id)})
        return str(doc["uid"])
    return str(uid)


async def subject_for_uid(uid):
    if uid in (None, ""):
        return None
    doc = await db.device_uids.find_one({"uid": int(uid)}) if str(uid).isdigit() else None
    return doc["_id"] if doc else None


# ---------- helpers puros ----------
def sensor_type_code(kind) -> int:
    """Tipo do contato do sensor no ponto do SCARVEL → valor do facial (SS 3532 MF W: 0 = NF, 1 = NA)."""
    return 0 if kind == "NF" else 1


def parse_kv(text: str) -> dict:
    """Resposta CGI 'chave=valor' por linha → dict."""
    out = {}
    for line in (text or "").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def is_ok(status: int, text: str) -> bool:
    t = (text or "").strip()
    return status == 200 and not t.lower().startswith("error")


def user_payload(uid: str, person: dict) -> dict:
    begin, end = FOREVER
    if person.get("card_valid_begin") and person.get("card_valid_end"):
        begin, end = person["card_valid_begin"], person["card_valid_end"]
    u = {"UserID": uid, "UserName": (person.get("name") or "")[:32], "UserType": 0, "UserStatus": 0,
         "Authority": 2, "Doors": [0], "TimeSections": [255], "ValidFrom": begin, "ValidTo": end}
    if person.get("pin"):
        u["Password"] = str(person["pin"])[:8]
    return u


def door_state(mode: str) -> str:
    return {"liberada": "OpenAlways", "bloqueada": "CloseAlways"}.get(mode, "Normal")


class IntelbrasDriver(AccessControlDriver):
    brand = "intelbras"

    def _base(self):
        import vpn
        d = self.device
        ip, port = vpn.device_addr(d.get("ip", ""), d.get("port") or 80)
        return f"http://{ip}:{port}"

    def _auth(self):
        d = self.device
        pwd = decrypt_secret(d.get("password_enc", "")) or d.get("password", "")
        return httpx.DigestAuth(d.get("username") or "admin", pwd)

    async def _req(self, method, cgi, query="", body=None, timeout=TIMEOUT):
        url = f"{self._base()}/cgi-bin/{cgi}" + (f"?{query}" if query else "")
        try:
            async with httpx.AsyncClient(timeout=timeout, auth=self._auth()) as c:
                if method == "POST":
                    r = await c.post(url, content=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
                else:
                    r = await c.get(url)
            ok = is_ok(r.status_code, r.text)
            detail = "" if ok else (f"HTTP {r.status_code}: " + (r.text or "").strip()[:160])
            if r.status_code == 401:
                detail = "Usuário ou senha do facial incorretos (HTTP 401)"
            return {"ok": ok, "code": r.status_code, "text": r.text, "detail": detail}
        except httpx.TimeoutException:
            return {"ok": False, "code": 0, "text": "", "detail": f"Facial não respondeu em {timeout}s ({self._base()})"}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "code": 0, "text": "", "detail": f"Sem conexão com {self._base()}: {str(e)[:120]}"}

    async def snapshot(self, timeout=4):
        """Foto da câmera do facial agora (JPEG) ou None."""
        try:
            async with httpx.AsyncClient(timeout=timeout, auth=self._auth()) as c:
                r = await c.get(f"{self._base()}/cgi-bin/snapshot.cgi?channel=1")
            return r.content if r.status_code == 200 and r.content[:3] == b"\xff\xd8\xff" else None
        except Exception:  # noqa: BLE001
            return None

    async def _get(self, cgi, query=""):
        return await self._req("GET", cgi, query)

    async def _post(self, cgi, query, body):
        return await self._req("POST", cgi, query, body, timeout=20)

    # --- conexão / status ---
    async def connect(self):
        return (await self._get("magicBox.cgi", "action=getSoftwareVersion"))["ok"]

    async def get_status(self):
        r = await self._get("magicBox.cgi", "action=getSoftwareVersion")
        return {"online": r["ok"], "firmware": parse_kv(r["text"]).get("version", ""), "detail": r["detail"]}

    async def get_device_info(self):
        v = await self._get("magicBox.cgi", "action=getSoftwareVersion")
        if not v["ok"]:
            return {"ok": False, "brand": "intelbras", "firmware": "", "detail": v["detail"], "code": v["code"]}
        sn = await self._get("magicBox.cgi", "action=getSerialNo")
        return {"ok": True, "brand": "intelbras", "firmware": parse_kv(v["text"]).get("version", ""),
                "serial": parse_kv(sn["text"]).get("sn", ""), "code": 200, "detail": ""}

    # --- porta ---
    async def open_door(self, door_id, seconds=5):
        return await self._get("accessControl.cgi", "action=openDoor&channel=1&Type=Remote")

    async def set_door_mode(self, door_id, mode):
        return await self._get("configManager.cgi", f"action=setConfig&AccessControl[0].State={door_state(mode)}")

    # --- cadastro ---
    async def sync_person(self, person):
        uid = await uid_for(person["id"])
        body = {"UserList": [user_payload(uid, person)]}
        r = await self._post("AccessUser.cgi", "action=insertMulti", body)
        if not r["ok"]:  # já existe → atualiza
            r = await self._post("AccessUser.cgi", "action=updateMulti", body)
        if r["ok"] and person.get("card_number"):
            c = await self.sync_card(person["id"], {"number": person["card_number"]})
            if not c["ok"]:
                return {**c, "detail": "cartão: " + c["detail"]}
        return {**r, "uid": uid}

    async def delete_person(self, person_id):
        ids = person_id if isinstance(person_id, list) else [person_id]
        uids = [u for u in [await uid_for(i, create=False) for i in ids] if u]
        if not uids:
            return {"ok": True, "detail": "não estava no facial"}
        q = "&".join(f"UserIDList[{i}]={u}" for i, u in enumerate(uids[:100]))
        r = await self._get("AccessUser.cgi", f"action=removeMulti&{q}")
        if not r["ok"] and r["code"] in (400, 500):  # usuário inexistente no facial: nada a remover
            return {**r, "ok": True, "detail": "não estava no facial"}
        return r

    async def sync_face(self, person_id, photo):
        uid = await uid_for(person_id)
        b64 = prepare_photo(photo, max_bytes=FACE_MAX_BYTES)
        if not b64:
            return {"ok": False, "detail": "foto inválida"}
        body = {"FaceList": [{"UserID": uid, "PhotoData": [b64]}]}
        r = await self._post("AccessFace.cgi", "action=insertMulti", body)
        if not r["ok"]:
            r = await self._post("AccessFace.cgi", "action=updateMulti", body)
        if not r["ok"]:
            r["detail"] = r["detail"] or "facial recusou a foto"
        return r

    async def sync_card(self, person_id, card):
        uid = await uid_for(person_id)
        body = {"CardList": [{"UserID": uid, "CardNo": str(card.get("number", "")), "CardType": 0, "CardStatus": 0}]}
        return await self._post("AccessCard.cgi", "action=insertMulti", body)

    async def sync_access_rules(self):
        return {"ok": True, "note": "Modo Online: regras avaliadas no servidor"}

    async def count_users(self):
        r = await self._get("recordFinder.cgi", "action=getQuerySize&name=AccessUserInfo")
        return {**r, "count": parse_kv(r["text"]).get("count")}

    async def configure_door(self, ap: dict):
        """Relé, tempo de porta aberta e sensor (giro) conforme o ponto de acesso do SCARVEL.

        Cada parâmetro vai num setConfig separado (um parâmetro recusado não derruba os outros) e o
        resultado é conferido com getConfig. Testado no SS 3532 MF W: SensorType 0 = NF, 1 = NA
        (com 0 e o fio solto o facial mostra a porta "Open")."""
        sensor = ap.get("passage_mode") == "confirmacao"
        stype = sensor_type_code(ap.get("sensor_type"))
        want = {"UnlockHoldInterval": int(ap.get("relay_time") or 5) * 1000,
                "CloseTimeout": int(ap.get("door_open_time") or 20),
                "SensorEnable": "true" if sensor else "false"}
        if sensor:
            want["SensorType"] = stype
        failed = []
        for k, v in want.items():
            r = await self._get("configManager.cgi", f"action=setConfig&AccessControl[0].{k}={v}")
            if not r["ok"]:
                failed.append(f"{k}: {r['detail'] or r['code']}")
        if sensor:  # alguns firmwares usam o tipo geral; não é obrigatório
            await self._get("configManager.cgi", f"action=setConfig&AccessControlGeneral.SensorType={stype}")
        cfg = await self._get("configManager.cgi", "action=getConfig&name=AccessControl")
        if not cfg["ok"]:
            return {**cfg, "detail": "não foi possível conferir a configuração da porta: " + (cfg["detail"] or str(cfg["code"]))}
        got = parse_kv(cfg["text"])
        wrong = [k for k, v in want.items() if str(got.get(f"table.AccessControl[0].{k}", "")).lower() != str(v).lower()]
        if wrong:
            detail = "facial não aceitou: " + ", ".join(f"{k} (está {got.get('table.AccessControl[0].' + k, '?')}, devia ser {want[k]})" for k in wrong)
            if failed:
                detail += " · " + "; ".join(failed)
            return {"ok": False, "code": 200, "text": cfg["text"], "detail": detail}
        return {"ok": True, "code": 200, "text": "OK", "detail": "sensor ligado" if sensor else "sensor desligado"}

    # --- Modo Online ---
    async def configure_online(self, host: str, port: int, token: str, keepalive_s: int = 10, timeout_ms: int = 2000):
        """Liga o envio de eventos ao SCARVEL e o Modo Online (servidor decide e mostra a mensagem)."""
        base = f"/api/intelbras/{token}"
        q1 = ("action=setConfig&PictureHttpUpload.Enable=true"
              f"&PictureHttpUpload.UploadServerList[0].Address={quote(host)}"
              f"&PictureHttpUpload.UploadServerList[0].Port={int(port)}"
              f"&PictureHttpUpload.UploadServerList[0].Uploadpath={quote(base + '/notification')}")
        r1 = await self._get("configManager.cgi", q1)
        if not r1["ok"]:
            return {**r1, "step": "servidor de eventos"}
        q2 = ("action=setConfig&Intelbras_ModeCfg.DeviceMode=2&Intelbras_ModeCfg.KeepAlive.Enable=true"
              f"&Intelbras_ModeCfg.KeepAlive.Interval={int(keepalive_s)}"
              f"&Intelbras_ModeCfg.KeepAlive.Path={quote(base + '/keepalive')}"
              f"&Intelbras_ModeCfg.KeepAlive.TimeOut={int(timeout_ms)}&Intelbras_ModeCfg.RemoteCheckTimeout=5")
        r2 = await self._get("configManager.cgi", q2)
        return {**r2, "step": "modo online"}

    async def get_events(self, since=None):
        return []  # Modo Online: eventos chegam por push

    # --- operações ---
    async def set_datetime(self):
        now = datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")
        return await self._get("global.cgi", f"action=setCurrentTime&time={quote(now)}")

    async def reboot(self):
        return await self._get("magicBox.cgi", "action=reboot")

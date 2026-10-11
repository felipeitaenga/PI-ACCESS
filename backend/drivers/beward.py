"""Driver BEWARD (linha B2002FR) — transportes HTTP e MQTT, interface Adapter comum."""
import os
import json
import logging
import httpx
from .base import AccessControlDriver
from .beward_common import (time_range_to_strategy, strategy_id_for, prepare_photo,
                            map_verify, VERIFY_STATUS, VERIFY_TYPE)
from security import decrypt_secret

logger = logging.getLogger(__name__)

OPENDOOR_BY_MODE = {"servidor": 3, "local": 0, "local_remoto": 2}


class _BewardShared:
    """Lógica comum aos dois transportes."""

    def _creds(self):
        d = self.device
        pwd = decrypt_secret(d.get("password_enc", "")) or d.get("password", "")
        return d.get("username", "admin"), pwd

    def person_payload(self, person: dict, photo_mode="picinfo", pic_uri=None, strategy_ids=None):
        p = {
            "IdType": 2, "PersonUUID": str(person.get("id"))[:48],
            "Name": (person.get("name") or "")[:32],
            "PersonType": 1 if person.get("_impeditive") else 0,
            "IdCard": person.get("document", ""), "Telnum": person.get("phone", ""),
            "Notes": person.get("role_title", ""),
        }
        if person.get("valid_until"):
            p["Tempvalid"] = 0  # validade controlada pelo NX-ACCESS, não pelo equipamento
        if strategy_ids is not None:
            p["strategyInfo"] = {"strategyData": [{"strategyID": s} for s in strategy_ids]}
        if person.get("pin"):
            p["PersonalPassword"] = str(person["pin"])[:6]
        if photo_mode == "picURI" and pic_uri:
            p["picURI"] = pic_uri
        elif person.get("photo"):
            b64 = prepare_photo(person["photo"])
            if b64:
                p["picinfo"] = b64
        return p


class BewardHttpDriver(_BewardShared, AccessControlDriver):
    brand = "beward_http"

    def _url(self, operator):
        ip = self.device.get("ip", "")
        port = self.device.get("port") or 80
        return f"http://{ip}:{port}/action/{operator}"

    async def _post(self, operator, info=None):
        user, pwd = self._creds()
        body = json.dumps({"operator": operator, "info": info or {}}).encode("utf-8")
        headers = {"Content-Type": "application/json", "Content-Length": str(len(body))}
        try:
            async with httpx.AsyncClient(timeout=15) as c:
                r = await c.post(self._url(operator), content=body, headers=headers, auth=(user, pwd))
            data = r.json() if r.content else {}
            code = data.get("code", r.status_code)
            detail = (data.get("info") or {}).get("Detail", "")
            return {"ok": code == 200, "code": code, "detail": detail, "info": data.get("info", {})}
        except Exception as e:
            return {"ok": False, "code": 0, "detail": str(e), "info": {}}

    def _device_id(self):
        return self.device.get("beward_device_id")

    async def connect(self):
        r = await self.get_device_info()
        return r.get("ok", False)

    async def get_status(self):
        r = await self._post("GetSysParam")
        return {"online": r["ok"], "firmware": r.get("info", {}).get("Version", ""), "detail": r["detail"]}

    async def get_device_info(self):
        r = await self._post("GetSysParam")
        info = r.get("info", {})
        return {"ok": r["ok"], "brand": "beward", "name": info.get("Name"),
                "device_id": info.get("DeviceID"), "firmware": info.get("Version"),
                "code": r["code"], "detail": r["detail"]}

    async def set_datetime(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        n = datetime.now(ZoneInfo("America/Sao_Paulo"))
        return await self._post("SetSysTime", {"DeviceID": self._device_id(), "Year": n.year,
                "Month": n.month, "Day": n.day, "Hour": n.hour, "Minute": n.minute, "Second": n.second})

    async def open_door(self, door_id, seconds=5):
        return await self._post("OpenDoor", {"DeviceID": self._device_id(), "status": 1,
                "msg": "Acesso liberado", "msgAttribute": {"color": "green", "pleace": 1, "font": 32}})

    async def set_door_mode(self, door_id, mode):
        return await self._post("SetKeepOpen", {"DeviceID": self._device_id(), "KeepOpen": 1 if mode == "liberada" else 0})

    async def sync_person(self, person, strategy_ids=None):
        return await self._post("EditPersonNew", self.person_payload(person, "picinfo", strategy_ids=strategy_ids))

    async def sync_persons_batch(self, people_with_uri):
        """people_with_uri: lista de (person, pic_uri, strategy_ids). Foto só por picURI neste comando."""
        persons = [self.person_payload(p, "picURI", uri, sids) for (p, uri, sids) in people_with_uri[:1000]]
        return await self._post("EditPersonsNew", {"PersonList": persons, "TotalNum": len(persons)})

    async def delete_person(self, person_id):
        ids = person_id if isinstance(person_id, list) else [person_id]
        return await self._post("DeletePerson", {"IdType": 2, "PersonUUID": ids[:256], "TotalNum": len(ids[:256])})

    async def delete_all(self):
        return await self._post("DeleteAllPerson", {"DeviceID": self._device_id()})

    async def query_persons(self):
        return await self._post("searchPersonNum", {"DeviceID": self._device_id()})

    async def sync_face(self, person_id, photo):
        return await self._post("EditPersonNew", {"IdType": 2, "PersonUUID": person_id, "picinfo": prepare_photo(photo)})

    async def sync_card(self, person_id, card):
        info = {"IdType": 2, "PersonUUID": person_id, "RFIDCard": card.get("number"),
                "RFCardMode": 1 if card.get("hex") else 0}
        if card.get("wiegand"):
            info.update({"MjCardFrom": 2, "WiegandType": card.get("wiegand_type", 0),
                         "WGFacilityCode": card.get("facility", 0), "MjCardNo": card.get("number")})
        return await self._post("EditPersonNew", info)

    async def add_strategy(self, time_range, holidays=None):
        return await self._post("AddAccessStrategy", time_range_to_strategy(time_range, holidays))

    async def del_strategy(self, strategy_id):
        return await self._post("DelAccessStrategy", {"strategyID": strategy_id})

    async def bind_person_strategies(self, person_uuid, strategy_ids):
        """Substituição TOTAL — envia sempre a lista completa."""
        return await self._post("PersonsBindStrategyID", {"PersonUUID": [person_uuid],
                "strategyID": list(strategy_ids)})

    async def sync_access_rules(self):
        return {"ok": True, "note": "use add_strategy + bind_person_strategies por pessoa"}

    async def set_door_condition(self, decision_mode="servidor", verify_mode=1, wiegand=0, reset_time=3):
        return await self._post("SetDoorCondition", {"DeviceID": self._device_id(),
                "OpendoorWay": OPENDOOR_BY_MODE.get(decision_mode, 3), "VerifyMode": verify_mode,
                "VerifyResetTime": reset_time, "Wiegand": wiegand})

    async def get_door_condition(self):
        return await self._post("GetDoorCondition", {"DeviceID": self._device_id()})

    async def set_face_param(self, threshold=75):
        return await self._post("SetFaceParam", {"DeviceID": self._device_id(), "Similarity": threshold})

    async def get_events(self, since=None):
        r = await self._post("searchControl", {"DeviceID": self._device_id(), "StartTime": since or ""})
        return r.get("info", {}).get("Records", [])

    async def subscribe(self, payload):
        return await self._post("Subscribe", payload)

    async def reboot(self):
        return await self._post("RebootDevice", {"DeviceID": self._device_id()})


class BewardMqttDriver(_BewardShared, AccessControlDriver):
    """Transporte MQTT (equipamentos fora da rede/4G). Publica comandos com messageId."""
    brand = "beward_mqtt"
    _seq = 0

    def _client(self):
        import paho.mqtt.client as mqtt
        broker = os.environ.get("MQTT_BROKER", "localhost")
        port = int(os.environ.get("MQTT_PORT", "61613"))
        cli = mqtt.Client(client_id=f"nxaccess-{self.device.get('id','')[:8]}")
        cli.connect(broker, port, keepalive=30)
        return cli

    def _topic(self):
        return f"mqtt/face/{self.device.get('beward_device_id') or self.device.get('id')}"

    async def _publish(self, operator, info=None):
        BewardMqttDriver._seq += 1
        msg = {"operator": operator, "messageId": f"nx-{BewardMqttDriver._seq}", "info": info or {}}
        try:
            cli = self._client()
            cli.publish(self._topic(), json.dumps(msg), qos=1)
            cli.disconnect()
            return {"ok": True, "messageId": msg["messageId"], "detail": "publicado (aguarda Ack em /Ack)"}
        except Exception as e:
            return {"ok": False, "code": 0, "detail": f"MQTT indisponível: {e}"}

    async def connect(self):
        try:
            cli = self._client(); cli.disconnect(); return True
        except Exception:
            return False

    async def get_status(self): return {"online": await self.connect()}
    async def get_device_info(self): return await self._publish("Versions")
    async def set_datetime(self): return await self._publish("SetSysTime")
    async def open_door(self, door_id, seconds=5):
        return await self._publish("Unlock", {"facesluiceId": self.device.get("beward_device_id"),
                "openDoor": 1, "showInfo": "Acesso liberado"})
    async def set_door_mode(self, door_id, mode):
        return await self._publish("SetKeepOpen", {"KeepOpen": 1 if mode == "liberada" else 0})
    async def sync_person(self, person, strategy_ids=None):
        info = self.person_payload(person, "picinfo", strategy_ids=strategy_ids)
        info["customId"] = str(person.get("id"))
        return await self._publish("EditPerson", info)
    async def delete_person(self, person_id):
        ids = person_id if isinstance(person_id, list) else [person_id]
        return await self._publish("DeletePersons", {"PersonUUID": ids})
    async def sync_face(self, person_id, photo):
        return await self._publish("EditPerson", {"customId": person_id, "pic": prepare_photo(photo)})
    async def sync_card(self, person_id, card):
        return await self._publish("EditPerson", {"customId": person_id, "RFIDCard": card.get("number")})
    async def sync_access_rules(self): return {"ok": True}
    async def add_strategy(self, time_range, holidays=None):
        return await self._publish("AddAccessStrategy", time_range_to_strategy(time_range, holidays))
    async def bind_person_strategies(self, person_uuid, strategy_ids):
        return await self._publish("PersonsBindStrategyID", {"PersonUUID": [person_uuid], "strategyID": list(strategy_ids)})
    async def get_events(self, since=None): return []
    async def subscribe(self, payload): return {"ok": True, "note": "MQTT usa tópicos, assinatura não necessária"}
    async def reboot(self): return await self._publish("RebootDevice")

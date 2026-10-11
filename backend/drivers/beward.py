"""Driver BEWARD (linha B2002FR) — transportes HTTP e MQTT, interface Adapter comum."""
import os
import json
import base64
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
            p["Tempvalid"] = 0  # validade controlada pelo PI-ACCESS, não pelo equipamento
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
        """Facial na rede local: comando executado pelo pi-access-agent (POST http://ip/action/<Operator>)."""
        from routers.integrations import run_via_agent
        return await run_via_agent(self.device, operator, info)

    async def _post_direct(self, operator, info=None):
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
    """Transporte MQTT via broker externo (mqtt_bus). Comandos em <prefixo>/<ID Equipamento> com Ack."""
    brand = "beward_mqtt"

    def _dev(self):
        return str(self.device.get("beward_device_id") or "")

    def _online(self):
        from datetime import datetime, timezone
        from mqtt_bus import ONLINE_WINDOW
        hb = self.device.get("last_heartbeat")
        return bool(hb) and (datetime.now(timezone.utc) - datetime.fromisoformat(hb)).total_seconds() < ONLINE_WINDOW

    async def _publish(self, operator, info=None):
        from mqtt_bus import bus
        if not self._dev():
            return {"ok": False, "detail": "Informe o ID Equipamento (DeviceID)"}
        return await bus.command(self._dev(), operator, info, online=self._online())

    async def connect(self):
        from mqtt_bus import bus
        return bus.connected and self._online()

    async def get_status(self):
        from mqtt_bus import bus
        online = await self.connect()
        err = "" if online else ("broker MQTT desconectado" if not bus.connected else
                                 "sem heartbeat do facial (<prefixo>/heartbeat) nos últimos 3 min")
        return {"online": online, "error": err, "last_heartbeat": self.device.get("last_heartbeat")}

    async def get_device_info(self):
        r = await self._publish("Versions")
        if not r.get("ok") and self._online():
            # alguns firmwares não respondem "Versions" por MQTT; o heartbeat recente já prova a comunicação
            return {"ok": True, "firmware": self.device.get("firmware", ""),
                    "detail": "Online (heartbeat recente). O facial não respondeu ao comando Versions."}
        return {"ok": r.get("ok"), "firmware": (r.get("info") or {}).get("firmware", ""), **r}

    async def set_datetime(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        return await self._publish("SetSysTime", {"SysTime": datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%Y-%m-%d %H:%M:%S")})

    async def open_door(self, door_id, seconds=5):
        return await self._publish("Unlock", {"openDoor": "1", "showInfo": "Acesso liberado"})

    async def set_door_mode(self, door_id, mode):
        return await self._publish("SetKeepOpen", {"KeepOpen": 1 if mode == "liberada" else 0})

    async def _photo_b64(self, photo):
        """Foto sempre embutida em base64 (o facial não alcança URLs externas/HTTPS)."""
        if photo and photo.startswith("http"):
            try:
                async with httpx.AsyncClient(timeout=10, follow_redirects=True) as c:
                    r = await c.get(photo)
                if r.status_code == 200 and r.content:
                    photo = base64.b64encode(r.content).decode()
                else:
                    return ""
            except Exception:  # noqa: BLE001
                return ""
        return prepare_photo(photo or "", max_bytes=200_000)

    async def sync_person(self, person, strategy_ids=None):
        info = {"customId": str(person.get("id"))[:48], "name": (person.get("name") or "")[:32],
                "personType": 0, "idCard": person.get("document") or person.get("cpf") or "",
                "telnum": person.get("phone", ""), "tempCardType": 0}
        if person.get("temp_valid"):
            info.update({"tempCardType": 1, "cardValidBegin": person["card_valid_begin"],
                         "cardValidEnd": person["card_valid_end"]})
        if person.get("card_number"):
            info["RFIDCard"] = str(person["card_number"])
        b64 = await self._photo_b64(person.get("photo") or "")
        if not b64:
            return {"ok": False, "detail": "Pessoa sem foto válida — o facial exige foto no cadastro"}
        info["pic"] = f"data:image/jpeg;base64,{b64}"
        if strategy_ids is not None:
            info["strategyID"] = list(strategy_ids)
        return await self._publish("EditPerson", info)

    async def delete_person(self, person_id):
        ids = person_id if isinstance(person_id, list) else [person_id]
        return await self._publish("DeletePersons", {"customId": [str(i) for i in ids]})

    async def sync_face(self, person_id, photo):
        return {"ok": True, "detail": "foto enviada junto no EditPerson"}

    async def sync_card(self, person_id, card):
        return await self._publish("EditPerson", {"customId": person_id, "RFIDCard": card.get("number")})

    async def sync_access_rules(self): return {"ok": True}

    async def add_strategy(self, time_range, holidays=None):
        return await self._publish("AddAccessStrategy", time_range_to_strategy(time_range, holidays))

    async def bind_person_strategies(self, person_uuid, strategy_ids):
        return await self._publish("PersonsBindStrategyID", {"customId": [person_uuid], "strategyID": list(strategy_ids)})

    async def set_door_condition(self, decision_mode="servidor", verify_mode=1, wiegand=0, reset_time=3):
        return await self._publish("SetDoorCondition", {"OpendoorWay": OPENDOOR_BY_MODE.get(decision_mode, 3),
                                                         "VerifyMode": verify_mode, "VerifyResetTime": reset_time})

    async def get_events(self, since=None): return []
    async def subscribe(self, payload): return {"ok": True, "note": "MQTT usa o prefixo de tópico definido em Integrações"}
    async def reboot(self): return await self._publish("RebootDevice")

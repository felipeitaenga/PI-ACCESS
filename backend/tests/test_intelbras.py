"""Intelbras Bio-T: driver CGI (UserID curto, LGPD) e Modo Online (o servidor decide e responde auth/message)."""
import asyncio
import base64
import json
from datetime import datetime, timedelta, timezone

import mongomock_motor
import pytest

import access_service
import beward_ingest
import intelbras_ingest
import scope
import visits_core
from drivers import intelbras
from drivers.factory import get_driver

_LOOP = asyncio.new_event_loop()
JPEG = b"\xff\xd8\xff\xe0fakejpeg\xff\xd9"


def run(c):
    return _LOOP.run_until_complete(c)


@pytest.fixture()
def env(monkeypatch):
    db = mongomock_motor.AsyncMongoMockClient()["t_intelbras"]
    import passage
    for m in (access_service, beward_ingest, intelbras_ingest, scope, visits_core, intelbras, passage):
        monkeypatch.setattr(m, "db", db)

    async def _noop(*a, **k):
        return None
    monkeypatch.setattr(intelbras_ingest.manager, "broadcast", _noop)
    monkeypatch.setattr(beward_ingest.manager, "broadcast", _noop)
    now = datetime.now(timezone.utc)
    ctrl = {"id": "c1", "name": "Facial Intelbras", "brand": "intelbras", "ip": "10.66.1.2", "port": 8013,
            "username": "admin", "password": "x", "intelbras_token": "t" * 32, "online_mode": True, "deleted": False,
            "online": True, "time_synced_at": now.isoformat(), "time_sync_tried_at": now.isoformat()}
    run(db.controllers.insert_one(dict(ctrl)))
    run(db.access_points.insert_one({"id": "ap1", "controller_id": "c1", "reader": 1, "site_id": "s1", "direction": "entrada",
                                     "origin_area_id": "ext", "dest_area_id": "int", "deleted": False, "description": "Porta"}))
    run(db.areas.insert_many([{"id": "int", "description": "Interna"}, {"id": "ext", "description": "Externa", "is_exterior": True}]))
    run(db.time_ranges.insert_one({"id": "tr", "enabled": True, "weekdays": [0, 1, 2, 3, 4, 5, 6], "valid_on_holidays": True,
                                   "intervals": [{"start": "00:00", "end": "23:59"}]}))
    run(db.categories.insert_one({"id": "cat", "code": "FUNC", "enabled": True, "impeditive": False, "control_origin": False,
                                  "control_anti_double": True, "reentry_timed": False, "reentry_minutes": 0,
                                  "access_areas": [{"area_id": "int", "time_range_id": "tr", "require_escort": False}]}))
    run(db.people.insert_one({"id": "p-uuid-1", "name": "Mariana Costa Lima", "status": "ativo", "category_ids": ["cat"],
                              "doc_number": "11144477735", "phone": "11999999999", "person_type": "funcionario"}))
    return db, ctrl, now


class FakeReq:
    """Grava as chamadas CGI do driver em vez de ir à rede."""

    def __init__(self, monkeypatch, responses=None):
        self.calls = []
        self.responses = responses or {}
        me = self

        async def _req(drv, method, cgi, query="", body=None, timeout=8):
            me.calls.append((method, cgi, query, body))
            ok = me.responses.get((cgi, query.split("&")[0]), True)
            return {"ok": ok, "code": 200 if ok else 400, "text": "OK" if ok else "Error", "detail": "" if ok else "erro"}
        monkeypatch.setattr(intelbras.IntelbrasDriver, "_req", _req)


def test_factory_returns_intelbras_driver():
    assert isinstance(get_driver({"brand": "intelbras"}), intelbras.IntelbrasDriver)


def test_uid_is_short_stable_and_reversible(env):
    a1 = run(intelbras.uid_for("p-uuid-1"))
    a2 = run(intelbras.uid_for("p-uuid-1"))
    b = run(intelbras.uid_for("v-uuid-2"))
    assert a1 == a2 == "1" and b == "2"
    assert run(intelbras.subject_for_uid("2")) == "v-uuid-2"
    assert run(intelbras.uid_for("nunca-enviado", create=False)) is None


def test_sync_person_sends_no_cpf_or_phone_and_falls_back_to_update(env, monkeypatch):
    db, ctrl, _ = env
    fr = FakeReq(monkeypatch, {("AccessUser.cgi", "action=insertMulti"): False})  # já existe no facial
    person = run(db.people.find_one({"id": "p-uuid-1"}, {"_id": 0}))
    r = run(get_driver(ctrl).sync_person(person))
    assert r["ok"] and r["uid"] == "1"
    assert [c[2] for c in fr.calls] == ["action=insertMulti", "action=updateMulti"]
    u = fr.calls[-1][3]["UserList"][0]
    assert u["UserID"] == "1" and u["UserName"] == "Mariana Costa Lima"
    dump = json.dumps(fr.calls)
    assert "11144477735" not in dump and "11999999999" not in dump and "CitizenIDNo" not in dump


def test_visitor_validity_goes_to_device(env, monkeypatch):
    _, ctrl, _ = env
    fr = FakeReq(monkeypatch)
    run(get_driver(ctrl).sync_person({"id": "v9", "name": "Visitante", "card_valid_begin": "2026-10-29 09:00:00",
                                      "card_valid_end": "2026-10-29 13:00:00", "card_number": "12345"}))
    u = fr.calls[0][3]["UserList"][0]
    assert (u["ValidFrom"], u["ValidTo"]) == ("2026-10-29 09:00:00", "2026-10-29 13:00:00")
    assert fr.calls[-1][1] == "AccessCard.cgi" and fr.calls[-1][3]["CardList"][0]["CardNo"] == "12345"


def test_delete_uses_mapped_ids_and_skips_unknown(env, monkeypatch):
    _, ctrl, _ = env
    fr = FakeReq(monkeypatch)
    run(intelbras.uid_for("a"))
    run(intelbras.uid_for("b"))
    r = run(get_driver(ctrl).delete_person(["a", "b", "nunca-enviado"]))
    assert r["ok"] and fr.calls[0][2] == "action=removeMulti&UserIDList[0]=1&UserIDList[1]=2"
    fr.calls.clear()
    assert run(get_driver(ctrl).delete_person("so-no-scarvel"))["ok"] and fr.calls == []


def test_configure_online_points_to_token_paths(env, monkeypatch):
    _, ctrl, _ = env
    fr = FakeReq(monkeypatch)
    r = run(get_driver(ctrl).configure_online("192.168.0.2", 8080, "TOKEN123"))
    assert r["ok"]
    q1, q2 = fr.calls[0][2], fr.calls[1][2]
    assert "UploadServerList[0].Address=192.168.0.2" in q1 and "Port=8080" in q1
    assert "Uploadpath=/api/intelbras/TOKEN123/notification" in q1
    assert "DeviceMode=2" in q2 and "KeepAlive.Path=/api/intelbras/TOKEN123/keepalive" in q2


def _multipart(data: dict, jpeg=JPEG):
    return (b"--myboundary\r\nContent-Type: text/plain\r\n\r\n" + json.dumps(data).encode() +
            b"\r\n--myboundary\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n--myboundary--\r\n")


def _access(uid, utc=None, status=0):
    return {"Events": [{"Code": "AccessControl", "Data": {"UserID": uid, "CardNo": "", "Method": 15, "Status": status,
                                                          "UTC": utc or int(datetime.now(timezone.utc).timestamp())}}]}


def test_parse_multipart_json_and_photo():
    data, jpeg = intelbras_ingest.parse_notification(_multipart(_access("1")), "multipart/x-mixed-replace; boundary=myboundary")
    assert data["Events"][0]["Data"]["UserID"] == "1" and jpeg == JPEG


def test_online_mode_server_decides_and_applies_anti_double(env):
    db, ctrl, now = env
    uid = run(intelbras.uid_for("p-uuid-1"))
    r1 = run(intelbras_ingest.handle_notification(ctrl, _multipart(_access(uid, int(now.timestamp()))), ""))
    # nova tentativa (não o eco da mesma leitura): passou do ECHO_S
    run(db.intelbras_last.update_many({}, {"$set": {"at": now - timedelta(seconds=60)}}))
    r2 = run(intelbras_ingest.handle_notification(ctrl, _multipart(_access(uid, int(now.timestamp()) + 5)), ""))
    assert r1 == {"message": "Bem-vindo(a), Mariana!", "code": "200", "auth": "true"}
    assert r2["auth"] == "false" and r2["message"].startswith("Acesso negado: Anti-dupla")
    evs = run(db.access_events.find({}, {"_id": 0}).sort("timestamp", 1).to_list(5))
    assert [e["access_result"] for e in evs] == ["granted", "denied"]
    assert evs[0]["captured_photo"].startswith("data:image/jpeg;base64,") and evs[0]["via"] == "intelbras"
    assert run(db.controllers.find_one({"id": "c1"}))["online"] is True  # notificação também conta como sinal de vida


def test_same_event_twice_is_ignored(env):
    db, ctrl, now = env
    uid = run(intelbras.uid_for("p-uuid-1"))
    body = _multipart(_access(uid, int(now.timestamp())))
    run(intelbras_ingest.handle_notification(ctrl, body, ""))
    run(intelbras_ingest.handle_notification(ctrl, body, ""))
    assert run(db.access_events.count_documents({})) == 1


def test_unknown_user_is_denied(env):
    db, ctrl, _ = env
    r = run(intelbras_ingest.handle_notification(ctrl, _multipart(_access("999")), ""))
    assert r["auth"] == "false" and "Não cadastrado" in r["message"]
    ev = run(db.access_events.find_one({}, {"_id": 0}))
    assert ev["access_result"] == "denied" and ev["person_name"] == "Desconhecido"


def test_offline_backlog_is_logged_as_retroactive_without_deciding(env):
    db, ctrl, now = env
    uid = run(intelbras.uid_for("p-uuid-1"))
    old = int((now - timedelta(hours=2)).timestamp())
    r = run(intelbras_ingest.handle_notification(ctrl, _multipart(_access(uid, old, status=1)), ""))
    assert r["auth"] == "false"  # acesso já aconteceu; resposta não abre nada
    ev = run(db.access_events.find_one({}, {"_id": 0}))
    assert ev["access_result"] == "granted" and "retroativo" in ev["reason"]


def test_keepalive_stops_raises_alarm(env):
    db, ctrl, now = env
    run(db.controllers.update_one({"id": "c1"}, {"$set": {"online": True,
                                                         "last_heartbeat": (now - timedelta(minutes=5)).isoformat()}}))
    run(intelbras_ingest.watch_once())
    assert run(db.controllers.find_one({"id": "c1"}))["online"] is False
    alarm = run(db.alarms.find_one({}, {"_id": 0}))
    assert alarm["type"] == "facial_offline" and "libera TODOS" in alarm["message"]
    run(intelbras_ingest.watch_once())
    assert run(db.alarms.count_documents({})) == 1  # não repete enquanto continua offline


def test_photo_is_base64_jpeg(env, monkeypatch):
    _, ctrl, _ = env
    fr = FakeReq(monkeypatch)
    from PIL import Image
    import io
    buf = io.BytesIO()
    Image.new("RGB", (400, 500), "gray").save(buf, "PNG")
    run(get_driver(ctrl).sync_face("p-uuid-1", "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()))
    b64 = fr.calls[0][3]["FaceList"][0]["PhotoData"][0]
    assert base64.b64decode(b64)[:3] == b"\xff\xd8\xff"


def test_routes_called_by_the_device(env, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routers import intelbras as ri
    db, ctrl, now = env
    monkeypatch.setattr(ri, "db", db)
    app = FastAPI()
    app.include_router(ri.router, prefix="/api")
    c = TestClient(app)
    assert c.get("/api/intelbras/errado-errado-errado/keepalive").status_code == 404
    r = c.get(f"/api/intelbras/{ctrl['intelbras_token']}/keepalive")
    assert r.status_code == 200 and r.text == "OK"
    uid = run(intelbras.uid_for("p-uuid-1"))
    r = c.post(f"/api/intelbras/{ctrl['intelbras_token']}/notification", content=_multipart(_access(uid)),
               headers={"Content-Type": "multipart/x-mixed-replace; boundary=myboundary"})
    assert r.status_code == 200 and r.json()["auth"] == "true"


def test_clock_is_set_when_device_comes_back_and_on_test(env, monkeypatch):
    db, ctrl, now = env
    fr = FakeReq(monkeypatch)
    run(db.controllers.update_one({"id": "c1"}, {"$set": {"online": False, "time_sync_tried_at": None}}))
    c = run(db.controllers.find_one({"id": "c1"}, {"_id": 0}))
    run(intelbras_ingest.heartbeat(c))
    run(asyncio.sleep(0.05))
    assert any(call[1] == "global.cgi" and "setCurrentTime" in call[2] for call in fr.calls)
    c = run(db.controllers.find_one({"id": "c1"}, {"_id": 0}))
    assert c["time_sync_ok"] is True and c["online"] is True
    fr.calls.clear()
    run(intelbras_ingest.heartbeat(c))  # já acertado há pouco: não repete
    run(asyncio.sleep(0.05))
    assert fr.calls == []


def test_score_of_reads_similarity_fields():
    assert intelbras_ingest.score_of({"Similarity": 87}) == 87
    assert intelbras_ingest.score_of({"FaceSimilarity": "0.913"}) == 91.3
    assert intelbras_ingest.score_of({"UserID": "1", "Method": 15}) == 0

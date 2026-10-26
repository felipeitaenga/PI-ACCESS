"""Helpers do driver BEWARD: conversões puras e utilidades de foto/estratégia."""
import base64
import binascii
import zlib

# dom(0)..sab(6) -> nomes Beward
DAY_NAMES = ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]

VERIFY_STATUS = {
    0: ("pending", "Aguardando decisão remota"),  # 1457460 no modo remoto
    1: ("granted", "Acesso liberado"),
    2: ("denied", "Lista negra"),
    3: ("denied", "Não cadastrado"),
    22: ("pending", "Aguardando decisão remota"),
    24: ("denied", "Fora da política de horário"),
}
VERIFY_TYPE = {
    1: "facial", 21: "cartao_rfid", 22: "cartao+facial", 24: "wiegand",
    25: "wiegand+facial", 27: "remoto_http",
}
DIRECTION = {0: None, 1: "entrada", 2: "saida"}

# Alarmes MQTT (AlarmInfoPush code) e HTTP
ALARM_CODES = {
    1: ("porta_aberta", "Porta aberta por tempo excedido", "media"),
    2: ("porta_forcada", "Porta forçada", "alta"),
    3: ("tamper", "Remoção do equipamento", "alta"),
    4: ("prova_vida", "Ataque de prova de vida (foto/vídeo)", "alta"),
    5: ("incendio", "Alarme de incêndio", "alta"),
    6: ("sensor_porta", "Status do sensor de porta", "baixa"),
}


def strategy_id_for(time_range_id: str) -> int:
    """ID numérico estável (int32) para o strategyID do equipamento a partir do uuid da faixa."""
    return zlib.crc32(str(time_range_id).encode()) % (2 ** 31)


def _hhmmss(t: str) -> str:
    t = (t or "00:00").strip()
    return t if t.count(":") == 2 else f"{t}:00"


def time_range_to_strategy(tr: dict, holidays: list = None) -> dict:
    """Converte uma Faixa horária do PI-ACCESS em AccessStrategy do facial Beward.
    - Dia sem acesso: NÃO inclui a chave do dia.
    - Feriados -> holidayInfo (período vazio se a faixa não vale em feriado).
    """
    intervals = [{"startTime": _hhmmss(i.get("start")), "endTime": _hhmmss(i.get("end"))}
                 for i in tr.get("intervals", [])]
    out = {
        "strategyID": strategy_id_for(tr.get("id")),
        "strategyName": (tr.get("description") or "")[:64],
        "accessNumLimit": 0,
        "startDate": "2020-01-01",
        "endDate": "2099-12-31",
    }
    for d in tr.get("weekdays", []):
        if 0 <= d <= 6 and intervals:
            out[DAY_NAMES[d]] = intervals
    holiday_info = []
    for h in (holidays or []):
        if h.get("deleted") or not h.get("enabled", True):
            continue
        date = str(h.get("date", ""))[:10]
        if not date:
            continue
        period = intervals if tr.get("valid_on_holidays") else [{"startTime": "00:00:00", "endTime": "00:00:00"}]
        holiday_info.append({"holidayStartDate": date, "holidayEndDate": date, "holidayPeriod": period})
    if holiday_info:
        out["holidayInfo"] = holiday_info
    return out


def map_verify(verify_status, verify_type, sendintime=1):
    status, reason = VERIFY_STATUS.get(int(verify_status or 0), ("denied", "Desconhecido"))
    vtype = VERIFY_TYPE.get(int(verify_type or 0), "facial")
    st = 1 if sendintime is None else int(sendintime)
    retroactive = st == 0 or int(verify_type or 0) == 27
    return {"access_result": "granted" if status == "granted" else "denied",
            "status": status, "reason": reason, "verify_type": vtype, "retroactive": retroactive}


def dedup_key(device_id, create_time, person_id):
    return f"{device_id}:{create_time}:{person_id}"


def prepare_photo(data: str, max_bytes: int = 1_000_000) -> str:
    """Normaliza foto para base64 puro (sem prefixo data:). Redimensiona se Pillow disponível."""
    if not data:
        return ""
    if data.startswith("data:"):
        data = data.split(",", 1)[-1]
    try:
        raw = base64.b64decode(data)
    except (binascii.Error, ValueError):
        return ""  # URL externa — usar picURI
    try:
        from PIL import Image  # opcional
        import io
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        if img.width > 1080:
            ratio = 1080 / img.width
            img = img.resize((1080, int(img.height * ratio)))
        q = 85
        while q >= 40:
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=q)
            if buf.tell() <= max_bytes:
                raw = buf.getvalue()
                break
            q -= 10
    except Exception:
        pass
    return base64.b64encode(raw).decode()

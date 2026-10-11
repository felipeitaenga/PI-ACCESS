"""Motor de decisão de acesso — função pura e testável."""
from datetime import datetime, timezone


def _parse(ts):
    if not ts:
        return None
    try:
        d = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d
    except Exception:
        return None


def is_holiday(d, site_id, holidays):
    for h in holidays:
        if h.get("deleted") or not h.get("enabled", True):
            continue
        if h.get("scope", "all") not in ("all", site_id):
            continue
        hd = str(h.get("date", ""))
        if h.get("recurring_annual"):
            if len(hd) >= 10 and hd[5:10] == d.strftime("%m-%d"):
                return True
        elif hd[:10] == d.strftime("%Y-%m-%d"):
            return True
    return False


def time_range_valid(tr, br_dow, hhmm, holiday):
    if not tr or not tr.get("enabled", True):
        return False
    if br_dow not in tr.get("weekdays", []):
        return False
    if holiday and not tr.get("valid_on_holidays", False):
        return False
    for iv in tr.get("intervals", []):
        if iv.get("start", "00:00") <= hhmm <= iv.get("end", "23:59"):
            return True
    return False


def decide(person, ap, dest_area, origin_area, categories, tr_by_id, holidays, now,
           company_active=True, recent_events=None, site_id=None):
    """Retorna {granted, reason, steps[], escort_required, category_code}."""
    steps = []

    def add(ok, msg):
        steps.append({"ok": ok, "msg": msg})

    def deny(reason):
        return {"granted": False, "reason": reason, "steps": steps,
                "escort_required": False, "category_code": None}

    # 1) Pessoa ativa e dentro da validade; empresa ativa
    if person.get("status") != "ativo":
        add(False, f"Pessoa com status '{person.get('status')}'")
        return deny("Pessoa inativa/bloqueada")
    add(True, "Pessoa ativa")
    vu = _parse(person.get("valid_until"))
    if vu and vu < now:
        add(False, "Validade de acesso expirada")
        return deny("Acesso expirado")
    vf = _parse(person.get("valid_from"))
    if vf and vf > now:
        add(False, "Acesso ainda não iniciado")
        return deny("Acesso fora da validade")
    add(True, "Dentro da validade")
    if not company_active:
        add(False, "Empresa inativa/contrato vencido")
        return deny("Empresa inativa")
    add(True, "Empresa ativa")

    # 2) Categoria impeditiva prevalece
    imped = [c for c in categories if c.get("impeditive")]
    if imped:
        add(False, f"Categoria impeditiva: {imped[0].get('code')}")
        return deny("Categoria impeditiva")
    add(True, "Sem categoria impeditiva")

    # 3) Categoria com a área de destino e faixa horária válida agora
    holiday = is_holiday(now.date(), site_id, holidays)
    br_dow = (now.weekday() + 1) % 7  # 0=domingo ... 6=sábado
    hhmm = now.strftime("%H:%M")
    matched = None
    area_cfg = None
    for c in categories:
        for cfg in c.get("access_areas", []):
            if cfg.get("area_id") == dest_area.get("id"):
                if time_range_valid(tr_by_id.get(cfg.get("time_range_id")), br_dow, hhmm, holiday):
                    matched, area_cfg = c, cfg
                    break
        if matched:
            break
    if not matched:
        has_area = any(cfg.get("area_id") == dest_area.get("id")
                       for c in categories for cfg in c.get("access_areas", []))
        if has_area:
            add(False, "Nenhuma faixa horária válida neste momento para a área")
            return deny("Fora da faixa horária")
        add(False, "Pessoa sem permissão para a área de destino")
        return deny("Sem permissão para a área")
    add(True, f"Categoria '{matched.get('code')}' libera '{dest_area.get('description')}' agora")

    # 5) Regras da categoria
    if matched.get("control_origin"):
        if person.get("current_area_id") != ap.get("origin_area_id"):
            add(False, "Pessoa não está registrada na área de origem do ponto")
            return deny("Origem inválida")
        add(True, "Origem de acesso válida")
    if matched.get("control_anti_double") or dest_area.get("anti_double_entry"):
        if person.get("current_area_id") == dest_area.get("id"):
            add(False, "Pessoa já consta dentro da área de destino")
            return deny("Anti-dupla entrada")
        add(True, "Anti-dupla entrada OK")
    if matched.get("reentry_timed") and matched.get("reentry_minutes", 0) > 0:
        mins = matched["reentry_minutes"]
        last_exit = None
        for e in (recent_events or []):
            if e.get("direction") == "saida" and e.get("access_result") == "granted":
                last_exit = _parse(e.get("timestamp"))
                break
        if last_exit:
            delta = (now - last_exit).total_seconds() / 60.0
            if delta < mins:
                add(False, f"Reentrada em {delta:.0f}min < mínimo {mins}min")
                return deny("Reentrada temporizada")
        add(True, "Reentrada temporizada OK")

    escort = bool(matched.get("require_escort_unconditional") or (area_cfg or {}).get("require_escort"))

    # 6) Lotação máxima da área de destino
    maxo = dest_area.get("max_occupancy", 0) or 0
    if maxo > 0 and not dest_area.get("is_exterior") and dest_area.get("current_occupancy", 0) >= maxo:
        add(False, f"Lotação {dest_area.get('current_occupancy', 0)}/{maxo}")
        return deny("Lotação máxima")
    if maxo:
        add(True, f"Lotação {dest_area.get('current_occupancy', 0)}/{maxo} OK")

    add(True, "Acesso liberado")
    return {"granted": True, "reason": "Acesso liberado", "steps": steps,
            "escort_required": escort, "category_code": matched.get("code")}

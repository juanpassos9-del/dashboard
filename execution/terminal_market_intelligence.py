"""Deterministic provenance and context helpers for the Trading Terminal."""

from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any
from zoneinfo import ZoneInfo


EXCEL_ERROR_SENTINELS = {-2146826246}
RTD_RECEIVE_STALE_SECONDS = 15
QUOTE_AGE_LIMITS = {"fx": 600, "equity": 600, "di": 1800, "treasury": 3600, "commodity": 900, "other": 900}


def _parse_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo("America/Sao_Paulo"))
    return parsed.astimezone(timezone.utc)


def _is_excel_error(value: Any) -> bool:
    if isinstance(value, str) and value.strip().upper() in {"#N/A", "#VALUE!", "#REF!", "#DIV/0!", "N/A"}:
        return True
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return False
    return math.isfinite(number) and number in EXCEL_ERROR_SENTINELS


def _finite_number(value: Any) -> float | None:
    if _is_excel_error(value):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def rtd_number(value: Any, *, positive: bool = False) -> float | None:
    """Convert RTD values safely, rejecting Excel error sentinels."""
    number = _finite_number(value)
    if number is None or (positive and number <= 0):
        return None
    return number


def rtd_text(value: Any, fallback: str = "indisponível") -> str:
    if value is None or _is_excel_error(value):
        return fallback
    text = str(value).strip()
    return text if text and text != "---" else fallback


def audit_rtd_payload(payload: Any, now: datetime | None = None) -> dict[str, Any]:
    """Separate bridge liveness from market-tick freshness and reject Excel errors."""
    data = payload[0] if isinstance(payload, list) and payload else payload
    if not isinstance(data, dict):
        return {
            "available": False,
            "state": "missing",
            "warnings": ["Feed RTD indisponível."],
            "invalid_fields": [],
            "bridge_age_seconds": None,
        }

    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)
    received_at = _parse_timestamp(data.get("updated_at"))
    bridge_age = max(0.0, (now - received_at).total_seconds()) if received_at else None

    numeric_fields = ("last_price", "vwap", "adjustment", "change_percent", "saldo_agressao")
    invalid_fields = [key for key in numeric_fields if _is_excel_error(data.get(key))]
    for key in ("last_price", "vwap", "adjustment"):
        number = _finite_number(data.get(key))
        if data.get(key) is not None and number is not None and number <= 0:
            invalid_fields.append(key)

    market_timestamp = _parse_timestamp(data.get("market_timestamp") or data.get("source_timestamp"))
    valid_values = {
        key: rtd_number(data.get(key), positive=key in {"last_price", "vwap", "adjustment"})
        for key in numeric_fields
    }
    semaforo = data.get("semaforo") if isinstance(data.get("semaforo"), dict) else {}
    invalid_fields.extend(f"semaforo.{key}" for key, value in semaforo.items() if _is_excel_error(value))
    warnings = []
    if not received_at:
        warnings.append("Horário de recepção do bridge ausente ou inválido.")
    elif bridge_age is not None and bridge_age > RTD_RECEIVE_STALE_SECONDS:
        warnings.append(f"Bridge sem atualização há {int(bridge_age)}s.")
    if not market_timestamp:
        warnings.append("O payload não informa o horário do último negócio; idade de mercado desconhecida.")
    if invalid_fields:
        warnings.append("O Excel enviou campo(s) inválido(s): " + ", ".join(sorted(set(invalid_fields))) + ".")

    state = "unknown" if bridge_age is None else "stale" if bridge_age > RTD_RECEIVE_STALE_SECONDS else "fresh"
    if invalid_fields:
        state = "invalid"
    return {
        "available": True,
        "state": state,
        "symbol": str(data.get("symbol") or "---"),
        "received_at": received_at.isoformat() if received_at else None,
        "bridge_age_seconds": bridge_age,
        "market_timestamp": market_timestamp.isoformat() if market_timestamp else None,
        "market_age_seconds": max(0.0, (now - market_timestamp).total_seconds()) if market_timestamp else None,
        "source": "ProfitChart RTD / Excel via dashboard_bridge → Supabase app_state",
        "change_basis": data.get("change_basis") or "não informada pelo Excel (campo L12)",
        "invalid_fields": sorted(set(invalid_fields)),
        "valid_values": valid_values,
        "warnings": warnings,
        "data": data,
    }


def format_age(seconds: float | None) -> str:
    if seconds is None:
        return "idade desconhecida"
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}min"
    return f"{seconds // 3600}h {(seconds % 3600) // 60}min"


def age_seconds_since(timestamp: Any, now: datetime | None = None) -> float | None:
    parsed = _parse_timestamp(timestamp)
    if not parsed:
        return None
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return max(0.0, (now.astimezone(timezone.utc) - parsed).total_seconds())


def assess_market_quote(item: dict[str, Any] | None, now: datetime, snapshot_age_seconds: float | None = None) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {"state": "missing", "age_seconds": None, "timestamp": None}
    observed = _parse_timestamp(item.get("source_timestamp"))
    if item.get("timestamp_type") == "retrieved_at":
        delay = _finite_number(item.get("market_delay_seconds"))
        age = delay if delay is not None else None
    elif observed:
        age = max(0.0, (now - observed).total_seconds())
    else:
        base_age = _finite_number(item.get("age_seconds"))
        age = base_age + max(0.0, snapshot_age_seconds or 0.0) if base_age is not None else None
    try:
        limit = float(item.get("max_age_seconds") or QUOTE_AGE_LIMITS.get(str(item.get("quote_class") or "other"), 900))
    except (TypeError, ValueError):
        limit = 900.0
    state = "unknown" if age is None else "stale" if age > limit else "fresh"
    return {"state": state, "age_seconds": age, "timestamp": observed.isoformat() if observed else None}


def build_terminal_market_brief(
    global_data: dict[str, Any] | None,
    di_regime: dict[str, Any] | None,
    rtd_audit: dict[str, Any] | None,
    flow_data: dict[str, Any] | None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Summarize only supplied observations; this is context, never a trade signal."""
    categories = (global_data or {}).get("categories", global_data or {})
    assets: dict[str, dict[str, Any]] = {}
    if isinstance(categories, dict):
        for rows in categories.values():
            if not isinstance(rows, list):
                continue
            for row in rows:
                if isinstance(row, dict):
                    for key in (row.get("symbol"), row.get("name"), row.get("source_symbol")):
                        if key:
                            assets[str(key).strip().upper()] = row

    def pick(*names: str) -> dict[str, Any] | None:
        for name in names:
            if name.upper() in assets:
                return assets[name.upper()]
        return None

    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)
    metadata = (global_data or {}).get("metadata") or {}
    snapshot_timestamp = _parse_timestamp(metadata.get("generated_at_utc") or metadata.get("full_timestamp"))
    snapshot_age = max(0.0, (now - snapshot_timestamp).total_seconds()) if snapshot_timestamp else None
    snapshot_state = "unknown" if snapshot_age is None else "stale" if snapshot_age > 900 else "fresh"

    evidence: list[str] = []
    confirms: list[str] = []
    divergences: list[str] = []
    quality_notes: list[str] = []
    di_direction = None
    di_items = [pick("DI1F27"), pick("DI1F29"), pick("DI1F32")]
    di_qualities = [assess_market_quote(item, now, snapshot_age) for item in di_items]
    di_fresh = len(di_qualities) == 3 and all(item["state"] == "fresh" for item in di_qualities) and snapshot_state == "fresh"
    if snapshot_state != "fresh":
        quality_notes.append(f"Snapshot global {snapshot_state} ({format_age(snapshot_age)}); leituras cruzadas não são tratadas como simultâneas.")
    if di_qualities and not di_fresh:
        quality_notes.append("Curva DI incompleta, sem timestamp, ou fora da janela de frescor; sem confirmação intradiária pelo DI.")
    if di_regime:
        regime = str(di_regime.get("regime") or "DI sem classificação")
        avg_change = _finite_number(di_regime.get("avg_change"))
        if di_fresh and avg_change is not None and avg_change >= 0.20:
            di_direction = "abrindo"
            evidence.append(f"DI: {regime}; variação média dos contratos {avg_change:+.2f}% (dados do snapshot).")
        elif di_fresh and avg_change is not None and avg_change <= -0.20:
            di_direction = "fechando"
            evidence.append(f"DI: {regime}; variação média dos contratos {avg_change:+.2f}% (dados do snapshot).")
        else:
            evidence.append(f"DI: {regime}; direção não classificada como intradiária confiável por frescor insuficiente.")

    usdbrl = pick("BRL=X", "USDBRL", "USDBRL (COMERCIAL)")
    usd_change = _finite_number(usdbrl.get("change")) if usdbrl else None
    usd_quality = assess_market_quote(usdbrl, now, snapshot_age)
    if usd_change is not None:
        evidence.append(f"USD/BRL: {usd_change:+.2f}% vs. {usdbrl.get('change_basis') or 'base da fonte não especificada'}; dado {usd_quality['state']} ({format_age(usd_quality['age_seconds'])}).")
        if usd_quality["state"] != "fresh":
            quality_notes.append("USD/BRL não usado para confirmação por timestamp ausente ou cotação atrasada.")
        di_times = [
            _parse_timestamp(item.get("source_timestamp"))
            for item in di_items if isinstance(item, dict)
        ]
        valid_di_times = [value for value in di_times if value]
        usd_time = _parse_timestamp(usdbrl.get("source_timestamp")) if usdbrl else None
        time_skew = max([abs((value - usd_time).total_seconds()) for value in valid_di_times], default=None) if usd_time and len(valid_di_times) == 3 else None
        timestamps_aligned = time_skew is not None and time_skew <= 300
        comparable = di_fresh and usd_quality["state"] == "fresh" and timestamps_aligned
        if not timestamps_aligned:
            quality_notes.append("DI e USD/BRL não têm timestamps conhecidos alinhados em até 5 minutos; a comparação fica apenas descritiva.")
        if comparable and di_direction == "abrindo":
            (confirms if usd_change > 0.15 else divergences if usd_change < -0.15 else evidence).append(
                "Câmbio confirma pressão junto do DI." if usd_change > 0.15 else
                "Câmbio diverge: real se fortalece enquanto o DI abre." if usd_change < -0.15 else
                "Câmbio sem variação relevante contra o DI."
            )
        elif comparable and di_direction == "fechando":
            (confirms if usd_change < -0.15 else divergences if usd_change > 0.15 else evidence).append(
                "Câmbio confirma alívio junto do DI." if usd_change < -0.15 else
                "Câmbio diverge: real se enfraquece enquanto o DI fecha." if usd_change > 0.15 else
                "Câmbio sem variação relevante contra o DI."
            )

    for names, label in ((("^GSPC", "S&P 500"), "S&P 500"), (("DX-Y.NYB", "DXY"), "DXY"), (("BZ=F", "BRENT OIL"), "Brent")):
        item = pick(*names)
        change = _finite_number(item.get("change")) if item else None
        if change is not None:
            quality = assess_market_quote(item, now, snapshot_age)
            evidence.append(f"{label}: {change:+.2f}% no snapshot ({quality['state']}, {format_age(quality['age_seconds'])}), base {item.get('change_basis') or 'fonte não especificada'}.")

    flow_record = None
    records = (flow_data or {}).get("records") or []
    if isinstance(records, list) and records:
        flow_record = next((row for row in records if isinstance(row, dict) and _finite_number(row.get("foreigners")) is not None), None)
    if flow_record:
        flow_millions = _finite_number(flow_record.get("foreigners")) / 1000
        evidence.append(f"Fluxo estrangeiro B3: R$ {flow_millions:+,.1f} mi em {flow_record.get('date', 'data sem registro')} (série diária; não é intradiária).".replace(",", "X").replace(".", ",").replace("X", "."))
        quality_notes.append("Fluxo estrangeiro é diário; mantido como contexto e excluído das confirmações intradiárias por diferença de janela.")

    semaforo = ((rtd_audit or {}).get("data") or {}).get("semaforo") or {}
    direction = str(semaforo.get("direcao") or "").strip()
    rtd_fresh_for_cross = bool(
        (rtd_audit or {}).get("state") == "fresh"
        and (rtd_audit or {}).get("market_timestamp")
        and (rtd_audit or {}).get("market_age_seconds") is not None
        and (rtd_audit or {}).get("market_age_seconds") <= 15
    )
    if direction and direction not in {"---", "-2146826246"} and not rtd_fresh_for_cross:
        quality_notes.append("Semáforo RTD não comparado com DI: falta timestamp de mercado sincronizável ou o feed está atrasado.")
    if direction and direction not in {"---", "-2146826246"}:
        evidence.append(f"RTD: semáforo do Excel reporta ‘{direction}’; fórmula original não acompanha o payload.")
        if rtd_fresh_for_cross and di_fresh and di_direction == "abrindo" and any(word in direction.upper() for word in ("COMPRA", "COMPRAR", "COMPRADO")):
            divergences.append("Semáforo RTD comprador diverge do DI abrindo; são medidas independentes.")
        elif rtd_fresh_for_cross and di_fresh and di_direction == "fechando" and any(word in direction.upper() for word in ("VENDA", "VENDER", "VENDIDO")):
            divergences.append("Semáforo RTD vendedor diverge do DI fechando; são medidas independentes.")

    if not evidence:
        return {"available": False, "evidence": [], "confirms": [], "divergences": [], "quality_notes": quality_notes, "headline": "Aguardando dados para compor a leitura."}
    headline = "Leitura mista / sem confirmação suficiente"
    if di_fresh and di_direction == "abrindo":
        headline = "Prêmio de juros no Brasil em alta; confirmação intermercado parcial"
    elif di_fresh and di_direction == "fechando":
        headline = "Alívio na curva de juros brasileira; confirmação intermercado parcial"
    elif not di_regime:
        headline = "Contexto global disponível; leitura de DI aguardando dados"
    return {
        "available": True,
        "headline": headline,
        "evidence": evidence,
        "confirms": confirms,
        "divergences": divergences,
        "quality_notes": quality_notes,
        "caveat": "Leitura descritiva e determinística, não é recomendação nem sinal automático de operação.",
    }

import json
import math
import os
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from execution.gemini_client import generate_gemini_text
from execution.market_data_engine import FRESHNESS_LIMITS_SECONDS, quote_age_seconds
from execution.terminal_market_intelligence import audit_rtd_payload, format_age, rtd_number, rtd_text
from execution.yield_curve_regime import analyze_yield_curve_regime

load_dotenv()

FALLBACK_BLOCK_WEIGHTS = {
    "equities": 20,
    "volatility": 15,
    "rates": 20,
    "dollar": 15,
    "em_brazil": 20,
    "risk_appetite": 10,
}

FALLBACK_SIGNAL_THRESHOLDS = {
    "sp500": 0.15, "nasdaq": 0.15, "dow": 0.15,
    "vix": 0.25, "dxy": 0.12,
    "us02y": 0.08, "us10y": 0.08, "us30y": 0.08,
    "eem": 0.15, "ewz": 0.15, "usbrl": 0.15, "real_cme": 0.10,
    "brent": 0.30, "wti": 0.30, "gold": 0.25, "bitcoin": 0.50, "ibov": 0.15,
}
FALLBACK_HORIZON_WEIGHTS = {"1 dia": 0.50, "5 pregoes": 0.30, "20 pregoes": 0.20}
FALLBACK_HISTORY_KEY = "macro_fallback_market_history"
FALLBACK_HISTORY_SAMPLE_INTERVAL = timedelta(hours=4)
FALLBACK_HISTORY_RETENTION = timedelta(days=35)


def _load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list) and len(data) == 1 and isinstance(data[0], dict):
            return data[0]
        return data
    except Exception:
        return default


def _load_macro_inputs(dashboard_inputs=None):
    keys = {
        "dados_mercado": ("dados_mercado.json", {}),
        "mercados_globais": ("mercados_globais.json", {}),
        "calendario_economico": ("calendario_economico.json", []),
    }
    state = {}
    client = None
    try:
        from execution.app_state_sync import get_service_client

        client = get_service_client()
        response = (
            client
            .table("app_state")
            .select("key,value")
            .in_("key", [*keys, FALLBACK_HISTORY_KEY])
            .execute()
        )
        state = {row.get("key"): row.get("value") for row in response.data or []}
    except Exception as error:
        print(f"[WARN] Snapshot Supabase indisponivel para Analista IA: {error}")

    inputs = {
        key: state.get(key) if state.get(key) is not None else _load_json(path, default)
        for key, (path, default) in keys.items()
    }
    for key, value in (dashboard_inputs or {}).items():
        if key in keys and value is not None:
            inputs[key] = value
    inputs[FALLBACK_HISTORY_KEY] = state.get(FALLBACK_HISTORY_KEY) or {"samples": []}
    return inputs, client


def _dashboard_rtd_context(local_data, now):
    audit = audit_rtd_payload(local_data, now=now)
    if not audit.get("available"):
        return {"available": False, "state": "missing", "evidence": []}

    data = audit.get("data") or {}
    market_age = audit.get("market_age_seconds")
    bridge_age = audit.get("bridge_age_seconds")
    state = audit.get("state", "unknown")
    if market_age is None:
        market_state = "horario de mercado desconhecido"
    elif market_age <= 15 and state == "fresh":
        market_state = "negocio recente"
    else:
        market_state = f"negocio possivelmente atrasado ({format_age(market_age)})"

    details = []
    price = rtd_number(data.get("last_price"), positive=True)
    change = rtd_number(data.get("change_percent"))
    aggression = rtd_number(data.get("saldo_agressao"))
    if price is not None:
        details.append(f"preco {price:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    if change is not None:
        details.append(f"variacao {change:+.2f}%")
    if aggression is not None:
        details.append(f"saldo de agressao {aggression:+,.0f}".replace(",", "."))
    semaforo = data.get("semaforo") if isinstance(data.get("semaforo"), dict) else {}
    direction = rtd_text(semaforo.get("direcao"), "")
    if direction:
        details.append(f"semaforo {direction}")

    symbol = rtd_text(data.get("symbol"), "ativo RTD")
    received = f"bridge recebeu ha {format_age(bridge_age)}" if bridge_age is not None else "recepcao sem horario"
    evidence = [f"{symbol}: {', '.join(details) or 'sem campos numericos validos'}; {market_state}; {received}."]
    evidence.extend(audit.get("warnings") or [])
    return {
        "available": True,
        "state": state,
        "symbol": symbol,
        "market_timestamp": audit.get("market_timestamp"),
        "market_age_seconds": market_age,
        "bridge_age_seconds": bridge_age,
        "evidence": evidence[:3],
        "usable_for_confirmation": state == "fresh" and market_age is not None and market_age <= 15,
    }


def _macro_snapshot_needs_refresh(context):
    quality = context.get("data_quality", {})
    age = context.get("market_snapshot_age_seconds")
    return quality.get("coverage_pct", 0) < 60 or age is None or age > 10 * 60


def _refresh_macro_dashboard_snapshot(market_inputs, client, context):
    status = {"attempted": False, "succeeded": False, "error": None}
    if not _macro_snapshot_needs_refresh(context):
        return market_inputs.get("mercados_globais"), status

    status["attempted"] = True
    try:
        from execution.market_data_engine import collect_and_publish_market_snapshot

        snapshot = collect_and_publish_market_snapshot(client)
        if snapshot:
            market_inputs["mercados_globais"] = snapshot
            status["succeeded"] = True
            return snapshot, status
    except Exception as error:
        status["error"] = str(error)
        print(f"[WARN] Atualizacao sob demanda do snapshot falhou; usando o snapshot atual do dashboard: {error}")
    return market_inputs.get("mercados_globais"), status


def append_macro_market_snapshot(history, quotes, now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)
    current = history if isinstance(history, dict) else {"samples": []}
    samples = current.get("samples") if isinstance(current.get("samples"), list) else []
    valid_quotes = {
        key: value for key, value in (quotes or {}).items()
        if isinstance(value, dict) and value.get("price") is not None
    }
    if not valid_quotes:
        return current, False

    latest = samples[-1] if samples and isinstance(samples[-1], dict) else {}
    try:
        latest_time = datetime.fromisoformat(str(latest.get("timestamp", "")).replace("Z", "+00:00"))
        if latest_time.tzinfo is None:
            latest_time = latest_time.replace(tzinfo=timezone.utc)
        latest_time = latest_time.astimezone(timezone.utc)
        if now - latest_time < FALLBACK_HISTORY_SAMPLE_INTERVAL or latest.get("quotes") == valid_quotes:
            return current, False
    except (TypeError, ValueError):
        pass

    sample = {"timestamp": now.isoformat(timespec="seconds"), "quotes": valid_quotes}
    cutoff = now - FALLBACK_HISTORY_RETENTION
    retained = []
    for item in samples:
        try:
            sample_time = datetime.fromisoformat(str(item.get("timestamp", "")).replace("Z", "+00:00"))
            if sample_time.tzinfo is None:
                sample_time = sample_time.replace(tzinfo=timezone.utc)
            if sample_time.astimezone(timezone.utc) >= cutoff:
                retained.append(item)
        except (AttributeError, TypeError, ValueError):
            continue
    retained.append(sample)
    return {"schema_version": 1, "updated_at": now.isoformat(timespec="seconds"), "samples": retained[-240:]}, True


def _flatten_assets(global_data):
    categories = global_data.get("categories", global_data) if isinstance(global_data, dict) else {}
    assets = []
    if isinstance(categories, dict):
        for items in categories.values():
            if isinstance(items, list):
                assets.extend([item for item in items if isinstance(item, dict)])
    return assets


def _find_asset(global_data, *terms):
    terms = [term.lower() for term in terms]
    for item in _flatten_assets(global_data):
        name = str(item.get("name", "")).lower()
        symbol = str(item.get("symbol", "")).lower()
        if any(term in name or term in symbol for term in terms):
            return item
    return {}


def _change(item):
    try:
        value = float(item.get("change"))
        return value if math.isfinite(value) else None
    except Exception:
        return None


def _price(item):
    try:
        return float(item.get("price"))
    except Exception:
        return None


def _session_open(now, session):
    zones = {
        "us_equity": ("America/New_York", time(9, 30), time(16, 0)),
        "br_equity": ("America/Sao_Paulo", time(10, 0), time(17, 0)),
        "treasury": ("America/New_York", time(7, 0), time(17, 30)),
        "commodity": ("America/New_York", time(18, 0), time(17, 0)),
    }
    if session == "crypto":
        return True
    if session == "fx":
        local = now.astimezone(ZoneInfo("America/New_York"))
        if local.weekday() == 6:
            return local.time() >= time(17)
        if local.weekday() == 5:
            return local.time() < time(17)
        return True
    zone, start, end = zones[session]
    local = now.astimezone(ZoneInfo(zone))
    if local.weekday() >= 5:
        return False
    if session == "commodity":
        return local.time() >= start or local.time() < end
    return start <= local.time() < end


def _quote_status(item, quote_class, session, now):
    if not item:
        return "missing", None
    age = quote_age_seconds(item, now)
    if age is None:
        return "unknown", None
    if age <= FRESHNESS_LIMITS_SECONDS[quote_class]:
        return "fresh", age
    if not _session_open(now, session):
        closed_grace = 72 * 60 * 60 if quote_class != "fx" else 48 * 60 * 60
        if age <= closed_grace:
            return "last_close", age
    return "stale", age


def _age_text(age_seconds):
    if age_seconds is None:
        return "idade desconhecida"
    minutes = int(age_seconds // 60)
    if minutes < 1:
        return "agora"
    if minutes < 60:
        return f"ha {minutes} min"
    hours = minutes // 60
    if hours < 24:
        return f"ha {hours} h"
    return f"ha {hours // 24} d"


def _move_score(value, threshold, positive_when_up):
    if abs(value) <= threshold:
        return 0.0
    excess = min(1.0, (abs(value) - threshold) / threshold)
    return math.copysign(excess, value) * (1 if positive_when_up else -1)


def _change_signal(item, label, positive_when_up, threshold, quote_class, session, now):
    status, age = _quote_status(item, quote_class, session, now)
    value = _change(item)
    if status not in {"fresh", "last_close"} or value is None:
        return {"score": None, "status": status, "age_seconds": age, "evidence": None}

    realized_vol = item.get("daily_volatility_pct") or item.get("volatility_20d_pct")
    try:
        realized_vol = float(realized_vol)
        if math.isfinite(realized_vol) and realized_vol > 0:
            threshold = max(threshold, realized_vol * 0.5)
    except (TypeError, ValueError, OverflowError):
        pass

    score = _move_score(value, threshold, positive_when_up)
    direction = (
        "neutro" if score == 0 else
        "favoravel ao risco" if score > 0 else
        "desfavoravel ao risco"
    )

    name = item.get("name") or label
    source = item.get("source") or "fonte nao identificada"
    close_note = " (ultimo fechamento; sessao encerrada)" if status == "last_close" else ""
    evidence = f"{name} {value:+.2f}% no dia, {source}, {_age_text(age)}{close_note}: {direction}"
    return {"score": score, "status": status, "age_seconds": age, "evidence": evidence, "value": value}


def _mean_score(signals):
    values = [item["score"] for item in signals if item["score"] is not None]
    return sum(values) / len(values) if values else None


def _calendar_events(calendar_data, now):
    if isinstance(calendar_data, dict):
        events = calendar_data.get("events") or calendar_data.get("value") or []
    else:
        events = calendar_data if isinstance(calendar_data, list) else []
    today = now.astimezone(ZoneInfo("America/Sao_Paulo")).date()
    result = []
    dated_events = []
    for event in events:
        if not isinstance(event, dict) or str(event.get("impact", "")).upper() not in {"HIGH", "MEDIUM"}:
            continue
        raw_date = event.get("date") or event.get("timestamp") or event.get("datetime")
        try:
            event_date = datetime.fromisoformat(str(raw_date).replace("Z", "+00:00")).date()
        except (TypeError, ValueError):
            try:
                event_date = datetime.strptime(str(raw_date), "%Y-%m-%d").date()
            except (TypeError, ValueError):
                continue
        dated_events.append(event_date)
        if today <= event_date <= today.fromordinal(today.toordinal() + 1):
            actual = str(event.get("actual") or "").strip()
            forecast = str(event.get("forecast") or "").strip()
            previous = str(event.get("previous") or "").strip()
            state = "divulgado" if actual and actual not in {"-", "---"} else "a divulgar"
            result.append(
                f"{event.get('date', event_date.isoformat())} {event.get('time', '--:--')} "
                f"{event.get('currency', '')} {event.get('impact')}: {event.get('event', 'evento')} "
                f"({state}; atual {actual or '—'}, projecao {forecast or '—'}, anterior {previous or '—'})"
            )
    result.sort()
    stale = bool(dated_events) and max(dated_events) < today
    return result[:6], stale


def _optional_horizons(assets):
    fields = {
        "5 dias": ("change_5d", "change_1w", "return_5d_pct", "weekly_change_pct"),
        "20 dias": ("change_20d", "change_1m", "return_20d_pct", "monthly_change_pct"),
    }
    summaries = []
    for horizon, candidates in fields.items():
        values = []
        for label, item in assets.items():
            if not item:
                continue
            value = next((item.get(key) for key in candidates if item.get(key) is not None), None)
            try:
                value = float(value)
                if math.isfinite(value):
                    values.append((label, value))
            except (TypeError, ValueError, OverflowError):
                continue
        if values:
            values.sort(key=lambda pair: abs(pair[1]), reverse=True)
            summaries.append(f"{horizon}: " + ", ".join(f"{name} {value:+.2f}%" for name, value in values[:3]))
    return summaries


def _historical_horizon_scores(history, current_quotes, now):
    samples = history.get("samples", []) if isinstance(history, dict) else []
    parsed_samples = []
    for sample in samples if isinstance(samples, list) else []:
        try:
            timestamp = datetime.fromisoformat(str(sample["timestamp"]).replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            parsed_samples.append((timestamp.astimezone(timezone.utc), sample.get("quotes", {})))
        except (KeyError, TypeError, ValueError):
            continue

    horizons = {}
    for label, days, tolerance in (("5 pregoes", 7, timedelta(days=2)), ("20 pregoes", 28, timedelta(days=4))):
        target = now - timedelta(days=days)
        moves = {}
        for key, current in (current_quotes or {}).items():
            try:
                current_price = float(current["price"])
                candidates = [
                    (abs((timestamp - target).total_seconds()), quotes.get(key))
                    for timestamp, quotes in parsed_samples
                    if timestamp < now and timestamp <= target + tolerance
                ]
                candidates = [(distance, row) for distance, row in candidates if isinstance(row, dict)]
                if not candidates:
                    continue
                distance, reference = min(candidates, key=lambda pair: pair[0])
                if distance > tolerance.total_seconds():
                    continue
                reference_price = float(reference["price"])
                if reference_price <= 0 or not math.isfinite(current_price):
                    continue
                moves[key] = (current_price / reference_price - 1.0) * 100.0
            except (KeyError, TypeError, ValueError, OverflowError):
                continue

        score_by_asset = {
            key: _move_score(value, FALLBACK_SIGNAL_THRESHOLDS[key], positive_when_up)
            for key, value in moves.items()
            for positive_when_up in (key not in {"vix", "dxy", "usbrl"},)
            if key in FALLBACK_SIGNAL_THRESHOLDS
        }
        em_groups = []
        if "eem" in score_by_asset:
            em_groups.append(score_by_asset["eem"])
        brazil_equity = _mean_values(score_by_asset, ("ewz", "ibov"))
        currency = _mean_values(score_by_asset, ("usbrl", "real_cme"))
        if brazil_equity is not None:
            em_groups.append(brazil_equity)
        if currency is not None:
            em_groups.append(currency)
        groups = {
            "equities": _mean_values(score_by_asset, ("sp500", "nasdaq", "dow")),
            "volatility": score_by_asset.get("vix"),
            "dollar": score_by_asset.get("dxy"),
            "em_brazil": sum(em_groups) / len(em_groups) if em_groups else None,
            "risk_appetite": score_by_asset.get("bitcoin"),
        }
        covered = [(FALLBACK_BLOCK_WEIGHTS[key], value) for key, value in groups.items() if value is not None]
        coverage_weight = sum(weight for weight, _ in covered)
        horizon_score = (
            round(sum(weight * value for weight, value in covered) / coverage_weight * 100, 1)
            if coverage_weight >= 40 else None
        )
        leaders = sorted(moves.items(), key=lambda item: abs(item[1]), reverse=True)[:3]
        horizons[label] = {
            "score": horizon_score,
            "coverage_pct": coverage_weight,
            "evidence": ", ".join(f"{key} {value:+.2f}%" for key, value in leaders),
        }
    return horizons


def _mean_values(values, keys):
    available = [values[key] for key in keys if key in values]
    return sum(available) / len(available) if available else None


def build_macro_regime_context(local_data, global_data, calendar_data, now=None, market_history=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)
    rtd_context = _dashboard_rtd_context(local_data, now)
    metadata = global_data.get("metadata") if isinstance(global_data, dict) else {}
    snapshot_timestamp = (metadata or {}).get("generated_at_utc") or (metadata or {}).get("full_timestamp")
    try:
        parsed_snapshot_timestamp = datetime.fromisoformat(str(snapshot_timestamp).replace("Z", "+00:00"))
        if parsed_snapshot_timestamp.tzinfo is None:
            parsed_snapshot_timestamp = parsed_snapshot_timestamp.replace(tzinfo=timezone.utc)
        snapshot_age_seconds = max(0.0, (now - parsed_snapshot_timestamp.astimezone(timezone.utc)).total_seconds())
    except (TypeError, ValueError):
        parsed_snapshot_timestamp = None
        snapshot_age_seconds = None
    assets = {
        "sp500": _find_asset(global_data, "s&p 500", "sp 500", "^gspc", "spy", "usa500"),
        "nasdaq": _find_asset(global_data, "nasdaq", "^ixic", "usatec"),
        "dow": _find_asset(global_data, "dow", "djia", "^dji"),
        "vix": _find_asset(global_data, "vix", "^vix", "vxx"),
        "dxy": _find_asset(global_data, "dxy", "dolar index", "dollar index", "dx-y"),
        "us02y": _find_asset(global_data, "us 02y", "us 2y", "us02y", "dgs2", "2yy=f"),
        "us10y": _find_asset(global_data, "us 10y", "us10y", "^tnx"),
        "us30y": _find_asset(global_data, "us 30y", "us30y", "^tyx"),
        "eem": _find_asset(global_data, "eem", "emerging"),
        "ewz": _find_asset(global_data, "ewz", "brazil etf"),
        "usbrl": _find_asset(global_data, "usdbrl", "brl=x"),
        "real_cme": _find_asset(global_data, "6l", "real cme"),
        "brent": _find_asset(global_data, "brent", "ukoil"),
        "wti": _find_asset(global_data, "wti", "crude oil"),
        "gold": _find_asset(global_data, "gold", "ouro", "xau"),
        "bitcoin": _find_asset(global_data, "bitcoin", "btc"),
        "ibov": _find_asset(global_data, "ibov", "bovespa", "^bvsp"),
    }
    specs = {
        "sp500": ("S&P 500", True, "equity", "us_equity"),
        "nasdaq": ("Nasdaq", True, "equity", "us_equity"),
        "dow": ("Dow Jones", True, "equity", "us_equity"),
        "vix": ("VIX", False, "other", "us_equity"),
        "dxy": ("DXY", False, "fx", "fx"),
        "us02y": ("US02Y", False, "treasury", "treasury"),
        "us10y": ("US10Y", False, "treasury", "treasury"),
        "us30y": ("US30Y", False, "treasury", "treasury"),
        "eem": ("EEM", True, "equity", "us_equity"),
        "ewz": ("EWZ", True, "equity", "us_equity"),
        "usbrl": ("USDBRL", False, "fx", "fx"),
        "real_cme": ("6L Real CME", True, "other", "commodity"),
        "brent": ("Brent", True, "commodity", "commodity"),
        "wti": ("WTI", True, "commodity", "commodity"),
        "gold": ("Ouro", True, "commodity", "commodity"),
        "bitcoin": ("Bitcoin", True, "crypto", "crypto"),
        "ibov": ("IBOV", True, "equity", "br_equity"),
    }
    observations = {
        key: _change_signal(
            item,
            specs[key][0],
            specs[key][1],
            FALLBACK_SIGNAL_THRESHOLDS[key],
            specs[key][2],
            specs[key][3],
            now,
        )
        for key, item in assets.items()
    }

    usable_ids = {
        id(assets[key])
        for key, observation in observations.items()
        if assets[key] and observation["status"] in {"fresh", "last_close"}
    }
    filtered_global = {"categories": {}}
    categories = global_data.get("categories", global_data) if isinstance(global_data, dict) else {}
    if isinstance(categories, dict):
        filtered_global["categories"] = {
            category: [item for item in rows if isinstance(item, dict) and id(item) in usable_ids]
            for category, rows in categories.items()
            if isinstance(rows, list)
        }

    rate_count = sum(
        observations[key]["score"] is not None
        for key in ("us02y", "us10y", "us30y")
    )
    curve = analyze_yield_curve_regime(filtered_global, include_fred=False) if rate_count >= 2 else {}

    equity_score = _mean_score([observations[key] for key in ("sp500", "nasdaq", "dow")])
    vix_score = observations["vix"]["score"]
    dxy_score = observations["dxy"]["score"]
    rate_regime = curve.get("regime", "Dados insuficientes")
    curve_signal = {
        "Bear Flattening": -0.75,
        "Parallel Up": -0.50,
        "Bull Flattening": 0.50 if (dxy_score or 0) >= 0 and (vix_score or 0) >= 0 else 0.0,
        "Parallel Down": 0.50 if (dxy_score or 0) > 0 and (vix_score or 0) > 0 else 0.0,
    }.get(rate_regime, 0.0)
    rates_valid = [observations[key] for key in ("us02y", "us10y", "us30y") if observations[key]["score"] is not None]
    rates_coverage = min(1.0, len(rates_valid) / 2.0)
    rates_score = curve_signal if rates_valid else None

    em_basket = observations["eem"]["score"]
    brazil_equity_basket = _mean_score([observations[key] for key in ("ewz", "ibov")])
    currency_basket = _mean_score([observations[key] for key in ("usbrl", "real_cme")])
    em_components = [score for score in (em_basket, brazil_equity_basket, currency_basket) if score is not None]
    em_score = sum(em_components) / len(em_components) if em_components else None
    em_equity_count = sum(observations[key]["score"] is not None for key in ("eem", "ewz", "ibov"))
    em_fx_count = sum(observations[key]["score"] is not None for key in ("usbrl", "real_cme"))
    em_coverage = (min(1.0, em_equity_count / 2.0) + min(1.0, em_fx_count / 2.0)) / 2.0
    risk_appetite_score = observations["bitcoin"]["score"]

    blocks = [
        {"key": "equities", "label": "Acoes EUA", "weight": FALLBACK_BLOCK_WEIGHTS["equities"], "score": equity_score, "coverage": min(1.0, sum(observations[k]["score"] is not None for k in ("sp500", "nasdaq", "dow")) / 2.0)},
        {"key": "volatility", "label": "Volatilidade", "weight": FALLBACK_BLOCK_WEIGHTS["volatility"], "score": vix_score, "coverage": 1.0 if vix_score is not None else 0.0},
        {"key": "rates", "label": "Juros/curva", "weight": FALLBACK_BLOCK_WEIGHTS["rates"], "score": rates_score, "coverage": rates_coverage},
        {"key": "dollar", "label": "Dolar global", "weight": FALLBACK_BLOCK_WEIGHTS["dollar"], "score": dxy_score, "coverage": 1.0 if dxy_score is not None else 0.0},
        {"key": "em_brazil", "label": "Emergentes/Brasil", "weight": FALLBACK_BLOCK_WEIGHTS["em_brazil"], "score": em_score, "coverage": em_coverage},
        {"key": "risk_appetite", "label": "Apetite a risco", "weight": FALLBACK_BLOCK_WEIGHTS["risk_appetite"], "score": risk_appetite_score, "coverage": 1.0 if risk_appetite_score is not None else 0.0},
    ]
    daily_score = round(sum(block["weight"] * block["score"] for block in blocks if block["score"] is not None), 1)
    history_quotes = {}
    for key, item in assets.items():
        price = _price(item)
        if item and price is not None and observations[key]["status"] in {"fresh", "last_close"}:
            history_quotes[key] = {"price": price, "source_timestamp": item.get("source_timestamp")}

    historical_scores = _historical_horizon_scores(market_history or {}, history_quotes, now)
    score_horizons = {"1 dia": daily_score}
    score_horizons.update({label: item["score"] for label, item in historical_scores.items()})
    available_horizons = [
        (FALLBACK_HORIZON_WEIGHTS[label], value)
        for label, value in score_horizons.items()
        if value is not None
    ]
    score = round(
        sum(weight * value for weight, value in available_horizons) / sum(weight for weight, _ in available_horizons),
        1,
    ) if available_horizons else 0.0
    history_conflicts = [
        f"Horizonte {label} contradiz o sinal diario ({value:+.1f} vs {daily_score:+.1f})."
        for label, value in score_horizons.items()
        if label != "1 dia" and value is not None and value * daily_score < 0 and abs(value) >= 15 and abs(daily_score) >= 15
    ]
    coverage_pct = round(sum(block["weight"] * block["coverage"] for block in blocks), 1)
    available_blocks = [block for block in blocks if block["coverage"] > 0]
    positive_weight = sum(block["weight"] for block in available_blocks if (block["score"] or 0) > 0.15)
    negative_weight = sum(block["weight"] for block in available_blocks if (block["score"] or 0) < -0.15)
    directional_weight = positive_weight + negative_weight
    alignment = max(positive_weight, negative_weight) / directional_weight if directional_weight else 1.0
    if history_conflicts:
        alignment = min(alignment, 0.55)

    if coverage_pct >= 80 and len(available_blocks) >= 4 and alignment >= 0.70:
        confidence = "Alta"
    elif coverage_pct >= 60 and len(available_blocks) >= 3 and alignment >= 0.60:
        confidence = "Media"
    else:
        confidence = "Baixa"

    if coverage_pct < 40 or len(available_blocks) < 2:
        regime, sentiment_hint = "Dados insuficientes", "NEUTRO"
    elif score >= 35 and coverage_pct >= 80:
        regime, sentiment_hint = "Risk-on forte", "COMPRA"
    elif score >= 15:
        regime, sentiment_hint = "Risk-on moderado", "COMPRA"
    elif score <= -35 and coverage_pct >= 80:
        regime, sentiment_hint = "Risk-off forte", "VENDA"
    elif score <= -15:
        regime, sentiment_hint = "Risk-off moderado", "VENDA"
    else:
        regime, sentiment_hint = "Neutro/seletivo", "NEUTRO"

    if confidence == "Baixa" and regime in {"Risk-on forte", "Risk-off forte"}:
        regime = regime.replace("forte", "moderado")

    fresh_count = sum(item["status"] == "fresh" for item in observations.values())
    close_count = sum(item["status"] == "last_close" for item in observations.values())
    stale_assets = [specs[key][0] for key, item in observations.items() if item["status"] == "stale"]
    unknown_assets = [specs[key][0] for key, item in observations.items() if item["status"] == "unknown"]
    missing_assets = [specs[key][0] for key, item in observations.items() if item["status"] == "missing"]
    quality = {
        "coverage_pct": coverage_pct,
        "fresh_assets": fresh_count,
        "last_close_assets": close_count,
        "stale_assets": stale_assets,
        "unknown_timestamp_assets": unknown_assets,
        "missing_assets": missing_assets,
        "covered_blocks": len(available_blocks),
        "alignment_pct": round(alignment * 100),
        "status": "adequada" if coverage_pct >= 60 else "limitada",
        "horizons_available": [label for label, value in score_horizons.items() if value is not None],
        "history_samples": len(market_history.get("samples", [])) if isinstance(market_history, dict) else 0,
    }

    group_scores = {block["key"]: block for block in blocks}
    reasons = []
    confirmations = []
    divergences = list(history_conflicts)
    for block in blocks:
        block_score = block["score"]
        if block_score is None:
            continue
        member_keys = {
            "equities": ("sp500", "nasdaq", "dow"),
            "volatility": ("vix",),
            "rates": ("us02y", "us10y", "us30y"),
            "dollar": ("dxy",),
            "em_brazil": ("eem", "ewz", "ibov", "usbrl", "real_cme"),
            "risk_appetite": ("bitcoin",),
        }[block["key"]]
        evidence = [observations[key]["evidence"] for key in member_keys if observations[key]["evidence"]]
        if block["key"] == "rates" and curve:
            evidence.insert(0, f"Curva: {rate_regime}; {curve.get('macro_reading', '')}")
        direction = "favoravel" if block_score > 0.15 else "desfavoravel" if block_score < -0.15 else "neutro"
        contribution = block["weight"] * block_score
        block["contribution"] = round(contribution, 1)
        block["direction"] = direction
        block["evidence"] = evidence[:3]
        if abs(contribution) >= 1:
            reasons.append(f"{block['label']}: {direction} (contribuicao {contribution:+.1f})")
        if regime.startswith("Risk-on") and block_score > 0.15:
            confirmations.append(f"{block['label']} confirma apetite a risco")
        elif regime.startswith("Risk-off") and block_score < -0.15:
            confirmations.append(f"{block['label']} confirma defesa")
        elif (block_score > 0.15 and regime.startswith("Risk-off")) or (block_score < -0.15 and regime.startswith("Risk-on")):
            divergences.append(f"{block['label']} diverge do regime agregado")

    for key, item in assets.items():
        daily = _change(item)
        try:
            short_move = float(item.get("change_5m"))
        except (TypeError, ValueError, AttributeError):
            continue
        if daily is None or abs(short_move) < 0.03 or observations[key]["score"] is None:
            continue
        if daily * short_move > 0:
            confirmations.append(f"{specs[key][0]}: impulso de 5 min confirma a direcao diaria")
        elif daily * short_move < 0:
            divergences.append(f"{specs[key][0]}: impulso de 5 min contraria a direcao diaria")

    important_calendar, calendar_stale = _calendar_events(calendar_data, now)
    if calendar_stale:
        important_calendar.insert(0, "AVISO: calendario recebido sem eventos atuais; verificar atualizacao da fonte.")
    horizon_summaries = _optional_horizons({
        key: assets[key] if observations[key]["status"] in {"fresh", "last_close"} else {}
        for key in assets
    })
    horizon_summaries = [f"1 dia: score {daily_score:+.1f}/100"] + [
        f"{label}: score {value['score']:+.1f}/100, cobertura {value['coverage_pct']}%" +
        (f"; destaques {value['evidence']}" if value.get("evidence") else "")
        for label, value in historical_scores.items() if value.get("score") is not None
    ] + horizon_summaries
    for label in ("5 pregoes", "20 pregoes"):
        if historical_scores.get(label, {}).get("score") is None:
            horizon_summaries.append(f"{label}: historico ainda em formacao; sem amostra suficiente.")
    source_times = [
        str(item.get("source_timestamp"))
        for key, item in assets.items()
        if item and item.get("source_timestamp") and observations[key]["status"] in {"fresh", "last_close"}
    ]
    latest_source_time = max(source_times) if source_times else None

    for name in ("brent", "wti", "gold"):
        if observations[name]["evidence"]:
            reasons.append(f"Contexto de commodities: {observations[name]['evidence']}")

    snapshot_lines = [observations[key]["evidence"] for key in assets if observations[key]["evidence"]]
    return {
        "score": score,
        "daily_score": daily_score,
        "regime": regime,
        "confidence": confidence,
        "sentiment_hint": sentiment_hint,
        "reasons": reasons[:8],
        "curve": {
            "regime": rate_regime,
            "confidence": curve.get("confidence", "Baixo"),
            "bias": curve.get("operational_bias", "Neutro"),
            "reading": curve.get("macro_reading", "Sem dados recentes suficientes para ler a curva."),
        },
        "snapshot": snapshot_lines,
        "calendar_focus": important_calendar[:6],
        "local_data_available": bool(local_data),
        "data_quality": quality,
        "block_scores": group_scores,
        "confirmations": confirmations[:5],
        "divergences": divergences[:5],
        "horizons": horizon_summaries,
        "horizon_scores": score_horizons,
        "latest_source_timestamp": latest_source_time,
        "market_snapshot_timestamp": parsed_snapshot_timestamp.isoformat() if parsed_snapshot_timestamp else None,
        "market_snapshot_age_seconds": snapshot_age_seconds,
        "dashboard_rtd": rtd_context,
        "calendar_stale": calendar_stale,
        "history_quotes": history_quotes,
    }


def _extract_sentiment(full_text, fallback="NEUTRO"):
    upper = full_text.upper()
    if "REGIME: RISK-ON" in upper or "REGIME: RISK ON" in upper:
        return "COMPRA"
    if "REGIME: RISK-OFF" in upper or "REGIME: RISK OFF" in upper:
        return "VENDA"
    if "REGIME: NEUTRO" in upper or "REGIME: NEUTRO/SELETIVO" in upper:
        return "NEUTRO"
    if "VEREDITO: COMPRA" in upper:
        return "COMPRA"
    if "VEREDITO: VENDA" in upper:
        return "VENDA"
    if "VEREDITO: NEUTRO" in upper:
        return "NEUTRO"
    return fallback


def _clean_verdict(full_text):
    cleaned = full_text
    for verdict in [
        "VEREDITO: COMPRA", "VEREDITO: VENDA", "VEREDITO: NEUTRO",
        "REGIME: RISK-ON", "REGIME: RISK ON", "REGIME: RISK-OFF", "REGIME: RISK OFF",
        "REGIME: NEUTRO", "REGIME: NEUTRO/SELETIVO",
    ]:
        cleaned = cleaned.replace(verdict, "")
        cleaned = cleaned.replace(verdict.lower(), "")
        cleaned = cleaned.replace(verdict.title(), "")
    return cleaned.strip()


def _local_fallback_text(context):
    quality = context.get("data_quality", {})
    curve = context.get("curve", {})
    score = context.get("score", 0)
    score_text = "n/d" if context.get("regime") == "Dados insuficientes" else f"{score:+.1f}/100"
    freshness = (
        f"cobertura {quality.get('coverage_pct', 0):.0f}% | "
        f"{quality.get('fresh_assets', 0)} cotacoes frescas | "
        f"{quality.get('last_close_assets', 0)} no ultimo fechamento"
    )
    if context.get("latest_source_timestamp"):
        freshness += f" | dado mais recente {context['latest_source_timestamp']}"
    evidence = [
        entry
        for block in context.get("block_scores", {}).values()
        for entry in block.get("evidence", [])
    ][:8]
    evidence = evidence or ["Sem cotacoes atuais suficientes para formar evidencias por mercado."]
    confirmations = context.get("confirmations") or ["Nenhum bloco independente confirma uma direcao dominante."]
    divergences = context.get("divergences") or ["Sem divergencia direcional relevante identificada nos dados validos."]
    calendar = context.get("calendar_focus") or ["Sem evento HIGH/MEDIUM atual encontrado no calendario."]
    stale = quality.get("stale_assets") or []
    stale_text = ", ".join(stale[:5]) if stale else "nenhum"
    horizons = context.get("horizons") or ["Historico semanal/mensal nao esta presente no snapshot; nao foi inferido."]
    rtd = context.get("dashboard_rtd", {})
    rtd_evidence = rtd.get("evidence") or ["Sem leitura RTD Brasil disponivel no snapshot do dashboard."]
    if context.get("regime") == "Dados insuficientes":
        impact = "A cobertura ou a atualizacao dos dados nao permite inferir um regime confiavel. Evitar conclusao direcional ate normalizar as fontes."
    elif context["regime"].startswith("Risk-on"):
        impact = "O conjunto favorece apetite a risco; confirmar transmissao por dolar, volatilidade e emergentes antes de ampliar exposicao."
    elif context["regime"].startswith("Risk-off"):
        impact = "O conjunto aponta defesa e condicoes financeiras mais restritivas; observar dolar, yields e comportamento relativo dos emergentes."
    else:
        impact = "Os blocos nao formam direcao dominante; tratar como ambiente seletivo e esperar confirmacao entre juros, dolar, volatilidade e Brasil."

    return f"""REGIME MACRO
{context['regime']} | confianca {context['confidence']} | score {score_text}.

QUALIDADE DOS DADOS
{freshness}. Cotacoes atrasadas excluidas: {stale_text}.

RTD BRASIL DO DASHBOARD
{chr(10).join('- ' + item for item in rtd_evidence[:3])}

EVIDENCIAS OBSERVADAS
{chr(10).join('- ' + item for item in evidence)}

CONFIRMACOES
{chr(10).join('- ' + item for item in confirmations[:4])}

DIVERGENCIAS / RISCOS
{chr(10).join('- ' + item for item in divergences[:4])}

CURVA, JUROS E DOLAR
{curve.get('regime', 'Dados insuficientes')} | vies {curve.get('bias', 'Neutro')}. {curve.get('reading', '')}

HORIZONTES
{chr(10).join('- ' + item for item in horizons[:3])}

CALENDARIO
{chr(10).join('- ' + item for item in calendar[:3])}

IMPACTO PROVAVEL
{impact}

RISCO
Score local e leitura de regime, nao recomendacao de compra/venda. Pesos fixos provisorios; divergencias entre blocos reduzem confianca.
"""


def generate_macro_insight(market_inputs=None, refresh_stale_dashboard=False):
    try:
        dashboard_inputs_supplied = market_inputs is not None
        loaded_inputs, supabase_client = _load_macro_inputs(market_inputs)
        market_inputs = dict(loaded_inputs)
        local_data = market_inputs["dados_mercado"]
        global_data = market_inputs["mercados_globais"]
        calendar_data = market_inputs["calendario_economico"]
        market_history = market_inputs.get(FALLBACK_HISTORY_KEY, {"samples": []})
        dashboard_refresh = {"attempted": False, "succeeded": False, "error": None}
        preview = build_macro_regime_context(
            local_data, global_data, calendar_data, market_history=market_history
        )
        if refresh_stale_dashboard and dashboard_inputs_supplied:
            global_data, dashboard_refresh = _refresh_macro_dashboard_snapshot(
                market_inputs, supabase_client, preview
            )
        macro_context = build_macro_regime_context(
            local_data, global_data, calendar_data, market_history=market_history
        )
        macro_context["dashboard_refresh"] = dashboard_refresh
        updated_history, history_added = append_macro_market_snapshot(
            market_history,
            macro_context.get("history_quotes"),
        )
        if history_added and supabase_client:
            try:
                from execution.app_state_sync import sync_app_state_value

                sync_app_state_value(FALLBACK_HISTORY_KEY, updated_history, supabase_client)
            except Exception as history_error:
                print(f"[WARN] Historico de mercado nao foi salvo no Supabase: {history_error}")

        api_key = (os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY") or "").strip()
        insufficient_data = macro_context["regime"] == "Dados insuficientes"
        if not api_key or insufficient_data:
            clean_text = _local_fallback_text(macro_context)
            sentiment = macro_context["sentiment_hint"]
            provider = "Local/data_quality_guard" if insufficient_data else "Local/macro_regime_engine"
        else:
            model_name = os.getenv("AI_ANALYST_GEMINI_MODEL", "gemini-flash-latest").strip()
            prompt = f"""
Voce e um Analista Macro Global Profissional, com mentalidade de trader institucional.

Use o painel macro estruturado abaixo como fonte principal. Os dados brutos sao apenas apoio.
Seu trabalho e transformar o contexto em uma leitura curta de regime macro para o Terminal de Trading.
O bloco RTD Brasil e um dado do proprio dashboard, mas e separado do score global; use-o apenas como contexto/confirmacao local e respeite o horario e a idade informados.

HIERARQUIA OBRIGATORIA:
1. Curva americana, US02Y e yields longos
2. DXY e liquidez global
3. VIX e apetite a risco
4. S&P 500, Nasdaq e Dow
5. Emergentes: EEM, EWZ, USDBRL e 6L
6. Commodities: petroleo, ouro e cripto
7. Calendario economico

PAINEL MACRO ESTRUTURADO:
{json.dumps({key: value for key, value in macro_context.items() if key != 'history_quotes'}, ensure_ascii=False, indent=2)}

DADOS BRUTOS DE APOIO:
MERCADO LOCAL: {json.dumps(local_data, ensure_ascii=False)}
MERCADOS GLOBAIS: {json.dumps(global_data, ensure_ascii=False)}
CALENDARIO: {json.dumps(calendar_data, ensure_ascii=False)}

FORMATO:
REGIME
Uma linha com Risk-on, Risk-off ou Neutro/seletivo e o motivo principal.

DRIVERS
3 bullets curtos conectando dado observado -> leitura macro -> impacto provavel.

INTERMERCADOS
- Juros/DXY:
- VIX/Indices EUA:
- Emergentes/Brasil:
- Commodities:

CALENDARIO
Classifique os eventos relevantes como inflacao, crescimento, emprego, politica monetaria ou neutro. Explique o risco macro em 1 ou 2 linhas.

IMPACTO PROVAVEL
Explique em uma linha o efeito esperado em juros, DXY, petroleo, indices EUA e Brasil.

RISCO
Uma linha com o principal ponto que pode invalidar a leitura.

REGRAS:
- Nao seja generico.
- Nao invente dados ausentes.
- Nao trate a curva como gatilho isolado.
- Nao liste ativos isoladamente; explique a cadeia juros -> dolar -> risco -> emergentes -> Brasil.
- Nao gere recomendacao direta de compra/venda. E uma leitura de regime macro, nao call de trade.
- A ultima linha deve ser exatamente: REGIME: RISK-ON, REGIME: RISK-OFF ou REGIME: NEUTRO.
"""
            try:
                full_text = generate_gemini_text(prompt, model_name=model_name, api_key=api_key)
                sentiment = _extract_sentiment(full_text, macro_context["sentiment_hint"])
                clean_text = _clean_verdict(full_text)
                provider = f"Gemini/{model_name} + macro_regime_engine"
            except Exception as e:
                print(f"[WARN] Gemini indisponivel para IA Analista; usando leitura local: {e}")
                clean_text = _local_fallback_text(macro_context)
                sentiment = macro_context["sentiment_hint"]
                provider = "Local/macro_regime_engine (fallback Gemini)"

        updated_at = datetime.now(ZoneInfo("America/Sao_Paulo")).isoformat(timespec="seconds")
        payload = {
            "insight": clean_text,
            "sentiment": sentiment,
            "updated_at": updated_at,
            "provider": provider,
            "macro_regime": macro_context.get("regime"),
            "confidence": macro_context.get("confidence"),
            "macro_score": macro_context.get("score"),
            "curve_regime": macro_context.get("curve", {}).get("regime"),
            "curve_bias": macro_context.get("curve", {}).get("bias"),
            "drivers": macro_context.get("reasons", []),
            "data_quality": macro_context.get("data_quality", {}),
            "block_scores": macro_context.get("block_scores", {}),
            "confirmations": macro_context.get("confirmations", []),
            "divergences": macro_context.get("divergences", []),
            "horizons": macro_context.get("horizons", []),
            "latest_source_timestamp": macro_context.get("latest_source_timestamp"),
            "daily_score": macro_context.get("daily_score"),
            "horizon_scores": macro_context.get("horizon_scores", {}),
            "market_snapshot_timestamp": macro_context.get("market_snapshot_timestamp"),
            "market_snapshot_age_seconds": macro_context.get("market_snapshot_age_seconds"),
            "dashboard_rtd": macro_context.get("dashboard_rtd", {}),
            "dashboard_refresh": dashboard_refresh,
        }
        with open("ai_insight.json", "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        return clean_text

    except Exception as e:
        print(f"Erro na IA: {e}")
        return f"Erro ao gerar analise: {e}"


if __name__ == "__main__":
    generate_macro_insight()

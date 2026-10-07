"""Plain-language, rule-based summary of the Brazilian macro monitor."""

from __future__ import annotations

from typing import Any


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _series_map(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    history = payload.get("official_history") or {}
    return {
        str(item.get("key")): item
        for item in history.get("series", [])
        if isinstance(item, dict) and item.get("key")
    }


def _latest_pair(series: dict[str, Any] | None) -> tuple[dict[str, Any], dict[str, Any]]:
    observations = series.get("observations", []) if isinstance(series, dict) else []
    valid = [row for row in observations if isinstance(row, dict) and _number(row.get("value")) is not None]
    valid.sort(key=lambda row: str(row.get("period") or row.get("date") or ""))
    return (valid[-1], valid[-2]) if len(valid) > 1 else (valid[-1], {}) if valid else ({}, {})


def _fmt(value: Any, digits: int = 2) -> str:
    number = _number(value)
    if number is None:
        return "dado indisponível"
    return f"{number:,.{digits}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _movement(current: Any, previous: Any) -> float | None:
    now, before = _number(current), _number(previous)
    return round(now - before, 4) if now is not None and before is not None else None


def _period(row: dict[str, Any]) -> str:
    value = str(row.get("date") or row.get("period") or "período não informado")
    return value[:7] if len(value) == 10 and value[7:] == "-01" else value


def build_monitor_br_briefing(payload: Any) -> dict[str, Any]:
    """Turn latest observations into concise descriptions, not forecasts."""
    data = payload if isinstance(payload, dict) else {}
    series = _series_map(data)
    official = data.get("official") or {}
    focus = data.get("focus") or {}
    policy = data.get("monetary_policy") or {}
    points: list[dict[str, str]] = []

    ipca, ipca_prev = _latest_pair(series.get("ipca"))
    if not ipca:
        fallback_ipca = official.get("ipca") or {}
        if _number(fallback_ipca.get("value")) is not None:
            ipca = {"date": fallback_ipca.get("date"), "value": fallback_ipca.get("value")}
            ipca_prev = {"date": "mês anterior", "value": fallback_ipca.get("previous")}
    if ipca:
        delta = _movement(ipca.get("value"), ipca_prev.get("value"))
        if delta is None:
            direction = "Ainda não há mês anterior disponível para comparar."
        elif delta > 0.00005:
            direction = f"A taxa mensal subiu de {_fmt(ipca_prev.get('value'))}% para {_fmt(ipca.get('value'))}% (variação de +{_fmt(delta, 3)} p.p.) em relação a {_period(ipca_prev)}."
        elif delta < -0.00005:
            direction = f"A taxa mensal recuou de {_fmt(ipca_prev.get('value'))}% para {_fmt(ipca.get('value'))}% (variação de -{_fmt(abs(delta), 3)} p.p.) em relação a {_period(ipca_prev)}."
        else:
            direction = "A variação mensal ficou praticamente estável ante o mês anterior."
        component_series = [item for key, item in series.items() if key.startswith("ipca_group_")]
        contributions = []
        for component in component_series:
            rows = component.get("observations", [])
            match = next((row for row in reversed(rows) if row.get("period") == ipca.get("period") and _number(row.get("contribution_pp_approx")) is not None), None)
            if match:
                contributions.append((match["contribution_pp_approx"], component.get("name", "Grupo")))
        contribution_text = ""
        if contributions:
            biggest_up = max(contributions)
            biggest_down = min(contributions)
            if biggest_up[0] > 0 and biggest_down[0] < 0:
                contribution_text = f" Entre os grupos, {biggest_up[1]} teve a maior pressão de alta (cerca de +{_fmt(biggest_up[0], 3)} p.p.), enquanto {biggest_down[1]} mais ajudou a reduzir o índice (cerca de {_fmt(biggest_down[0], 3)} p.p.)."
        ipca_source = "IBGE SIDRA · tabela 7060" if series.get("ipca") else "BCB SGS 433 · IPCA"
        points.append({
            "title": "Preços",
            "text": f"O IPCA variou {_fmt(ipca.get('value'))}% em {_period(ipca)}. {direction}{contribution_text}",
            "reference": f"{ipca_source} · {_period(ipca)}",
        })

    activity_parts = []
    for key, label in (("ibc_br", "IBC-Br"), ("retail", "vendas no varejo")):
        current, previous = _latest_pair(series.get(key))
        change = _movement(current.get("value"), previous.get("value"))
        if not current:
            continue
        unit = series[key].get("unit", "")
        value_text = _fmt(current.get("value"))
        if key == "retail":
            if change is None:
                trend = "sem comparação disponível"
            elif change > 0.00005:
                trend = f"acelerou {_fmt(change, 3)} p.p. ante a leitura anterior"
            elif change < -0.00005:
                trend = f"desacelerou {_fmt(abs(change), 3)} p.p. ante a leitura anterior"
            else:
                trend = "ficou estável ante a leitura anterior"
            activity_parts.append(f"{label}: {_fmt(current.get('value'))}% em {_period(current)}, {trend}")
        else:
            if change is None:
                trend = "não há variação mensal comparável disponível"
            elif change > 0.00005:
                previous_value = _number(previous.get("value"))
                rate = (change / previous_value * 100) if previous_value else None
                trend = f"o índice avançou {_fmt(rate, 2)}% frente à observação anterior" if rate is not None else "o índice avançou frente à observação anterior"
            elif change < -0.00005:
                previous_value = _number(previous.get("value"))
                rate = (change / previous_value * 100) if previous_value else None
                trend = f"o índice recuou {_fmt(abs(rate), 2)}% frente à observação anterior" if rate is not None else "o índice recuou frente à observação anterior"
            else:
                trend = "o índice ficou estável frente à observação anterior"
            activity_parts.append(f"{label}: {value_text} {unit} em {_period(current)}; {trend}")
    if activity_parts:
        points.append({"title": "Atividade e consumo", "text": ". ".join(activity_parts) + ".", "reference": "IBGE SIDRA e Banco Central · referências indicadas em cada série"})

    labor, labor_prev = _latest_pair(series.get("unemployment"))
    if labor:
        change = _movement(labor.get("value"), labor_prev.get("value"))
        if change is None:
            trend = "sem trimestre anterior disponível para comparação"
        elif change > 0.00005:
            trend = f"subiu {_fmt(change, 2)} p.p., movimento que indica maior desocupação"
        elif change < -0.00005:
            trend = f"caiu {_fmt(abs(change), 2)} p.p., movimento que indica menor desocupação"
        else:
            trend = "ficou praticamente estável"
        points.append({
            "title": "Trabalho",
            "text": f"A taxa de desocupação foi {_fmt(labor.get('value'))}% em {_period(labor)} e {trend}. É uma taxa trimestral móvel, não uma contagem de empregos criados no mês.",
            "reference": "IBGE PNAD Contínua · taxa de desocupação",
        })

    credit_parts = []
    for key, label in (
        ("credit_interest", "juros médios de novas operações"),
        ("credit_delinquency", "inadimplência acima de 90 dias"),
    ):
        current, previous = _latest_pair(series.get(key))
        if not current:
            continue
        change = _movement(current.get("value"), previous.get("value"))
        item = series[key]
        if change is None:
            trend = "sem observação anterior para comparar"
        elif abs(change) < 0.00005:
            trend = "praticamente estável"
        else:
            direction = "subiu" if change > 0 else "caiu"
            trend = f"{direction} {_fmt(abs(change), 3)} p.p."
        credit_parts.append(f"{label}: {_fmt(current.get('value'))}{'%' if key == 'credit_delinquency' else '% a.a.'} ({trend}; {_period(current)})")
    for key, label in (
        ("credit_balance", "saldo total de crédito"),
        ("credit_concessions", "novas concessões"),
    ):
        current, previous = _latest_pair(series.get(key))
        if not current:
            continue
        value = _number(current.get("value"))
        previous_value = _number(previous.get("value"))
        if value is None:
            continue
        if previous_value:
            change_pct = (value / previous_value - 1) * 100
            movement = f", { 'subiu' if change_pct > 0 else 'caiu' if change_pct < 0 else 'ficou estável' } {_fmt(abs(change_pct), 2)}% nominal ante a leitura anterior"
        else:
            movement = ""
        credit_parts.append(f"{label}: R$ {_fmt(value / 1000, 1)} bilhões em {_period(current)}{movement}")
    if credit_parts:
        points.append({
            "title": "Crédito",
            "text": ". ".join(credit_parts) + ". Juros e inadimplência ajudam a acompanhar o custo e o risco do crédito; saldo e concessões estão em valores nominais, sem descontar a inflação.",
            "reference": "Banco Central · séries SGS 20714 e 21082",
        })

    selic = policy.get("selic") or official.get("selic") or {}
    focus_ipca = (focus.get("indicators") or {}).get("IPCA") or {}
    focus_date = focus.get("publish_date") or policy.get("focus_publish_date") or "data não informada"
    policy_parts = []
    if _number(selic.get("value")) is not None:
        policy_parts.append(f"A Selic está em {_fmt(selic['value'])}% ao ano ({selic.get('date') or 'referência não informada'}).")
    if _number(focus_ipca.get("value")) is not None:
        policy_parts.append(f"No Focus, a mediana para o IPCA de {focus.get('year') or 'este ano'} é {_fmt(focus_ipca['value'])}% (boletim de {focus_date}).")
        revised = _number(focus_ipca.get("delta_4w"))
        if revised is not None:
            if revised > 0.00005:
                policy_parts.append(f"Essa expectativa subiu {_fmt(revised, 2)} p.p. em quatro semanas.")
            elif revised < -0.00005:
                policy_parts.append(f"Essa expectativa caiu {_fmt(abs(revised), 2)} p.p. em quatro semanas.")
            else:
                policy_parts.append("Essa expectativa ficou estável em quatro semanas.")
    spread = _number((data.get("derived") or {}).get("selic_di_spread_pp"))
    if spread is not None:
        if spread > 0:
            di_reading = f"O DI curto está {_fmt(spread, 3)} p.p. acima da Selic observada"
        elif spread < 0:
            di_reading = f"O DI curto está {_fmt(abs(spread), 3)} p.p. abaixo da Selic observada"
        else:
            di_reading = "O DI curto está em linha com a Selic observada"
        policy_parts.append(di_reading + "; é o preço do mercado para juros futuros, não uma promessa do Copom.")
    next_meeting = policy.get("next_meeting") or {}
    if next_meeting.get("decision_date"):
        policy_parts.append(f"A próxima decisão do Copom está prevista para {next_meeting['decision_date']}.")
    if policy_parts:
        points.append({"title": "Juros e expectativas", "text": " ".join(policy_parts) + " Focus é expectativa dos participantes consultados pelo BCB, não uma promessa nem a decisão futura do Copom.", "reference": "BCB · Selic meta, Boletim Focus e curva DI"})

    return {
        "title": "O que está acontecendo no Brasil",
        "intro": "Resumo automático dos dados mais recentes disponíveis, explicado sem jargão.",
        "points": points,
        "empty_message": "Ainda não há séries suficientes para montar a leitura. Atualize o Monitor BR para consultar as fontes oficiais.",
    }

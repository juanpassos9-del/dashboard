"""Coleta ajustes oficiais de WIN e WDO no arquivo B3 BVBG.187.01."""

from __future__ import annotations

import argparse
import io
import json
import logging
from decimal import Decimal, ROUND_HALF_UP
import re
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

import requests


LOGGER = logging.getLogger("b3_settlements")
B3_DOWNLOAD_URL = "https://www.b3.com.br/pesquisapregao/download"
CACHE_DIR = Path(".tmp") / "b3" / "settlements"
OUTPUT_FILE = Path("b3_settlements.json")
USER_AGENT = "Mozilla/5.0 (compatible; TTS-Dashboard/1.0; +https://www.b3.com.br/)"
CONTRACT_RE = re.compile(r"^(WIN|WDO)([FGHJKMNQUVXZ])(\d{2})$")
MONTH_CODES = {
    "F": 1, "G": 2, "H": 3, "J": 4, "K": 5, "M": 6,
    "N": 7, "Q": 8, "U": 9, "V": 10, "X": 11, "Z": 12,
}


class B3SettlementError(RuntimeError):
    """Base para erros do coletor de ajustes B3."""


class B3DownloadError(B3SettlementError):
    """Arquivo oficial indisponivel ou download invalido."""


class B3DataFormatError(B3SettlementError):
    """Estrutura do BVBG.187 nao contem os campos esperados."""


class SettlementNotFoundError(B3SettlementError):
    """Nenhum ajuste valido foi encontrado para WIN/WDO."""


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _descendant_text(element: ET.Element, tag_name: str) -> str | None:
    for child in element.iter():
        if _local_name(child.tag) == tag_name and child.text:
            return child.text.strip()
    return None


def _as_float(value: str | None) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: str | None) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _contract_month_year(ticker: str) -> tuple[int, int]:
    match = CONTRACT_RE.match(ticker)
    if not match:
        raise ValueError(f"Ticker futuro invalido: {ticker}")
    return 2000 + int(match.group(3)), MONTH_CODES[match.group(2)]


def _win_expiry(year: int, month: int) -> date:
    """Quarta-feira mais proxima do dia 15, conforme especificacao do WIN."""
    center = date(year, month, 15)
    candidates = [center + timedelta(days=offset) for offset in range(-3, 4)]
    return min((day for day in candidates if day.weekday() == 2), key=lambda day: abs((day - center).days))


def _extract_xml_documents(payload: bytes) -> list[bytes]:
    documents: list[bytes] = []

    def visit(blob: bytes) -> None:
        if zipfile.is_zipfile(io.BytesIO(blob)):
            with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                for name in archive.namelist():
                    if not name.endswith("/"):
                        visit(archive.read(name))
            return
        if blob.lstrip().startswith(b"<?xml") or blob.lstrip().startswith(b"<Document"):
            documents.append(blob)

    visit(payload)
    if not documents:
        raise B3DataFormatError("O download nao continha XML do BVBG.187.01.")
    return documents


def _download_for_date(trade_date: date, force_download: bool = False) -> bytes:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"SPRD{trade_date:%y%m%d}.zip"
    cache_path = CACHE_DIR / filename
    if cache_path.exists() and not force_download:
        LOGGER.info("Arquivo encontrado no cache: %s", cache_path)
        return cache_path.read_bytes()

    LOGGER.info("Buscando BVBG.187 B3 para %s", trade_date.isoformat())
    try:
        response = requests.get(
            B3_DOWNLOAD_URL,
            params={"filelist": filename},
            headers={"User-Agent": USER_AGENT, "Accept": "application/zip,application/octet-stream,*/*"},
            timeout=60,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise B3DownloadError(f"Falha ao baixar {filename}: {exc}") from exc
    if not zipfile.is_zipfile(io.BytesIO(response.content)):
        raise B3DownloadError(f"B3 nao retornou um ZIP valido para {trade_date.isoformat()}.")
    try:
        _extract_xml_documents(response.content)
    except B3DataFormatError as exc:
        raise B3DownloadError(f"Arquivo oficial indisponivel para {trade_date.isoformat()}.") from exc
    cache_path.write_bytes(response.content)
    return response.content


def parse_bvbg187(payload: bytes) -> list[dict[str, Any]]:
    """Extrai contratos WIN/WDO e campos de ajuste, ignorando namespaces variaveis."""
    records: dict[str, dict[str, Any]] = {}
    for xml_data in _extract_xml_documents(payload):
        try:
            root = ET.fromstring(xml_data)
        except ET.ParseError as exc:
            raise B3DataFormatError(f"XML BVBG.187 invalido: {exc}") from exc
        for report in root.iter():
            if _local_name(report.tag) != "PricRpt":
                continue
            ticker = _descendant_text(report, "TckrSymb") or ""
            match = CONTRACT_RE.match(ticker)
            if not match:
                continue
            settlement = _as_float(_descendant_text(report, "AdjstdQt"))
            previous = _as_float(_descendant_text(report, "PrvsAdjstdQt"))
            trade_date = _descendant_text(report, "Dt")
            if settlement is None or not trade_date:
                continue
            record = {
                "date": trade_date,
                "symbol": match.group(1),
                "ticker": ticker,
                "settlement": settlement,
                "previous_settlement": previous,
                "settlement_status": _descendant_text(report, "AdjstdQtStin"),
                "previous_settlement_status": _descendant_text(report, "PrvsAdjstdQtStin"),
                "open_interest": _as_int(_descendant_text(report, "OpnIntrst")),
                "regular_transactions": _as_int(_descendant_text(report, "RglrTxsQty")),
            }
            existing = records.get(ticker)
            if not existing or record["regular_transactions"] >= existing["regular_transactions"]:
                records[ticker] = record
    if not records:
        raise SettlementNotFoundError("Nenhum contrato WIN/WDO com ajuste encontrado no BVBG.187.")
    return list(records.values())


def select_front_contract(records: list[dict[str, Any]], symbol: str, trade_date: date) -> dict[str, Any]:
    """Seleciona o vencimento frontal valido com ajuste e negociacao no arquivo oficial."""
    symbol = symbol.upper()
    candidates = []
    for record in records:
        if record.get("symbol") != symbol or record.get("settlement") is None:
            continue
        ticker = str(record.get("ticker") or "")
        year, month = _contract_month_year(ticker)
        if symbol == "WIN":
            if month not in {2, 4, 6, 8, 10, 12} or _win_expiry(year, month) < trade_date:
                continue
        elif (year, month) < (trade_date.year, trade_date.month):
            continue
        else:
            # O WDO e mensal. O proprio arquivo confirma o contrato ativo pela negociacao.
            if (year, month) == (trade_date.year, trade_date.month) and record.get("regular_transactions", 0) <= 0:
                continue
        candidates.append(record)
    if not candidates:
        raise SettlementNotFoundError(f"Contrato vigente de {symbol} nao encontrado em {trade_date.isoformat()}.")
    candidates.sort(
        key=lambda item: (
            _contract_month_year(str(item["ticker"])),
            -int(item.get("regular_transactions") or 0),
            -int(item.get("open_interest") or 0),
        )
    )
    return dict(candidates[0])


def build_settlement_levels(
    settlement: float,
    step_percent: float,
    *,
    levels: int = 5,
    tick_size: float = 0.01,
    zone_percent: float = 0.1,
) -> dict[str, Any]:
    """Cria desvios e regioes operacionais simetricas, respeitando o tick."""
    base = Decimal(str(settlement))
    step = Decimal(str(step_percent))
    tick = Decimal(str(tick_size))
    zone = Decimal(str(zone_percent))

    def at_tick(value: Decimal) -> float:
        ticks = (value / tick).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        return float(ticks * tick)

    def level_entry(index: int, deviation: Decimal) -> dict[str, Any]:
        center = Decimal(str(at_tick(base * (1 + deviation / 100))))
        return {
            "level": index,
            "percent": float(deviation),
            "price": float(center),
            "zone_lower": at_tick(center * (1 - zone / 100)),
            "zone_upper": at_tick(center * (1 + zone / 100)),
            "zone_percent": float(zone),
        }

    up = []
    down = []
    for index in range(1, levels + 1):
        deviation = step * index
        up.append(level_entry(index, deviation))
        down.append(level_entry(index, -deviation))
    return {
        "step_percent": float(step),
        "tick_size": float(tick),
        "zone_percent": float(zone),
        "up": up,
        "down": down,
    }


def _with_changes(record: dict[str, Any]) -> dict[str, Any]:
    settlement = float(record["settlement"])
    previous = record.get("previous_settlement")
    previous_value = float(previous) if previous not in (None, 0) else None
    record["change_points"] = settlement - previous_value if previous_value is not None else None
    record["change_percent"] = ((settlement / previous_value) - 1) * 100 if previous_value else None
    record["source"] = "B3 BVBG.187.01"
    record["reference_type"] = "official_settlement"
    symbol = str(record.get("symbol") or record.get("ticker") or "").upper()[:3]
    if symbol == "WIN":
        record["deviation_levels"] = build_settlement_levels(settlement, 0.5, tick_size=5)
    elif symbol == "WDO":
        record["deviation_levels"] = build_settlement_levels(settlement, 0.25, tick_size=0.5)
    return record


def get_b3_settlements(
    requested_date: date | datetime | str | None = None,
    *,
    max_lookback_days: int = 10,
    force_download: bool = False,
) -> dict[str, Any]:
    """Retorna ajustes oficiais WIN/WDO do ultimo pregao disponivel."""
    if requested_date is None:
        cursor = datetime.now().date()
    elif isinstance(requested_date, datetime):
        cursor = requested_date.date()
    elif isinstance(requested_date, date):
        cursor = requested_date
    else:
        cursor = date.fromisoformat(str(requested_date))

    errors = []
    for offset in range(max_lookback_days + 1):
        trade_date = cursor - timedelta(days=offset)
        if trade_date.weekday() >= 5:
            continue
        try:
            records = parse_bvbg187(_download_for_date(trade_date, force_download=force_download))
            contracts = {
                symbol: _with_changes(select_front_contract(records, symbol, trade_date))
                for symbol in ("WIN", "WDO")
            }
            payload = {
                "date": trade_date.isoformat(),
                "updated_at": datetime.now(ZoneInfo("America/Sao_Paulo")).isoformat(timespec="seconds"),
                "source": "B3 BVBG.187.01 - Simplified Price Report - Derivatives",
                "reference_type": "official_settlement",
                "contracts": contracts,
            }
            OUTPUT_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            return payload
        except B3SettlementError as exc:
            errors.append(f"{trade_date}: {exc}")
            LOGGER.warning("%s", errors[-1])
    raise B3DownloadError("Nenhum pregão B3 encontrado no limite configurado. " + " | ".join(errors[-3:]))


def get_win_settlement(requested_date: date | datetime | str | None = None) -> dict[str, Any]:
    return get_b3_settlements(requested_date)["contracts"]["WIN"]


def get_wdo_settlement(requested_date: date | datetime | str | None = None) -> dict[str, Any]:
    return get_b3_settlements(requested_date)["contracts"]["WDO"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Coleta ajustes oficiais WIN/WDO da B3.")
    parser.add_argument("--date", help="Pregao YYYY-MM-DD; omitir para o ultimo disponivel.")
    parser.add_argument("--force-download", action="store_true")
    parser.add_argument("--sync", action="store_true", help="Sincroniza app_state.b3_settlements no Supabase.")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
    payload = get_b3_settlements(args.date, force_download=args.force_download)
    if args.sync:
        try:
            from execution.app_state_sync import get_service_client, sync_app_state_value
        except ModuleNotFoundError:
            from app_state_sync import get_service_client, sync_app_state_value

        sync_app_state_value("b3_settlements", payload, get_service_client())
        LOGGER.info("Ajustes sincronizados no Supabase.")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

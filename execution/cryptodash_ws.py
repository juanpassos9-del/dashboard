"""Shared public WebSocket quote collector for CRIPTODASH."""

from __future__ import annotations

import gzip
import json
import threading
import time
import uuid
from typing import Any


def _as_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _message_text(message: Any) -> str:
    if isinstance(message, bytes):
        try:
            message = gzip.decompress(message)
        except OSError:
            pass
        return message.decode("utf-8", errors="replace")
    return str(message)


class CryptoDashRealtimeHub:
    """Maintains one public connection per provider/market and shares latest ticks."""

    _MARKETS = (
        "binance_spot", "binance_swap", "bingx_spot", "bingx_swap", "okx",
        "hyperliquid_default", "hyperliquid_xyz", "hyperliquid_para",
    )
    _BINGX_SUBSCRIPTIONS_PER_CONNECTION = 100

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._desired: dict[str, list[dict[str, str]]] = {key: [] for key in self._MARKETS}
        self._groups: dict[str, dict[str, list[dict[str, str]]]] = {}
        self._signatures: dict[str, tuple[tuple[str, str], ...]] = {}
        self._sockets: dict[str, Any] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._latest: dict[tuple[str, str, str], dict[str, Any]] = {}
        self._status: dict[str, dict[str, Any]] = {
            key: {"state": "aguardando", "last_message_at": None, "error": ""}
            for key in self._MARKETS
        }

    @staticmethod
    def _market_key(provider: str, market_type: str, dex: str | None = None) -> str:
        if provider == "Binance":
            return "binance_spot" if market_type == "Spot" else "binance_swap"
        if provider == "BingX":
            return "bingx_spot" if market_type == "Spot" else "bingx_swap"
        if provider == "Hyperliquid":
            return f"hyperliquid_{str(dex or 'default').lower()}"
        return "okx"

    def configure(self, instruments_by_provider: dict[str, list[dict[str, str]]]) -> None:
        """Backward-compatible configuration for the CRIPTODASH group."""
        self.configure_group("cryptodash", instruments_by_provider)

    def configure_group(
        self,
        group: str,
        instruments_by_provider: dict[str, list[dict[str, str]]],
    ) -> None:
        """Configure one consumer without replacing other consumers' subscriptions."""
        normalized: dict[str, list[dict[str, str]]] = {}
        for provider, rows in (instruments_by_provider or {}).items():
            if provider not in {"Binance", "BingX", "OKX", "Hyperliquid"}:
                continue
            normalized[provider] = [
                {
                    "asset": str(row.get("asset") or ""),
                    "instrument": str(row.get("instrument") or ""),
                    "market_type": str(row.get("market_type") or ""),
                    "dex": str(row.get("dex") or ""),
                }
                for row in rows
                if row.get("asset") and row.get("instrument") and row.get("market_type")
            ]
        with self._lock:
            self._groups[str(group)] = normalized

            merged: dict[str, list[dict[str, str]]] = {"Binance": [], "BingX": [], "OKX": [], "Hyperliquid": []}
            seen: set[tuple[str, str, str, str, str]] = set()
            for group_rows in self._groups.values():
                for provider, rows in group_rows.items():
                    for row in rows:
                        identity = (provider, row["asset"], row["instrument"], row["market_type"], row.get("dex", ""))
                        if identity not in seen:
                            seen.add(identity)
                            merged[provider].append(row)

        self._configure_merged(merged)

    def _configure_merged(self, instruments_by_provider: dict[str, list[dict[str, str]]]) -> None:
        grouped: dict[str, list[dict[str, str]]] = {key: [] for key in self._MARKETS}
        for provider, rows in instruments_by_provider.items():
            for row in rows:
                instrument = str(row.get("instrument") or "")
                asset = str(row.get("asset") or "")
                market_type = str(row.get("market_type") or "")
                if instrument and asset:
                    key = self._market_key(provider, market_type, row.get("dex"))
                    grouped.setdefault(key, []).append({
                        "asset": asset,
                        "instrument": instrument,
                        "market_type": market_type,
                        "dex": str(row.get("dex") or ""),
                    })

        desired: dict[str, list[dict[str, str]]] = {
            key: grouped[key]
            for key in ("binance_spot", "binance_swap", "okx", "hyperliquid_default", "hyperliquid_xyz", "hyperliquid_para")
        }
        for base_key in ("bingx_spot", "bingx_swap"):
            rows = grouped[base_key]
            for offset in range(0, len(rows), self._BINGX_SUBSCRIPTIONS_PER_CONNECTION):
                shard = offset // self._BINGX_SUBSCRIPTIONS_PER_CONNECTION
                desired[f"{base_key}_{shard:02d}"] = rows[offset:offset + self._BINGX_SUBSCRIPTIONS_PER_CONNECTION]

        with self._lock:
            existing_keys = set(self._signatures) | set(self._threads)
        for key in existing_keys | set(desired):
            rows = desired.get(key, [])
            rows.sort(key=lambda row: (row["instrument"], row["asset"]))
            signature = tuple(
                (row["asset"], row["instrument"], row.get("dex", "")) if key.startswith("hyperliquid_")
                else (row["asset"], row["instrument"])
                for row in rows
            )
            socket_to_close = None
            with self._lock:
                if signature == self._signatures.get(key):
                    continue
                self._desired[key] = rows
                self._signatures[key] = signature
                self._status.setdefault(key, {"state": "aguardando", "last_message_at": None, "error": ""})
                socket_to_close = self._sockets.get(key)
                if rows and (key not in self._threads or not self._threads[key].is_alive()):
                    thread = threading.Thread(target=self._run, args=(key,), daemon=True, name=f"cryptodash-{key}")
                    self._threads[key] = thread
                    thread.start()
                if not rows:
                    self._status[key] = {"state": "sem instrumentos", "last_message_at": None, "error": ""}
            if socket_to_close:
                try:
                    socket_to_close.close()
                except Exception:
                    pass

    def _run(self, key: str) -> None:
        backoff = 1
        while True:
            with self._lock:
                rows = list(self._desired.get(key, []))
                signature = self._signatures.get(key, ())
            if not rows:
                with self._lock:
                    self._status[key] = {"state": "sem instrumentos", "last_message_at": None, "error": ""}
                return

            try:
                import websocket

                app = websocket.WebSocketApp(
                    self._url(key, rows),
                    on_open=lambda ws: self._on_open(key, ws, rows),
                    on_message=lambda ws, message: self._on_message(key, message, rows),
                    on_error=lambda ws, error: self._on_error(key, error),
                    on_close=lambda ws, code, reason: self._on_close(key),
                )
                with self._lock:
                    self._sockets[key] = app
                    self._status[key] = {"state": "conectando", "last_message_at": None, "error": ""}
                app.run_forever(ping_interval=20, ping_timeout=10, reconnect=0)
                backoff = 1
            except Exception as exc:
                self._on_error(key, exc)

            with self._lock:
                if self._sockets.get(key) is not None:
                    self._sockets.pop(key, None)
                changed = signature != self._signatures.get(key, ())
            if not changed:
                time.sleep(backoff)
                backoff = min(backoff * 2, 20)

    def _url(self, key: str, rows: list[dict[str, str]]) -> str:
        if key.startswith("binance_"):
            base = "wss://stream.binance.com:9443" if key == "binance_spot" else "wss://fstream.binance.com"
            return f"{base}/ws"
        if key.startswith("bingx_spot"):
            return "wss://open-api-ws.bingx.com/market"
        if key.startswith("bingx_swap"):
            return "wss://open-api-swap.bingx.com/swap-market"
        if key.startswith("hyperliquid_"):
            return "wss://api.hyperliquid.xyz/ws"
        return "wss://ws.okx.com:443/ws/v5/public"

    def _on_open(self, key: str, ws: Any, rows: list[dict[str, str]]) -> None:
        with self._lock:
            self._status[key] = {"state": "conectado", "last_message_at": None, "error": ""}
        try:
            if key.startswith("binance_"):
                streams = [f"{row['instrument'].lower()}@ticker" for row in rows]
                for offset in range(0, len(streams), 200):
                    ws.send(json.dumps({
                        "method": "SUBSCRIBE",
                        "params": streams[offset:offset + 200],
                        "id": offset // 200 + 1,
                    }))
            elif key.startswith("bingx_"):
                for row in rows:
                    ws.send(json.dumps({
                        "id": str(uuid.uuid4()),
                        "reqType": "sub",
                        "dataType": f"{row['instrument']}@ticker",
                    }))
            elif key.startswith("hyperliquid_"):
                for row in rows:
                    ws.send(json.dumps({
                        "method": "subscribe",
                        "subscription": {"type": "activeAssetCtx", "coin": row["instrument"]},
                    }))
            elif key == "okx":
                ws.send(json.dumps({
                    "op": "subscribe",
                    "args": [{"channel": "tickers", "instId": row["instrument"]} for row in rows],
                }))
        except Exception as exc:
            self._on_error(key, exc)

    def _on_message(self, key: str, message: Any, rows: list[dict[str, str]]) -> None:
        text = _message_text(message).strip()
        if text.lower() == "ping":
            with self._lock:
                ws = self._sockets.get(key)
            if ws:
                try:
                    ws.send("Pong")
                except Exception:
                    pass
            return
        try:
            payload = json.loads(text)
        except (TypeError, ValueError):
            return
        if not isinstance(payload, dict):
            return

        by_instrument: dict[str, list[dict[str, str]]] = {}
        for row in rows:
            by_instrument.setdefault(row["instrument"].upper(), []).append(row)
        parsed = []
        if key.startswith("binance_"):
            data = payload.get("data", payload)
            instrument = str(data.get("s") or "").upper()
            for row in by_instrument.get(instrument, []):
                parsed.append((row, {
                    "price": _as_float(data.get("c")),
                    "change_pct_24h": _as_float(data.get("P")),
                    "quote_volume_24h": _as_float(data.get("q")),
                    "high_24h": _as_float(data.get("h")),
                    "low_24h": _as_float(data.get("l")),
                    "timestamp_ms": int(_as_float(data.get("E"))),
                }))
        elif key.startswith("bingx_"):
            data = payload.get("data") or {}
            channel = str(payload.get("dataType") or "")
            instrument = str(data.get("s") or channel.split("@", 1)[0]).upper()
            for row in by_instrument.get(instrument, []):
                if not isinstance(data, dict):
                    continue
                parsed.append((row, {
                    "price": _as_float(data.get("c")),
                    "change_pct_24h": _as_float(data.get("P")),
                    "quote_volume_24h": _as_float(data.get("v")),
                    "high_24h": _as_float(data.get("h")),
                    "low_24h": _as_float(data.get("l")),
                    "timestamp_ms": int(_as_float(data.get("T") or payload.get("ts"))),
                }))
        elif key.startswith("hyperliquid_") and payload.get("channel") == "activeAssetCtx":
            data = payload.get("data") or {}
            instrument_rows = by_instrument.get(str(data.get("coin") or "").upper(), [])
            ctx = data.get("ctx") or {}
            price_fields = ("oraclePx", "midPx", "markPx") if key == "hyperliquid_para" else ("midPx", "oraclePx", "markPx")
            price = next((_as_float(ctx.get(field)) for field in price_fields if _as_float(ctx.get(field)) > 0), 0.0)
            prev_day = _as_float(ctx.get("prevDayPx"))
            if instrument_rows and price > 0:
                quote = {
                    "price": price,
                    "quote_volume_24h": _as_float(ctx.get("dayNtlVlm")),
                    "timestamp_ms": 0,
                }
                if prev_day > 0:
                    quote["change_pct_24h"] = ((price / prev_day) - 1) * 100
                    quote["change_basis"] = "hyperliquid_previous_day_price"
                    quote["previous_price"] = prev_day
                parsed.extend((row, quote) for row in instrument_rows)
        elif payload.get("arg", {}).get("channel") == "tickers":
            for data in payload.get("data", []):
                instrument_rows = by_instrument.get(str(data.get("instId") or "").upper(), [])
                if not instrument_rows:
                    continue
                last = _as_float(data.get("last"))
                open_24h = _as_float(data.get("open24h"))
                quote = {
                    "price": last,
                    "change_pct_24h": ((last / open_24h) - 1) * 100 if open_24h else 0.0,
                    "quote_volume_24h": _as_float(data.get("volCcy24h")),
                    "high_24h": _as_float(data.get("high24h")),
                    "low_24h": _as_float(data.get("low24h")),
                    "timestamp_ms": int(_as_float(data.get("ts"))),
                }
                parsed.extend((row, quote) for row in instrument_rows)

        received_at = time.time()
        with self._lock:
            for row, quote in parsed:
                if quote["price"] <= 0:
                    continue
                key_tuple = (self._provider_for(key), row["asset"], row["market_type"])
                self._latest[key_tuple] = {
                    **quote,
                    "exchange": key_tuple[0],
                    "asset": row["asset"],
                    "market_type": row["market_type"],
                    "received_at": received_at,
                    "source": "WebSocket",
                }
            if parsed:
                self._status[key].update({"state": "conectado", "last_message_at": received_at, "error": ""})

    @staticmethod
    def _provider_for(key: str) -> str:
        if key.startswith("binance_"):
            return "Binance"
        if key.startswith("bingx_"):
            return "BingX"
        if key.startswith("hyperliquid_"):
            return "Hyperliquid"
        return "OKX"

    def _on_error(self, key: str, error: Any) -> None:
        with self._lock:
            previous = self._status.get(key, {})
            self._status[key] = {"state": "reconectando", "last_message_at": previous.get("last_message_at"), "error": str(error)[:160]}

    def _on_close(self, key: str) -> None:
        with self._lock:
            if key in self._status:
                self._status[key]["state"] = "reconectando"

    def latest_quotes(self) -> dict[tuple[str, str, str], dict[str, Any]]:
        with self._lock:
            return {key: dict(value) for key, value in self._latest.items()}

    def statuses(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            now = time.time()
            return {
                key: {
                    **value,
                    "age_seconds": round(now - value["last_message_at"]) if value.get("last_message_at") else None,
                }
                for key, value in self._status.items()
            }

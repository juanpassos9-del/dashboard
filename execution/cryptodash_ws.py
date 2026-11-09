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

    _MARKETS = ("binance_spot", "binance_swap", "bingx_spot", "bingx_swap", "okx")

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._desired: dict[str, list[dict[str, str]]] = {key: [] for key in self._MARKETS}
        self._signatures: dict[str, tuple[tuple[str, str], ...]] = {}
        self._sockets: dict[str, Any] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._latest: dict[tuple[str, str, str], dict[str, Any]] = {}
        self._status: dict[str, dict[str, Any]] = {
            key: {"state": "aguardando", "last_message_at": None, "error": ""}
            for key in self._MARKETS
        }

    @staticmethod
    def _market_key(provider: str, market_type: str) -> str:
        if provider == "Binance":
            return "binance_spot" if market_type == "Spot" else "binance_swap"
        if provider == "BingX":
            return "bingx_spot" if market_type == "Spot" else "bingx_swap"
        return "okx"

    def configure(self, instruments_by_provider: dict[str, list[dict[str, str]]]) -> None:
        grouped: dict[str, list[dict[str, str]]] = {key: [] for key in self._MARKETS}
        for provider, rows in instruments_by_provider.items():
            for row in rows:
                instrument = str(row.get("instrument") or "")
                asset = str(row.get("asset") or "")
                market_type = str(row.get("market_type") or "")
                if instrument and asset:
                    grouped[self._market_key(provider, market_type)].append({
                        "asset": asset,
                        "instrument": instrument,
                        "market_type": market_type,
                    })

        for key, rows in grouped.items():
            rows.sort(key=lambda row: (row["instrument"], row["asset"]))
            signature = tuple((row["asset"], row["instrument"]) for row in rows)
            socket_to_close = None
            with self._lock:
                if signature == self._signatures.get(key):
                    continue
                self._desired[key] = rows
                self._signatures[key] = signature
                socket_to_close = self._sockets.get(key)
                if key not in self._threads or not self._threads[key].is_alive():
                    thread = threading.Thread(target=self._run, args=(key,), daemon=True, name=f"cryptodash-{key}")
                    self._threads[key] = thread
                    thread.start()
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
                time.sleep(5)
                continue

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
            streams = "/".join(f"{row['instrument'].lower()}@ticker" for row in rows)
            return f"{base}/stream?streams={streams}"
        if key == "bingx_spot":
            return "wss://open-api-ws.bingx.com/market"
        if key == "bingx_swap":
            return "wss://open-api-swap.bingx.com/swap-market"
        return "wss://ws.okx.com:443/ws/v5/public"

    def _on_open(self, key: str, ws: Any, rows: list[dict[str, str]]) -> None:
        with self._lock:
            self._status[key] = {"state": "conectado", "last_message_at": None, "error": ""}
        try:
            if key.startswith("bingx_"):
                for row in rows:
                    ws.send(json.dumps({
                        "id": str(uuid.uuid4()),
                        "reqType": "sub",
                        "dataType": f"{row['instrument']}@ticker",
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

        by_instrument = {row["instrument"].upper(): row for row in rows}
        parsed = []
        if key.startswith("binance_"):
            data = payload.get("data", payload)
            instrument = str(data.get("s") or "").upper()
            row = by_instrument.get(instrument)
            if row:
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
            row = by_instrument.get(instrument)
            if row and isinstance(data, dict):
                parsed.append((row, {
                    "price": _as_float(data.get("c")),
                    "change_pct_24h": _as_float(data.get("P")),
                    "quote_volume_24h": _as_float(data.get("v")),
                    "high_24h": _as_float(data.get("h")),
                    "low_24h": _as_float(data.get("l")),
                    "timestamp_ms": int(_as_float(data.get("T") or payload.get("ts"))),
                }))
        elif payload.get("arg", {}).get("channel") == "tickers":
            for data in payload.get("data", []):
                row = by_instrument.get(str(data.get("instId") or "").upper())
                if not row:
                    continue
                last = _as_float(data.get("last"))
                open_24h = _as_float(data.get("open24h"))
                parsed.append((row, {
                    "price": last,
                    "change_pct_24h": ((last / open_24h) - 1) * 100 if open_24h else 0.0,
                    "quote_volume_24h": _as_float(data.get("volCcy24h")),
                    "high_24h": _as_float(data.get("high24h")),
                    "low_24h": _as_float(data.get("low24h")),
                    "timestamp_ms": int(_as_float(data.get("ts"))),
                }))

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
        return "Binance" if key.startswith("binance_") else "BingX" if key.startswith("bingx_") else "OKX"

    def _on_error(self, key: str, error: Any) -> None:
        with self._lock:
            self._status[key] = {"state": "reconectando", "last_message_at": self._status[key].get("last_message_at"), "error": str(error)[:160]}

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

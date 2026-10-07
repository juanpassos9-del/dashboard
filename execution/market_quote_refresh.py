"""Single-process coordinator for stale-snapshot recovery in the dashboard."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any


class MarketQuoteRefreshCoordinator:
    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self._lock = threading.Lock()
        self._running = False
        self._last_attempt = float("-inf")
        self._last_success: float | None = None
        self._last_error: str | None = None

    def request_if_stale(
        self,
        snapshot_age_seconds: float | None,
        refresh: Callable[[], Any],
        *,
        stale_after_seconds: float = 600,
        cooldown_seconds: float = 300,
        force: bool = False,
        thread_factory: Callable[..., threading.Thread] = threading.Thread,
    ) -> bool:
        """Start one daemon refresh when stale, or immediately when explicitly forced."""
        if not force and snapshot_age_seconds is not None and snapshot_age_seconds < stale_after_seconds:
            return False

        with self._lock:
            now = self._clock()
            if self._running or now - self._last_attempt < cooldown_seconds:
                return False
            self._running = True
            self._last_attempt = now

        def run() -> None:
            try:
                refresh()
            except Exception as exc:
                with self._lock:
                    self._last_error = str(exc)
            else:
                with self._lock:
                    self._last_success = self._clock()
                    self._last_error = None
            finally:
                with self._lock:
                    self._running = False

        try:
            thread_factory(target=run, name="market-quote-refresh", daemon=True).start()
        except Exception as exc:
            with self._lock:
                self._running = False
                self._last_error = str(exc)
            return False
        return True

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "running": self._running,
                "last_attempt": self._last_attempt,
                "last_success": self._last_success,
                "last_error": self._last_error,
            }

import threading

from execution.market_quote_refresh import MarketQuoteRefreshCoordinator


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class InlineThread:
    def __init__(self, *, target, **_kwargs):
        self.target = target

    def start(self):
        self.target()


def test_fresh_snapshot_does_not_start_refresh():
    coordinator = MarketQuoteRefreshCoordinator()
    calls = []

    assert not coordinator.request_if_stale(599, lambda: calls.append(True), thread_factory=InlineThread)
    assert calls == []


def test_stale_snapshot_starts_one_refresh_and_respects_cooldown():
    clock = FakeClock()
    coordinator = MarketQuoteRefreshCoordinator(clock=clock)
    calls = []

    assert coordinator.request_if_stale(601, lambda: calls.append(True), thread_factory=InlineThread)
    assert calls == [True]
    assert coordinator.status()["last_success"] == clock.now
    assert not coordinator.request_if_stale(900, lambda: calls.append(True), thread_factory=InlineThread)

    clock.now += 301
    assert coordinator.request_if_stale(900, lambda: calls.append(True), thread_factory=InlineThread)
    assert calls == [True, True]


def test_concurrent_requests_are_coalesced():
    coordinator = MarketQuoteRefreshCoordinator()
    started = threading.Event()
    release = threading.Event()
    calls = []

    def refresh():
        calls.append(True)
        started.set()
        release.wait(timeout=2)

    assert coordinator.request_if_stale(900, refresh)
    assert started.wait(timeout=1)
    assert not coordinator.request_if_stale(900, refresh)
    release.set()

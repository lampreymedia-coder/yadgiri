"""Windows-safe stop-signal registration."""

from __future__ import annotations

import signal
from typing import Any
from unittest.mock import MagicMock

from app.core.signals import install_stop_signals


class _LoopWithSignals:
    def __init__(self) -> None:
        self.handlers: list[tuple[int, Any]] = []

    def add_signal_handler(self, sig: int, callback: Any) -> None:
        self.handlers.append((sig, callback))

    def call_soon_threadsafe(self, callback: Any) -> None:
        callback()


class _LoopWithoutSignals(_LoopWithSignals):
    def add_signal_handler(self, sig: int, callback: Any) -> None:
        raise NotImplementedError("Windows ProactorEventLoop")


def test_install_stop_signals_uses_asyncio_when_available() -> None:
    loop = _LoopWithSignals()
    on_stop = MagicMock()
    install_stop_signals(loop, on_stop)  # type: ignore[arg-type]
    assert {sig for sig, _ in loop.handlers} == {signal.SIGTERM, signal.SIGINT}
    for _, callback in loop.handlers:
        callback()
    assert on_stop.call_count == 2


def test_install_stop_signals_falls_back_on_not_implemented(
    monkeypatch: Any,
) -> None:
    loop = _LoopWithoutSignals()
    on_stop = MagicMock()
    registered: list[tuple[int, Any]] = []

    def fake_signal(sig: int, handler: Any) -> Any:
        registered.append((sig, handler))
        return None

    monkeypatch.setattr(signal, "signal", fake_signal)
    install_stop_signals(loop, on_stop)  # type: ignore[arg-type]

    assert {sig for sig, _ in registered} == {signal.SIGTERM, signal.SIGINT}
    assert loop.handlers == []
    # Emulate OS delivering SIGINT via signal.signal handler.
    registered[0][1](signal.SIGINT, None)
    on_stop.assert_called_once_with()

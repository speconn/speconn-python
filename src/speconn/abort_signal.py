from __future__ import annotations

import time

import anyio


class AbortSignal:
    def __init__(self) -> None:
        self._event: anyio.Event = anyio.Event()
        self._reason: str | None = None
        self._deadline: float | None = None  # monotonic time

    @property
    def is_cancelled(self) -> bool:
        if self._event.is_set():
            return True
        # Lazy deadline check — no background task needed
        if self._deadline is not None and time.monotonic() >= self._deadline:
            self.set("timeout")
            return True
        return False

    @property
    def reason(self) -> str | None:
        return self._reason

    def set(self, reason: str | None = None) -> None:
        if not self._event.is_set():
            self._reason = reason
            self._event.set()

    def wait(self) -> anyio.Event:
        """Return the underlying Event so callers can ``await signal.wait().wait()``."""
        return self._event

    def set_timeout(self, timeout_ms: int) -> None:
        self._deadline = time.monotonic() + timeout_ms / 1000.0

    def clear_timeout(self) -> None:
        self._deadline = None

    def remaining_ms(self) -> float | None:
        if self._deadline is None:
            return None
        remaining = (self._deadline - time.monotonic()) * 1000.0
        return max(0.0, remaining)

    async def throw_if_cancelled(self) -> None:
        if self.is_cancelled:
            raise anyio.get_cancelled_exc_class()(self._reason or "cancelled")


def create_abort_signal_with_timeout(timeout_ms: int) -> AbortSignal:
    signal = AbortSignal()
    signal.set_timeout(timeout_ms)
    return signal

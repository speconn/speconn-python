from __future__ import annotations

import time


class AbortSignal:
    def __init__(self) -> None:
        self._cancelled = False
        self._reason: str | None = None
        self._deadline: float | None = None

    @property
    def is_cancelled(self) -> bool:
        if self._cancelled:
            return True
        if self._deadline is not None and time.monotonic() >= self._deadline:
            self.set("timeout")
            return True
        return False

    @property
    def reason(self) -> str | None:
        return self._reason

    def set(self, reason: str | None = None) -> None:
        if not self._cancelled:
            self._reason = reason
            self._cancelled = True

    def set_timeout(self, timeout_ms: int) -> None:
        self._deadline = time.monotonic() + timeout_ms / 1000.0

    def clear_timeout(self) -> None:
        self._deadline = None

    def remaining_ms(self) -> float | None:
        if self._deadline is None:
            return None
        remaining = (self._deadline - time.monotonic()) * 1000.0
        return max(0.0, remaining)

    def check_cancelled(self) -> None:
        if self.is_cancelled:
            reason = self._reason or "cancelled"
            raise KeyboardInterrupt(reason)

    def cleanup(self) -> None:
        self.clear_timeout()
        if not self._cancelled:
            self.set("cleanup")


def create_abort_signal_with_timeout(timeout_ms: int) -> AbortSignal:
    signal = AbortSignal()
    signal.set_timeout(timeout_ms)
    return signal

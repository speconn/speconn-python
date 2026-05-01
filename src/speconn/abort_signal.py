from __future__ import annotations

import asyncio
import time
from typing import Any


class AbortSignal:
    def __init__(self) -> None:
        self._event: asyncio.Event = asyncio.Event()
        self._reason: str | None = None
        self._deadline: float | None = None
        self._timeout_task: asyncio.Task | None = None

    @property
    def is_cancelled(self) -> bool:
        return self._event.is_set()

    @property
    def reason(self) -> str | None:
        return self._reason

    def set(self, reason: str | None = None) -> None:
        self._reason = reason
        self._event.set()
        if self._timeout_task:
            self._timeout_task.cancel()

    def wait(self) -> asyncio.Event:
        return self._event

    def set_timeout(self, timeout_ms: int) -> None:
        self._deadline = time.monotonic() + (timeout_ms / 1000.0)
        
        async def timeout_trigger():
            try:
                await asyncio.sleep(timeout_ms / 1000.0)
                self.set("timeout")
            except asyncio.CancelledError:
                pass
        
        self._timeout_task = asyncio.create_task(timeout_trigger())

    def clear_timeout(self) -> None:
        if self._timeout_task:
            self._timeout_task.cancel()
            self._timeout_task = None

    def remaining_ms(self) -> float | None:
        if self._deadline is None:
            return None
        remaining = (self._deadline - time.monotonic()) * 1000.0
        return max(0.0, remaining)

    async def throw_if_cancelled(self) -> None:
        if self.is_cancelled:
            raise asyncio.CancelledError(self._reason or "cancelled")


def create_abort_signal_with_timeout(timeout_ms: int) -> AbortSignal:
    signal = AbortSignal()
    signal.set_timeout(timeout_ms)
    return signal
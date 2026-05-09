from __future__ import annotations

import dataclasses
from typing import Any

from .abort_signal import AbortSignal


@dataclasses.dataclass
class SpeconnContext:
    headers: dict[str, str]
    response_headers: dict[str, str]
    response_trailers: dict[str, str]
    signal: AbortSignal
    method_name: str
    local_addr: str | None
    remote_addr: str | None
    values: dict[str, Any]
    _headers_sent: bool = dataclasses.field(default=False, init=False)

    def set_response_header(self, key: str, value: str) -> None:
        if self._headers_sent:
            raise RuntimeError("headers already sent")
        self.response_headers[key.lower()] = value

    def add_response_header(self, key: str, value: str) -> None:
        if self._headers_sent:
            raise RuntimeError("headers already sent")
        normalized_key = key.lower()
        if normalized_key not in self.response_headers:
            self.response_headers[normalized_key] = value
        else:
            existing = self.response_headers[normalized_key]
            self.response_headers[normalized_key] = f"{existing}, {value}"

    def set_response_trailer(self, key: str, value: str) -> None:
        self.response_trailers[key.lower()] = value

    def mark_headers_sent(self) -> None:
        self._headers_sent = True

    def value(self, key: str) -> Any:
        return self.values.get(key)

    def set_value(self, key: str, value: Any) -> None:
        self.values[key] = value

    def user(self) -> str:
        return self.values.get("user", "")

    def set_user(self, user: str) -> None:
        self.values["user"] = user

    def request_id(self) -> str:
        return self.values.get("request-id", "")

    def set_request_id(self, id: str) -> None:
        self.values["request-id"] = id

    def is_cancelled(self) -> bool:
        return self.signal.is_cancelled

    def check_cancelled(self) -> None:
        if self.is_cancelled():
            reason = self.signal.reason or "cancelled"
            raise RuntimeError(reason)

    def cleanup(self) -> None:
        self.signal.cleanup()


def create_context(
    headers: dict[str, str],
    method_name: str,
    local_addr: str | None = None,
    remote_addr: str | None = None,
    timeout_ms: int | None = None,
) -> SpeconnContext:
    normalized_headers = {k.lower(): v for k, v in headers.items()}

    signal = AbortSignal()
    if timeout_ms and timeout_ms > 0:
        signal.set_timeout(timeout_ms)

    return SpeconnContext(
        headers=normalized_headers,
        response_headers={},
        response_trailers={},
        signal=signal,
        method_name=method_name,
        local_addr=local_addr,
        remote_addr=remote_addr,
        values={},
    )

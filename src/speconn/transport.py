# SpeconnChannel — send/recv
from __future__ import annotations
import dataclasses
from typing import Protocol, runtime_checkable

@dataclasses.dataclass
class SpeconnMessage:
    path: str
    headers: list[tuple[str, str]]
    body: bytes

@dataclasses.dataclass
class HttpResponse:
    status: int
    headers: list[tuple[str, str]]
    body: bytes

@runtime_checkable
class SpeconnChannel(Protocol):
    async def send(self, msg: SpeconnMessage) -> None: ...
    async def recv(self) -> bytes | None: ...
    @property
    def response_status(self) -> int: ...
    @property
    def response_headers(self) -> list[tuple[str, str]]: ...

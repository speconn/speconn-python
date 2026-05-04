from __future__ import annotations

import dataclasses
from abc import abstractmethod
from typing import Protocol, runtime_checkable


@dataclasses.dataclass
class HttpRequest:
    url: str
    method: str
    headers: list[tuple[str, str]]
    body: bytes


@dataclasses.dataclass
class HttpResponse:
    status: int
    headers: list[tuple[str, str]]
    body: bytes


@runtime_checkable
class SpeconnTransport(Protocol):
    @abstractmethod
    async def send(self, request: HttpRequest) -> HttpResponse: ...

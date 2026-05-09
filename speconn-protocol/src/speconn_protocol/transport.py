from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class SpeconnTransport(Protocol):
    def open(
        self,
        path: str,
        headers: list[tuple[str, str]],
    ) -> "SpeconnChannel": ...


@runtime_checkable
class SpeconnChannel(Protocol):
    async def send(self, body: bytes) -> None: ...
    async def close_write(self) -> None: ...

    @property
    def response_status(self) -> int: ...

    @property
    def response_headers(self) -> list[tuple[str, str]]: ...

    async def recv(self) -> bytes | None: ...
    def close(self) -> None: ...


@runtime_checkable
class ServerChannel(SpeconnChannel, Protocol):
    def set_status(self, status: int) -> None: ...
    def set_headers(self, headers: list[tuple[str, str]]) -> None: ...

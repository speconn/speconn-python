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
    body: bytes


@runtime_checkable
class HttpClient(Protocol):
    """HttpClient is the protocol Speconn expects HTTP clients to implement."""

    @abstractmethod
    async def send(self, request: HttpRequest) -> HttpResponse: ...


class HttpxHttpClient:
    """Default HttpClient implementation using httpx."""

    def __init__(self, client=None) -> None:
        import httpx
        self._client = client or httpx.AsyncClient()

    async def send(self, request: HttpRequest) -> HttpResponse:
        headers = {k: v for k, v in request.headers}
        resp = await self._client.request(
            request.method,
            request.url,
            content=request.body,
            headers=headers,
        )
        return HttpResponse(status=resp.status_code, body=resp.content)


def _create_default_http_client() -> HttpClient:
    try:
        return HttpxHttpClient()
    except ImportError:
        raise ImportError(
            "No HTTP client available. Install httpx: pip install httpx"
        )

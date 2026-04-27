from __future__ import annotations

import json
import dataclasses
from abc import ABC, abstractmethod


@dataclasses.dataclass
class TransportResponse:
    status: int
    body: bytes


class Transport(ABC):
    @abstractmethod
    async def post(
        self, url: str, content_type: str, body: bytes, headers: dict[str, str]
    ) -> TransportResponse:
        ...


class PyreqwestTransport(Transport):
    def __init__(self) -> None:
        from pyreqwest.client import ClientBuilder

        self._client = ClientBuilder().build()

    async def post(
        self, url: str, content_type: str, body: bytes, headers: dict[str, str]
    ) -> TransportResponse:
        builder = self._client.post(url).header("content-type", content_type)
        for k, v in headers.items():
            builder = builder.header(k, v)
        req_obj = json.loads(body) if body else {}
        resp = await builder.json(req_obj).build().send()
        raw = await resp.bytes()
        return TransportResponse(status=resp.status, body=raw)


class HttpxTransport(Transport):
    def __init__(self) -> None:
        import httpx

        self._client = httpx.AsyncClient()

    async def post(
        self, url: str, content_type: str, body: bytes, headers: dict[str, str]
    ) -> TransportResponse:
        merged = {"content-type": content_type, **headers}
        resp = await self._client.post(url, content=body, headers=merged)
        return TransportResponse(status=resp.status_code, body=resp.content)


def _create_default_transport() -> Transport:
    errors: list[str] = []
    try:
        return PyreqwestTransport()
    except ImportError as e:
        errors.append(f"pyreqwest: {e}")
    try:
        return HttpxTransport()
    except ImportError as e:
        errors.append(f"httpx: {e}")
    raise ImportError(
        "No HTTP transport available. Install pyreqwest or httpx.\n"
        + "\n".join(errors)
    )

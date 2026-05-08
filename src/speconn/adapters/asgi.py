# ASGI adapter — 把 ASGI scope/receive/send 转为 SpeconnServerRequest/Response
from __future__ import annotations

from collections.abc import Callable

from ..router import SpeconnRouter, SpeconnServerRequest


async def _read_body(receive: Callable) -> bytes:
    body = b""
    while True:
        event = await receive()
        if event["type"] == "http.request":
            body += event.get("body", b"")
            if not event.get("more", False):
                break
    return body


def create_asgi_adapter(router: SpeconnRouter):
    """返回一个 ASGI 3.0 callable"""
    async def asgi_app(scope: dict, receive: Callable, send: Callable) -> None:
        if scope["type"] != "http":
            return

        if scope.get("method") == "OPTIONS":
            await _send_response(send, 204, [], b"")
            return

        path = scope.get("path", "")
        headers: dict[str, str] = {}
        for k, v in scope.get("headers", []):
            headers[k.decode().lower()] = v.decode()

        local_addr = None
        if server := scope.get("server"):
            local_addr = f"{server[0]}:{server[1]}"
        remote_addr = None
        if client := scope.get("client"):
            remote_addr = f"{client[0]}:{client[1]}"

        body = await _read_body(receive)
        req = SpeconnServerRequest(path=path, headers=headers, body=body, local_addr=local_addr, remote_addr=remote_addr)
        resp = await router.handle(req)

        final_headers: list[tuple[bytes, bytes]] = []
        for k, v in resp.headers.items():
            final_headers.append((k.encode(), v.encode()))
        await _send_response(send, resp.status, final_headers, resp.body)

    return asgi_app


async def _send_response(send: Callable, status: int, headers: list[tuple[bytes, bytes]], body: bytes) -> None:
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})

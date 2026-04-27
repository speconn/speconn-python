from __future__ import annotations

import json
import dataclasses
from collections.abc import Awaitable, Callable
from typing import Any

from .envelope import encode_envelope, FLAG_END_STREAM
from .error import Code, SpeconnError


def _to_dict(obj: object) -> object:
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return dataclasses.asdict(obj)
    if isinstance(obj, dict):
        return obj
    return obj


def _instantiate(cls: type, data: dict) -> object:
    if dataclasses.is_dataclass(cls):
        return cls(**data)
    return data


async def _read_body(receive: Callable) -> bytes:
    body = b""
    while True:
        event = await receive()
        if event["type"] == "http.request":
            body += event.get("body", b"")
            if not event.get("more", False):
                break
    return body


async def _send_error(send: Callable, code: Code, message: str) -> None:
    status = code.http_status()
    body = json.dumps({"code": code.as_str(), "message": message}).encode()
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [[b"content-type", b"application/json"]],
        }
    )
    await send({"type": "http.response.body", "body": body})


class SpeconnRouter:
    def __init__(self) -> None:
        self._unary: dict[str, tuple[type, type, Callable]] = {}
        self._streams: dict[str, tuple[type, type, Callable]] = {}

    def unary(self, path: str, req_type: type, res_type: type) -> Callable:
        def decorator(fn: Callable) -> Callable:
            self._unary[path] = (req_type, res_type, fn)
            return fn

        return decorator

    def server_stream(self, path: str, req_type: type, res_type: type) -> Callable:
        def decorator(fn: Callable) -> Callable:
            self._streams[path] = (req_type, res_type, fn)
            return fn

        return decorator

    async def __call__(
        self, scope: dict, receive: Callable, send: Callable
    ) -> None:
        if scope["type"] != "http":
            return

        path = scope.get("path", "")
        ct = ""
        for k, v in scope.get("headers", []):
            if k == b"content-type":
                ct = v.decode()
                break

        body = await _read_body(receive)
        is_stream = "connect+json" in ct

        if is_stream and path in self._streams:
            req_type, _res_type, fn = self._streams[path]
            await self._handle_stream(req_type, fn, body, send)
        elif path in self._unary:
            req_type, _res_type, fn = self._unary[path]
            await self._handle_unary(fn, req_type, body, send)
        else:
            await _send_error(send, Code.NOT_FOUND, f"no route: {path}")

    async def _handle_unary(
        self, fn: Callable, req_type: type, body: bytes, send: Callable
    ) -> None:
        try:
            data = json.loads(body) if body else {}
            req = _instantiate(req_type, data)
            result = fn(req)
            if isinstance(result, Awaitable):
                result = await result
            res_body = json.dumps(_to_dict(result)).encode()
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [[b"content-type", b"application/json"]],
                }
            )
            await send({"type": "http.response.body", "body": res_body})
        except SpeconnError as e:
            await _send_error(send, e.code, e.message)
        except Exception as e:
            await _send_error(send, Code.INTERNAL, str(e))

    async def _handle_stream(
        self, req_type: type, fn: Callable, body: bytes, send: Callable
    ) -> None:
        chunks: list[bytes] = []
        try:
            data = json.loads(body) if body else {}
            req = _instantiate(req_type, data)
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [[b"content-type", b"application/connect+json"]],
                }
            )

            def emit(msg: object) -> None:
                payload = json.dumps(_to_dict(msg)).encode()
                chunks.append(encode_envelope(0, payload))

            result = fn(req, emit)
            if isinstance(result, Awaitable):
                await result

            trailer = json.dumps({}).encode()
            chunks.append(encode_envelope(FLAG_END_STREAM, trailer))
            await send({"type": "http.response.body", "body": b"".join(chunks)})
        except SpeconnError as e:
            trailer = json.dumps(
                {"error": {"code": e.code.as_str(), "message": e.message}}
            ).encode()
            payload = (
                b"".join(chunks) + encode_envelope(FLAG_END_STREAM, trailer)
                if chunks
                else encode_envelope(FLAG_END_STREAM, trailer)
            )
            await send({"type": "http.response.body", "body": payload})
        except Exception as e:
            trailer = json.dumps(
                {"error": {"code": "internal", "message": str(e)}}
            ).encode()
            await send(
                {
                    "type": "http.response.body",
                    "body": encode_envelope(FLAG_END_STREAM, trailer),
                }
            )

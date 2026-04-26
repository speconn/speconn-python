"""Speconn Python runtime — JSON unary + Connect streaming RPC."""

from __future__ import annotations

import json
import struct
import dataclasses
from typing import Any, Callable, TypeVar, AsyncGenerator

T = TypeVar("T")

FLAG_COMPRESSED = 0x01
FLAG_END_STREAM = 0x02

CODE_TO_STATUS = {
    "invalid_argument": 400, "failed_precondition": 400, "out_of_range": 400,
    "unauthenticated": 401, "permission_denied": 403, "not_found": 404,
    "already_exists": 409, "aborted": 409, "resource_exhausted": 429,
    "canceled": 499, "unimplemented": 501, "unavailable": 503, "deadline_exceeded": 504,
}


class SpeconnError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


def _encode_envelope(flags: int, payload: bytes) -> bytes:
    return struct.pack(">BI", flags, len(payload)) + payload


def _to_dict(obj: Any) -> Any:
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return dataclasses.asdict(obj)
    if isinstance(obj, dict):
        return obj
    return obj


def _write_error(send: Callable, code: str, message: str) -> Any:
    status = CODE_TO_STATUS.get(code, 500)
    body = json.dumps({"code": code, "message": message}).encode()
    import asyncio
    async def _do():
        await send({"type": "http.response.start", "status": status, "headers": [[b"content-type", b"application/json"]]})
        await send({"type": "http.response.body", "body": body})
    return _do()


class SpeconnRouter:
    def __init__(self):
        self._unary: dict[str, Callable] = {}
        self._streams: dict[str, Callable] = {}

    def unary(self, path: str, req_type: type, res_type: type):
        def decorator(fn: Callable):
            self._unary[path] = (req_type, fn)
            return fn
        return decorator

    def server_stream(self, path: str, req_type: type, res_type: type):
        def decorator(fn: Callable):
            self._streams[path] = (req_type, fn)
            return fn
        return decorator

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        if scope["type"] != "http":
            return

        path = scope.get("path", "")
        ct = ""
        for k, v in scope.get("headers", []):
            if k == b"content-type":
                ct = v.decode()
                break

        body = b""
        while True:
            event = await receive()
            if event["type"] == "http.request":
                body += event.get("body", b"")
                if not event.get("more", False):
                    break

        is_stream = "connect+json" in ct

        if is_stream and path in self._streams:
            await self._handle_stream(path, body, send)
        elif path in self._unary:
            await self._handle_unary(path, body, send)
        else:
            await _write_error(send, "not_found", f"no route: {path}")

    async def _handle_unary(self, path: str, body: bytes, send: Callable) -> None:
        req_type, fn = self._unary[path]
        try:
            req_data = json.loads(body) if body else {}
            req = req_type(**req_data) if dataclasses.is_dataclass(req_type) else req_data
            result = fn(req)
            if hasattr(result, "__await__"):
                result = await result
            res_body = json.dumps(_to_dict(result)).encode()
            await send({"type": "http.response.start", "status": 200, "headers": [[b"content-type", b"application/json"]]})
            await send({"type": "http.response.body", "body": res_body})
        except SpeconnError as e:
            await _write_error(send, e.code, e.message)
        except Exception as e:
            await _write_error(send, "internal", str(e))

    async def _handle_stream(self, path: str, body: bytes, send: Callable) -> None:
        req_type, fn = self._streams[path]
        try:
            req_data = json.loads(body) if body else {}
            req = req_type(**req_data) if dataclasses.is_dataclass(req_type) else req_data

            await send({"type": "http.response.start", "status": 200, "headers": [[b"content-type", b"application/connect+json"]]})

            sent_chunks: list[bytes] = []

            def send_msg(msg: Any) -> None:
                payload = json.dumps(_to_dict(msg)).encode()
                sent_chunks.append(_encode_envelope(0, payload))

            result = fn(req, send_msg)
            if hasattr(result, "__await__"):
                await result

            trailer = json.dumps({}).encode()
            sent_chunks.append(_encode_envelope(FLAG_END_STREAM, trailer))
            await send({"type": "http.response.body", "body": b"".join(sent_chunks)})
        except SpeconnError as e:
            trailer = json.dumps({"error": {"code": e.code, "message": e.message}}).encode()
            chunks = b"".join(sent_chunks) + _encode_envelope(FLAG_END_STREAM, trailer) if sent_chunks else _encode_envelope(FLAG_END_STREAM, trailer)
            await send({"type": "http.response.body", "body": chunks})
        except Exception as e:
            trailer = json.dumps({"error": {"code": "internal", "message": str(e)}}).encode()
            await send({"type": "http.response.body", "body": _encode_envelope(FLAG_END_STREAM, trailer)})


class UnaryClient:
    def __init__(self, base_url: str):
        import urllib.request
        self._base_url = base_url.rstrip("/")

    def call(self, path: str, req: Any = None) -> Any:
        import urllib.request
        body = json.dumps(_to_dict(req) if req else {}).encode()
        http_req = urllib.request.Request(
            self._base_url + path,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(http_req) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            try:
                err = json.loads(e.read())
            except Exception:
                err = {"code": "unknown", "message": str(e)}
            raise SpeconnError(err.get("code", "unknown"), err.get("message", "")) from None

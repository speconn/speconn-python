from __future__ import annotations

import json
import dataclasses
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

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


@dataclasses.dataclass
class SpeconnContext:
    headers: dict[str, str]
    values: dict[str, Any]

    def value(self, key: str) -> Any:
        return self.values.get(key)

    def set_value(self, key: str, value: Any) -> None:
        self.values[key] = value

    def user(self) -> str:
        return self.values.get("user", "")


@dataclasses.dataclass
class SpeconnRequest:
    path: str
    headers: dict[str, str]
    body: Any
    content_type: str


@dataclasses.dataclass
class SpeconnResponse:
    status: int
    headers: dict[str, str]
    body: Any


class Interceptor(Protocol):
    async def before(self, ctx: SpeconnContext, req: SpeconnRequest) -> None: ...
    async def after(self, ctx: SpeconnContext, resp: SpeconnResponse) -> None: ...


class SpeconnRouter:
    def __init__(self, interceptors: list[Interceptor] | None = None) -> None:
        self._unary: dict[str, tuple[type, type, Callable]] = {}
        self._streams: dict[str, tuple[type, type, Callable]] = {}
        self._interceptors: list[Interceptor] = interceptors or []

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

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        if scope["type"] != "http":
            return

        path = scope.get("path", "")
        ct = ""
        req_headers: dict[str, str] = {}
        for k, v in scope.get("headers", []):
            decoded_key = k.decode()
            req_headers[decoded_key] = v.decode()
            if k == b"content-type":
                ct = v.decode()

        if scope.get("method") == "OPTIONS":
            await _send_response(send, 204, [], b"")
            return

        body = await _read_body(receive)
        data = json.loads(body) if body else {}

        ctx = SpeconnContext(headers=req_headers, values={})
        speconn_req = SpeconnRequest(path=path, headers=req_headers, body=data, content_type=ct)

        for interceptor in self._interceptors:
            try:
                result = interceptor.before(ctx, speconn_req)
                if isinstance(result, Awaitable):
                    await result
            except SpeconnError as e:
                await _send_error(send, e.code, e.message)
                return
            except Exception as e:
                await _send_error(send, Code.INTERNAL, str(e))
                return

        is_stream = "connect+json" in ct
        resp_headers: dict[str, str] = {}
        status: int = 200
        resp_content_type: str = "application/json"
        resp_body: bytes = b""

        try:
            if is_stream and path in self._streams:
                req_type, _res_type, fn = self._streams[path]
                resp_content_type = "application/connect+json"
                chunks: list[bytes] = []
                req_obj = _instantiate(req_type, speconn_req.body)
                emit = lambda msg: chunks.append(encode_envelope(0, json.dumps(_to_dict(msg)).encode()))  # noqa: E731
                stream_result = fn(ctx, req_obj, emit)
                if isinstance(stream_result, Awaitable):
                    await stream_result
                trailer = json.dumps({}).encode()
                chunks.append(encode_envelope(FLAG_END_STREAM, trailer))
                resp_body = b"".join(chunks)
            elif path in self._unary:
                req_type, _res_type, fn = self._unary[path]
                req_obj = _instantiate(req_type, speconn_req.body)
                result = fn(ctx, req_obj)
                if isinstance(result, Awaitable):
                    result = await result
                resp_body = json.dumps(_to_dict(result)).encode()
            else:
                await _send_error(send, Code.NOT_FOUND, f"no route: {path}")
                return
        except SpeconnError as e:
            if is_stream:
                trailer = json.dumps({"error": {"code": e.code.as_str(), "message": e.message}}).encode()
                resp_body = encode_envelope(FLAG_END_STREAM, trailer)
            else:
                await _send_error(send, e.code, e.message)
                return
        except Exception as e:
            if is_stream:
                trailer = json.dumps({"error": {"code": "internal", "message": str(e)}}).encode()
                resp_body = encode_envelope(FLAG_END_STREAM, trailer)
            else:
                await _send_error(send, Code.INTERNAL, str(e))
                return

        speconn_resp = SpeconnResponse(status=status, headers=resp_headers, body=None)
        for interceptor in self._interceptors:
            result = interceptor.after(ctx, speconn_resp)
            if isinstance(result, Awaitable):
                await result

        final_headers: list[tuple[bytes, bytes]] = []
        for k, v in speconn_resp.headers.items():
            final_headers.append([k.encode(), v.encode()])
        final_headers.append([b"content-type", resp_content_type.encode()])
        await _send_response(send, speconn_resp.status, final_headers, resp_body)


async def _send_response(send: Callable, status: int, headers: list[tuple[bytes, bytes]], body: bytes) -> None:
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


async def _send_error(send: Callable, code: Code, message: str) -> None:
    status = code.http_status()
    body = json.dumps({"code": code.as_str(), "message": message}).encode()
    await _send_response(send, status, [[b"content-type", b"application/json"]], body)

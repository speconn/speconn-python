"""Speconn Python runtime — JSON unary + Connect streaming RPC."""

from __future__ import annotations

import json
import struct
import dataclasses
from typing import Any, Callable, TypeVar, AsyncIterator, Mapping

from pyreqwest.client import ClientBuilder

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


class MethodInfo:
    __slots__ = ("name", "service_name", "input", "output", "stream_type")

    def __init__(self, name: str, service_name: str, input: type, output: type, stream_type: str = "unary"):
        self.name = name
        self.service_name = service_name
        self.input = input
        self.output = output
        self.stream_type = stream_type


def _encode_envelope(flags: int, payload: bytes) -> bytes:
    return struct.pack(">BI", flags, len(payload)) + payload


def _to_dict(obj: Any) -> Any:
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return dataclasses.asdict(obj)
    if isinstance(obj, dict):
        return obj
    return obj


def _instantiate(req_type: type, body: bytes) -> Any:
    data = json.loads(body) if body else {}
    if dataclasses.is_dataclass(req_type):
        return req_type(**data)
    return data


async def _write_error(send: Callable, code: str, message: str) -> None:
    status = CODE_TO_STATUS.get(code, 500)
    body = json.dumps({"code": code, "message": message}).encode()
    await send({"type": "http.response.start", "status": status, "headers": [[b"content-type", b"application/json"]]})
    await send({"type": "http.response.body", "body": body})


async def _read_body(receive: Callable) -> bytes:
    body = b""
    while True:
        event = await receive()
        if event["type"] == "http.request":
            body += event.get("body", b"")
            if not event.get("more", False):
                break
    return body


class Endpoint:
    def __init__(self, method: MethodInfo, function: Callable, stream: bool = False):
        self.method = method
        self.function = function
        self.stream = stream

    @staticmethod
    def unary(method: MethodInfo, function: Callable) -> Endpoint:
        return Endpoint(method, function, stream=False)

    @staticmethod
    def server_stream(method: MethodInfo, function: Callable) -> Endpoint:
        return Endpoint(method, function, stream=True)


class SpeconnASGIApplication:
    def __init__(self, service: Any, endpoints: dict[str, Endpoint]):
        self._service = service
        self._endpoints = endpoints

    @property
    def path(self) -> str:
        paths = sorted(set(ep.method.service_name for ep in self._endpoints.values()))
        return f"/{paths[0]}" if paths else "/"

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        if scope["type"] != "http":
            return

        path = scope.get("path", "")
        ep = self._endpoints.get(path)
        if ep is None:
            await _write_error(send, "not_found", f"no route: {path}")
            return

        ct = ""
        for k, v in scope.get("headers", []):
            if k == b"content-type":
                ct = v.decode()
                break

        body = await _read_body(receive)

        if ep.stream:
            await self._handle_stream(ep, body, send)
        else:
            await self._handle_unary(ep, body, send)

    async def _handle_unary(self, ep: Endpoint, body: bytes, send: Callable) -> None:
        try:
            req = _instantiate(ep.method.input, body)
            result = ep.function(req)
            if hasattr(result, "__await__"):
                result = await result
            res_body = json.dumps(_to_dict(result)).encode()
            await send({"type": "http.response.start", "status": 200, "headers": [[b"content-type", b"application/json"]]})
            await send({"type": "http.response.body", "body": res_body})
        except SpeconnError as e:
            await _write_error(send, e.code, e.message)
        except Exception as e:
            await _write_error(send, "internal", str(e))

    async def _handle_stream(self, ep: Endpoint, body: bytes, send: Callable) -> None:
        try:
            req = _instantiate(ep.method.input, body)
            await send({"type": "http.response.start", "status": 200, "headers": [[b"content-type", b"application/connect+json"]]})

            sent_chunks: list[bytes] = []

            def send_msg(msg: Any) -> None:
                payload = json.dumps(_to_dict(msg)).encode()
                sent_chunks.append(_encode_envelope(0, payload))

            result = ep.function(req, send_msg)
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


class SpeconnClient:
    def __init__(self, base_url: str):
        self._base_url = base_url.rstrip("/")
        self._client = ClientBuilder().build()

    async def _call_unary(self, path: str, req: Any, output_type: type) -> Any:
        body = _to_dict(req) if req else {}
        url = self._base_url + path
        resp = await self._client.post(url).header("content-type", "application/json").json(body).build().send()

        if resp.status >= 400:
            try:
                err = await resp.json()
            except Exception:
                err = {"code": "unknown", "message": f"HTTP {resp.status}"}
            raise SpeconnError(err.get("code", "unknown"), err.get("message", ""))

        data = await resp.json()
        if dataclasses.is_dataclass(output_type):
            return output_type(**data)
        return data

    async def _call_stream(self, path: str, req: Any, output_type: type) -> list[Any]:
        body = _to_dict(req) if req else {}
        url = self._base_url + path
        resp = await self._client.post(url).header("content-type", "application/connect+json").header("connect-protocol-version", "1").json(body).build().send()

        if resp.status >= 400:
            try:
                err = await resp.json()
            except Exception:
                err = {"code": "unknown", "message": f"HTTP {resp.status}"}
            raise SpeconnError(err.get("code", "unknown"), err.get("message", ""))

        data = await resp.bytes()
        results: list[Any] = []
        pos = 0

        while pos < len(data):
            if len(data) - pos < 5:
                break
            flags = data[pos]
            length = struct.unpack(">I", data[pos + 1:pos + 5])[0]
            if len(data) - pos < 5 + length:
                break
            payload = data[pos + 5:pos + 5 + length]
            pos += 5 + length
            if flags & FLAG_END_STREAM:
                trailer = json.loads(payload)
                error = trailer.get("error")
                if error:
                    raise SpeconnError(error.get("code", "unknown"), error.get("message", ""))
                break
            msg = json.loads(payload)
            if dataclasses.is_dataclass(output_type):
                results.append(output_type(**msg))
            else:
                results.append(msg)

        return results


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

        body = await _read_body(receive)
        is_stream = "connect+json" in ct

        if is_stream and path in self._streams:
            req_type, fn = self._streams[path]
            ep = Endpoint.server_stream(MethodInfo("", "", req_type, type), fn)
            await SpeconnASGIApplication.__dict__["_handle_stream"](self, ep, body, send)
        elif path in self._unary:
            req_type, fn = self._unary[path]
            ep = Endpoint.unary(MethodInfo("", "", req_type, type), fn)
            await SpeconnASGIApplication.__dict__["_handle_unary"](self, ep, body, send)
        else:
            await _write_error(send, "not_found", f"no route: {path}")


SpeconnRouter._handle_unary = SpeconnASGIApplication._handle_unary
SpeconnRouter._handle_stream = SpeconnASGIApplication._handle_stream

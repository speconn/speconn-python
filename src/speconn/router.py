from __future__ import annotations

import dataclasses
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from specodec import SpecCodec, dispatch, respond

from .context import SpeconnContext, create_context_from_headers
from .envelope import encode_envelope, FLAG_END_STREAM
from .error import Code, SpeconnError


# ── 归一化服务端 I/O ──

@dataclasses.dataclass
class SpeconnServerRequest:
    path: str
    headers: dict[str, str]     # lowercase
    body: bytes
    local_addr: str | None = None
    remote_addr: str | None = None

@dataclasses.dataclass
class SpeconnServerResponse:
    status: int
    headers: dict[str, str]     # includes content-type
    body: bytes

# ── Interceptor（统一用归一化类型）──

class Interceptor(Protocol):
    async def before(self, ctx: SpeconnContext, req: SpeconnServerRequest) -> None: ...
    async def after(self, ctx: SpeconnContext, resp: SpeconnServerResponse) -> None: ...


# ── Router ──

class SpeconnRouter:
    def __init__(self, interceptors: list[Interceptor] | None = None) -> None:
        self._unary: dict[str, tuple[SpecCodec, SpecCodec, Callable]] = {}
        self._streams: dict[str, tuple[SpecCodec, SpecCodec, Callable]] = {}
        self._interceptors: list[Interceptor] = interceptors or []

    def unary(self, path: str, req_codec: SpecCodec, res_codec: SpecCodec) -> Callable:
        def decorator(fn: Callable) -> Callable:
            self._unary[path] = (req_codec, res_codec, fn)
            return fn
        return decorator

    def server_stream(self, path: str, req_codec: SpecCodec, res_codec: SpecCodec) -> Callable:
        def decorator(fn: Callable) -> Callable:
            self._streams[path] = (req_codec, res_codec, fn)
            return fn
        return decorator

    # ── 框架无关 handler ──
    async def handle(self, req: SpeconnServerRequest) -> SpeconnServerResponse:
        ct = req.headers.get("content-type", "application/json")
        accept = req.headers.get("accept", ct)
        timeout_ms: int | None = None
        t = req.headers.get("speconn-timeout-ms")
        if t:
            try:
                timeout_ms = int(t)
            except ValueError:
                pass

        ctx = create_context_from_headers(req.headers, req.path, req.local_addr, req.remote_addr, timeout_ms)

        for interceptor in self._interceptors:
            try:
                result = interceptor.before(ctx, req)
                if isinstance(result, Awaitable):
                    await result
            except SpeconnError as e:
                ctx.cleanup()
                return _error_response(e.code, e.message)
            except Exception as e:
                ctx.cleanup()
                return _error_response(Code.INTERNAL, str(e))

        def _ef(v: str) -> str:
            s = v.lower()
            s = s[len("application/"):] if s.startswith("application/") else s
            s = s[len("connect+"):] if s.startswith("connect+") else s
            if s == "msgpack": return "msgpack"
            if s == "x-gron": return "gron"
            return "json"
        req_fmt = _ef(ct)
        res_fmt = _ef(accept)
        is_stream = "connect+" in ct
        status: int = 200
        resp_content_type: str = f"application/connect+{res_fmt}" if is_stream else f"application/{res_fmt}"
        resp_body: bytes = b""

        try:
            if is_stream and req.path in self._streams:
                req_codec, res_codec, fn = self._streams[req.path]
                req_obj = dispatch(req_codec, req.body, req_fmt)
                chunks: list[bytes] = []
                emit = lambda msg: chunks.append(encode_envelope(0, respond(res_codec, msg, res_fmt).body))
                stream_result = fn(ctx, req_obj, emit)
                if isinstance(stream_result, Awaitable):
                    await stream_result
                chunks.append(encode_envelope(FLAG_END_STREAM, b""))
                resp_body = b"".join(chunks)

            elif req.path in self._unary:
                req_codec, res_codec, fn = self._unary[req.path]
                req_obj = dispatch(req_codec, req.body, req_fmt)
                result = fn(ctx, req_obj)
                if isinstance(result, Awaitable):
                    result = await result
                resp_body = respond(res_codec, result, res_fmt).body

            else:
                ctx.cleanup()
                return _error_response(Code.NOT_FOUND, f"no route: {req.path}")

        except SpeconnError as e:
            if is_stream:
                resp_body = encode_envelope(FLAG_END_STREAM, e.encode(res_fmt))
            else:
                ctx.cleanup()
                return _error_response(e.code, e.message, res_fmt)

        except Exception as e:
            if is_stream:
                resp_body = encode_envelope(FLAG_END_STREAM, SpeconnError(Code.INTERNAL, str(e)).encode(res_fmt))
            else:
                ctx.cleanup()
                return _error_response(Code.INTERNAL, str(e), res_fmt)

        resp_headers: dict[str, str] = dict(ctx.response_headers)
        resp_headers["content-type"] = resp_content_type

        resp = SpeconnServerResponse(status=status, headers=resp_headers, body=resp_body)
        for interceptor in self._interceptors:
            result = interceptor.after(ctx, resp)
            if isinstance(result, Awaitable):
                await result

        ctx.cleanup()
        return resp


def _error_response(code: Code, message: str, fmt: str = "json") -> SpeconnServerResponse:
    status = code.http_status()
    body = SpeconnError(code, message).encode(fmt)
    return SpeconnServerResponse(status=status, headers={"content-type": f"application/{fmt}"}, body=body)

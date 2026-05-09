from __future__ import annotations

import dataclasses
from collections.abc import Awaitable, Callable, AsyncIterator
from typing import Protocol

from specodec import SpecCodec, dispatch, respond

from .context import SpeconnContext, create_context
from .envelope import encode_envelope, decode_envelope, FLAG_END_STREAM
from .error import Code, SpeconnError
from .format import extract_format, format_to_mime
from .transport import ServerChannel


@dataclasses.dataclass
class SpeconnServerRequest:
    path: str
    headers: dict[str, str]
    body: bytes
    local_addr: str | None = None
    remote_addr: str | None = None


@dataclasses.dataclass
class SpeconnServerResponse:
    status: int
    headers: dict[str, str]
    body: bytes


class Interceptor(Protocol):
    async def before(self, ctx: SpeconnContext, req: SpeconnServerRequest) -> None: ...
    async def after(self, ctx: SpeconnContext, resp: SpeconnServerResponse) -> None: ...


class SpeconnRouter:
    def __init__(self, interceptors: list[Interceptor] | None = None) -> None:
        self._unary: dict[str, tuple[SpecCodec, SpecCodec, Callable]] = {}
        self._streams: dict[str, tuple[SpecCodec, SpecCodec, Callable]] = {}
        self._client_streams: dict[str, tuple[SpecCodec, SpecCodec, Callable]] = {}
        self._bidi: dict[str, tuple[SpecCodec, SpecCodec, Callable]] = {}
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

    def client_stream(self, path: str, req_codec: SpecCodec, res_codec: SpecCodec) -> Callable:
        def decorator(fn: Callable) -> Callable:
            self._client_streams[path] = (req_codec, res_codec, fn)
            return fn
        return decorator

    def bidi(self, path: str, req_codec: SpecCodec, res_codec: SpecCodec) -> Callable:
        def decorator(fn: Callable) -> Callable:
            self._bidi[path] = (req_codec, res_codec, fn)
            return fn
        return decorator

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

        ctx = create_context(req.headers, req.path, req.local_addr, req.remote_addr, timeout_ms)

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

        req_fmt = extract_format(ct)
        res_fmt = extract_format(accept)
        is_stream = "connect+" in ct
        status: int = 200
        resp_content_type: str = format_to_mime(res_fmt, is_stream)
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

            elif is_stream and req.path in self._client_streams:
                req_codec, res_codec, fn = self._client_streams[req.path]
                messages = _parse_stream_body(req.body, req_codec, req_fmt)
                recv_fn = lambda: next(messages, None)
                result = fn(ctx, recv_fn)
                if isinstance(result, Awaitable):
                    result = await result
                resp_body = respond(res_codec, result, res_fmt).body
                is_stream = False
                resp_content_type = format_to_mime(res_fmt, False)

            elif is_stream and req.path in self._bidi:
                req_codec, res_codec, fn = self._bidi[req.path]
                messages = _parse_stream_body(req.body, req_codec, req_fmt)
                recv_fn = lambda: next(messages, None)
                chunks: list[bytes] = []
                emit = lambda msg: chunks.append(encode_envelope(0, respond(res_codec, msg, res_fmt).body))
                stream_result = fn(ctx, recv_fn, emit)
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

    async def handle_channel(
        self,
        channel: ServerChannel,
        path: str,
        headers: dict[str, str],
        local_addr: str | None = None,
        remote_addr: str | None = None,
    ) -> None:
        try:
            body = await channel.recv()
            if body is None:
                channel.close()
                return
            req = SpeconnServerRequest(
                path=path, headers=headers, body=body,
                local_addr=local_addr, remote_addr=remote_addr,
            )
            resp = await self.handle(req)
            channel.set_status(resp.status)
            channel.set_headers(list(resp.headers.items()))
            await channel.send(resp.body)
            await channel.close_write()
        except Exception:
            try:
                channel.set_status(500)
                channel.set_headers([("content-type", "application/json")])
                await channel.send(b"")
                await channel.close_write()
            except Exception:
                pass


def _parse_stream_body(body: bytes, codec: SpecCodec, fmt: str):
    offset = 0
    while offset < len(body):
        if offset + 5 > len(body):
            break
        flags = body[offset]
        length = int.from_bytes(body[offset + 1:offset + 5], "big")
        if offset + 5 + length > len(body):
            break
        payload = body[offset + 5:offset + 5 + length]
        offset += 5 + length
        if flags & FLAG_END_STREAM:
            break
        if payload:
            yield dispatch(codec, payload, fmt)


def _error_response(code: Code, message: str, fmt: str = "json") -> SpeconnServerResponse:
    status = code.http_status()
    body = SpeconnError(code, message).encode(fmt)
    return SpeconnServerResponse(status=status, headers={"content-type": f"application/{fmt}"}, body=body)

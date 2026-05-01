from __future__ import annotations

import dataclasses
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from specodec import SpecCodec, dispatch, respond

from .context import SpeconnContext, create_context_from_asgi_scope
from .envelope import encode_envelope, FLAG_END_STREAM
from .error import Code, SpeconnError



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
class SpeconnRequest:
    path: str
    headers: dict[str, str]
    body: bytes
    content_type: str


@dataclasses.dataclass
class SpeconnResponse:
    status: int
    headers: dict[str, str]
    body: bytes


class Interceptor(Protocol):
    async def before(self, ctx: SpeconnContext, req: SpeconnRequest) -> None: ...
    async def after(self, ctx: SpeconnContext, resp: SpeconnResponse) -> None: ...


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

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        if scope["type"] != "http":
            return

        path = scope.get("path", "")
        ct = "application/json"
        accept = "application/json"
        timeout_ms: int | None = None
        
        req_headers: dict[str, str] = {}
        for k, v in scope.get("headers", []):
            decoded_key = k.decode()
            decoded_val = v.decode()
            req_headers[decoded_key] = decoded_val
            if decoded_key.lower() == "content-type":
                ct = decoded_val
            if decoded_key.lower() == "accept":
                accept = decoded_val
            if decoded_key.lower() == "speconn-timeout-ms":
                try:
                    timeout_ms = int(decoded_val)
                except ValueError:
                    pass

        if scope.get("method") == "OPTIONS":
            await _send_response(send, 204, [], b"")
            return

        body = await _read_body(receive)

        ctx = create_context_from_asgi_scope(scope, timeout_ms)
        speconn_req = SpeconnRequest(path=path, headers=req_headers, body=body, content_type=ct)

        for interceptor in self._interceptors:
            try:
                result = interceptor.before(ctx, speconn_req)
                if isinstance(result, Awaitable):
                    await result
            except SpeconnError as e:
                ctx.cleanup()
                await _send_error(send, e.code, e.message)
                return
            except Exception as e:
                ctx.cleanup()
                await _send_error(send, Code.INTERNAL, str(e))
                return

        req_fmt = "msgpack" if "msgpack" in ct else "json"
        res_fmt = "msgpack" if "msgpack" in accept else "json"
        is_stream = "connect+" in ct
        status: int = 200
        resp_content_type: str = f"application/connect+{res_fmt}" if is_stream else f"application/{res_fmt}"
        resp_body: bytes = b""

        try:
            if is_stream and path in self._streams:
                req_codec, res_codec, fn = self._streams[path]
                req_obj = dispatch(req_codec, body, req_fmt)

                chunks: list[bytes] = []
                emit = lambda msg: chunks.append(encode_envelope(0, respond(res_codec, msg, res_fmt).body))

                stream_result = fn(ctx, req_obj, emit)
                if isinstance(stream_result, Awaitable):
                    await stream_result

                chunks.append(encode_envelope(FLAG_END_STREAM, b""))
                resp_body = b"".join(chunks)

            elif path in self._unary:
                req_codec, res_codec, fn = self._unary[path]
                req_obj = dispatch(req_codec, body, req_fmt)
                result = fn(ctx, req_obj)
                if isinstance(result, Awaitable):
                    result = await result
                resp_body = respond(res_codec, result, res_fmt).body
                
            else:
                ctx.cleanup()
                await _send_error(send, Code.NOT_FOUND, f"no route: {path}")
                return
                
        except RuntimeError as e:
            if "headers already sent" in str(e):
                if is_stream:
                    resp_body = encode_envelope(FLAG_END_STREAM, SpeconnError(Code.INTERNAL, str(e)).encode(res_fmt))
                else:
                    ctx.cleanup()
                    await _send_error(send, Code.INTERNAL, str(e), res_fmt)
                    return
            else:
                raise

        except SpeconnError as e:
            if is_stream:
                resp_body = encode_envelope(FLAG_END_STREAM, e.encode(res_fmt))
            else:
                ctx.cleanup()
                await _send_error(send, e.code, e.message, res_fmt)
                return

        except Exception as e:
            if is_stream:
                resp_body = encode_envelope(FLAG_END_STREAM, SpeconnError(Code.INTERNAL, str(e)).encode(res_fmt))
            else:
                ctx.cleanup()
                await _send_error(send, Code.INTERNAL, str(e), res_fmt)
                return

        speconn_resp = SpeconnResponse(status=status, headers=ctx.response_headers, body=resp_body)
        
        for interceptor in self._interceptors:
            result = interceptor.after(ctx, speconn_resp)
            if isinstance(result, Awaitable):
                await result

        final_headers: list[tuple[bytes, bytes]] = []
        for k, v in speconn_resp.headers.items():
            final_headers.append([k.encode(), v.encode()])
        final_headers.append([b"content-type", resp_content_type.encode()])
        
        await _send_response(send, speconn_resp.status, final_headers, resp_body)
        ctx.cleanup()


async def _send_response(send: Callable, status: int, headers: list[tuple[bytes, bytes]], body: bytes) -> None:
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


async def _send_error(send: Callable, code: Code, message: str, fmt: str = "json") -> None:
    status = code.http_status()
    body = SpeconnError(code, message).encode(fmt)
    ct = f"application/{fmt}".encode()
    await _send_response(send, status, [[b"content-type", ct]], body)
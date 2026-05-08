from __future__ import annotations
import dataclasses
from collections.abc import AsyncIterator
from typing import Generic, TypeVar

from specodec import dispatch, respond, SpecCodec
from .error import Code, SpeconnError
from .transport import SpeconnMessage

T = TypeVar("T")

@dataclasses.dataclass
class CallOptions:
    headers: dict[str, str] = dataclasses.field(default_factory=dict)
    timeout_ms: int | None = None

@dataclasses.dataclass
class Response(Generic[T]):
    msg: T
    headers: dict[str, str]
    trailers: dict[str, str]

class StreamResponse(Generic[T]):
    def __init__(self, headers: dict[str, str]) -> None:
        self.headers = headers
        self.trailers: dict[str, str] = {}
        self._msgs: list[T] = []

    def __aiter__(self) -> AsyncIterator[T]:
        return self._aiter_impl()
    async def _aiter_impl(self) -> AsyncIterator[T]:
        for msg in self._msgs: yield msg

    def _add_msg(self, msg: T) -> None: self._msgs.append(msg)
    def _set_trailers(self, trailers: dict[str, str]) -> None: self.trailers = trailers

def _split_headers_trailers(raw_headers: list[tuple[str, str]]) -> tuple[dict[str, str], dict[str, str]]:
    headers: dict[str, str] = {}
    trailers: dict[str, str] = {}
    for k, v in raw_headers:
        if k.lower().startswith("trailer-"): trailers[k[8:]] = v
        else: headers[k.lower()] = v
    return headers, trailers

def _parse_error(status: int, body: bytes | None) -> SpeconnError:
    if body: return SpeconnError.decode(body, "json")
    return SpeconnError(Code.from_http_status(status), f"HTTP {status}")

def _create_default_transport(base_url: str):
    try:
        from .transport_httpx import HttpxChannel
        return HttpxChannel(base_url)
    except ImportError:
        raise ImportError("No HTTP transport available. Install httpx: pip install httpx")

def _get_content_type(headers: dict[str, str]) -> str: return headers.get("content-type", "application/json")
def _get_accept(headers: dict[str, str]) -> str: return headers.get("accept", headers.get("content-type", "application/json"))
def _extract_format(mime: str) -> str:
    ct = mime.lower()
    ct = ct[len("application/"):] if ct.startswith("application/") else ct
    ct = ct[len("connect+"):] if ct.startswith("connect+") else ct
    if ct == "msgpack": return "msgpack"
    if ct == "x-gron": return "gron"
    return "json"
def _format_to_mime(fmt: str, stream: bool = False) -> str:
    sub = "msgpack" if fmt == "msgpack" else "x-gron" if fmt == "gron" else "json"
    return f"application/connect+{sub}" if stream else f"application/{sub}"

class SpeconnClient:
    def __init__(self, base_url: str, path: str, transport=None) -> None:
        self._path = path
        self._transport = transport or _create_default_transport(base_url)

    async def call(self, req_codec: SpecCodec, req, res_codec: SpecCodec, options: CallOptions = CallOptions()) -> Response:
        h = options.headers
        req_fmt = _extract_format(_get_content_type(h))
        res_fmt = _extract_format(_get_accept(h))
        body = respond(req_codec, req, req_fmt).body
        req_headers: list[tuple[str, str]] = [("content-type", _format_to_mime(req_fmt, False)), ("accept", _format_to_mime(res_fmt, False))]
        for k, v in h.items():
            if k.lower() not in ("content-type", "accept"): req_headers.append((k, v))
        if options.timeout_ms: req_headers.append(("speconn-timeout-ms", str(options.timeout_ms)))

        await self._transport.send(SpeconnMessage(path=self._path, headers=req_headers, body=body))
        if self._transport.response_status >= 400:
            err_body = await self._transport.recv()
            raise _parse_error(self._transport.response_status, err_body)

        headers, trailers = _split_headers_trailers(self._transport.response_headers)
        resp_body = await self._transport.recv()
        if resp_body is None: raise SpeconnError(Code.INTERNAL, "empty response")
        msg = dispatch(res_codec, resp_body, res_fmt)
        return Response(msg=msg, headers=headers, trailers=trailers)

    async def stream(self, req_codec: SpecCodec, req, res_codec: SpecCodec, options: CallOptions = CallOptions()) -> StreamResponse:
        h = options.headers.copy()
        req_fmt = _extract_format(_get_content_type(h))
        res_fmt = _extract_format(_get_accept(h))
        if "connect-protocol-version" not in {k.lower() for k in h}: h["connect-protocol-version"] = "1"

        body = respond(req_codec, req, req_fmt).body
        req_headers: list[tuple[str, str]] = [("content-type", _format_to_mime(req_fmt, True)), ("accept", _format_to_mime(res_fmt, True))]
        for k, v in h.items():
            if k.lower() not in ("content-type", "accept"): req_headers.append((k, v))

        await self._transport.send(SpeconnMessage(path=self._path, headers=req_headers, body=body))
        if self._transport.response_status >= 400:
            err_body = await self._transport.recv()
            raise _parse_error(self._transport.response_status, err_body)

        headers, trailers = _split_headers_trailers(self._transport.response_headers)
        stream_resp = StreamResponse(headers=headers)

        while True:
            payload = await self._transport.recv()
            if payload is None: break
            msg = dispatch(res_codec, payload, res_fmt)
            stream_resp._add_msg(msg)

        stream_resp._set_trailers(trailers)
        return stream_resp

from __future__ import annotations

import dataclasses
from collections.abc import AsyncIterator
from typing import Generic, TypeVar

from specodec import dispatch, respond, SpecCodec

from .envelope import decode_envelope, FLAG_END_STREAM
from .error import Code, SpeconnError
from .transport import HttpRequest, HttpResponse


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
        self._iter_done = False

    def __aiter__(self) -> AsyncIterator[T]:
        return self._aiter_impl()

    async def _aiter_impl(self) -> AsyncIterator[T]:
        for msg in self._msgs:
            yield msg
        self._iter_done = True

    def _add_msg(self, msg: T) -> None:
        self._msgs.append(msg)

    def _set_trailers(self, trailers: dict[str, str]) -> None:
        self.trailers = trailers


def _split_headers_trailers(raw_headers: list[tuple[str, str]]) -> tuple[dict[str, str], dict[str, str]]:
    headers: dict[str, str] = {}
    trailers: dict[str, str] = {}
    for k, v in raw_headers:
        if k.lower().startswith("trailer-"):
            trailers[k[8:]] = v
        else:
            headers[k.lower()] = v
    return headers, trailers


def _parse_error(resp: HttpResponse) -> SpeconnError:
    if resp.body:
        return SpeconnError.decode(resp.body, "json")
    return SpeconnError(Code.from_http_status(resp.status), f"HTTP {resp.status}")


def _create_default_transport():
    try:
        from .transport_httpx import HttpxTransport
        return HttpxTransport()
    except ImportError:
        raise ImportError("No HTTP transport available. Install httpx: pip install httpx")


def _get_content_type(headers: dict[str, str]) -> str:
    return headers.get("content-type", "application/json")


def _get_accept(headers: dict[str, str]) -> str:
    return headers.get("accept", headers.get("content-type", "application/json"))


def _extract_format(mime: str) -> str:
    return "msgpack" if "msgpack" in mime else "json"


class SpeconnClient:
    def __init__(self, base_url: str, path: str, transport=None) -> None:
        self._url = base_url.rstrip("/") + path
        self._transport = transport or _create_default_transport()

    async def call(
        self,
        req_codec: SpecCodec,
        req: object,
        res_codec: SpecCodec,
        options: CallOptions = CallOptions(),
    ) -> Response[object]:
        h = options.headers
        req_fmt = _extract_format(_get_content_type(h))
        res_fmt = _extract_format(_get_accept(h))

        body = respond(req_codec, req, req_fmt).body

        req_headers = list(h.items())
        resp = await self._transport.send(
            HttpRequest(url=self._url, method="POST", headers=req_headers, body=body)
        )
        if resp.status >= 400:
            raise _parse_error(resp)

        headers, trailers = _split_headers_trailers(resp.headers)
        msg = dispatch(res_codec, resp.body, res_fmt)
        return Response(msg=msg, headers=headers, trailers=trailers)

    async def stream(
        self,
        req_codec: SpecCodec,
        req: object,
        res_codec: SpecCodec,
        options: CallOptions = CallOptions(),
    ) -> StreamResponse[object]:
        h = options.headers.copy()
        req_fmt = _extract_format(_get_content_type(h))
        res_fmt = _extract_format(_get_accept(h))

        if "connect-protocol-version" not in h:
            h["connect-protocol-version"] = "1"

        body = respond(req_codec, req, req_fmt).body

        req_headers = list(h.items())
        resp = await self._transport.send(
            HttpRequest(url=self._url, method="POST", headers=req_headers, body=body)
        )
        if resp.status >= 400:
            raise _parse_error(resp)

        headers, trailers = _split_headers_trailers(resp.headers)
        stream_resp = StreamResponse(headers=headers)

        pos = 0
        buf = resp.body
        while pos < len(buf):
            if len(buf) - pos < 5:
                break
            flags, payload = decode_envelope(buf[pos:])
            pos += 5 + len(payload)
            if flags & FLAG_END_STREAM:
                if payload:
                    raise SpeconnError.decode(payload, res_fmt)
                break
            msg = dispatch(res_codec, payload, res_fmt)
            stream_resp._add_msg(msg)

        stream_resp._set_trailers(trailers)
        return stream_resp

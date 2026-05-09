from __future__ import annotations

import dataclasses
from collections.abc import AsyncIterator, AsyncGenerator
from typing import Generic, TypeVar

from specodec import dispatch, respond, SpecCodec
from .error import Code, SpeconnError
from .format import extract_format, format_to_mime
from .transport import SpeconnChannel, SpeconnTransport

T = TypeVar("T")
TRes = TypeVar("TRes")


def split_headers_trailers(
    raw_headers: list[tuple[str, str]],
) -> tuple[dict[str, str], dict[str, str]]:
    headers: dict[str, str] = {}
    trailers: dict[str, str] = {}
    for k, v in raw_headers:
        if k.lower().startswith("trailer-"):
            trailers[k[8:].lower()] = v
        else:
            headers[k.lower()] = v
    return headers, trailers


def _get_header(headers: list[tuple[str, str]], name: str) -> str:
    lower = name.lower()
    for k, v in headers:
        if k.lower() == lower:
            return v
    return ""


def _req_fmt(options: "CallOptions") -> str:
    ct = _get_header(options.headers, "content-type") or "application/json"
    return extract_format(ct)


def _res_fmt(options: "CallOptions") -> str:
    accept = _get_header(options.headers, "accept") or "application/json"
    return extract_format(accept)


def _base_headers(options: "CallOptions") -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    for k, v in options.headers:
        if k.lower() not in ("content-type", "accept"):
            result.append((k, v))
    return result


def _stream_headers(
    req_fmt: str, res_fmt: str, options: "CallOptions"
) -> list[tuple[str, str]]:
    headers: list[tuple[str, str]] = [
        ("content-type", format_to_mime(req_fmt, stream=True)),
        ("accept", format_to_mime(res_fmt, stream=True)),
    ]
    lower_keys = {k.lower() for k, _ in options.headers}
    if "connect-protocol-version" not in lower_keys:
        headers.append(("connect-protocol-version", "1"))
    headers.extend(_base_headers(options))
    return headers


def _unary_headers(
    req_fmt: str, res_fmt: str, options: "CallOptions"
) -> list[tuple[str, str]]:
    headers: list[tuple[str, str]] = [
        ("content-type", format_to_mime(req_fmt, stream=False)),
        ("accept", format_to_mime(res_fmt, stream=False)),
    ]
    headers.extend(_base_headers(options))
    return headers


@dataclasses.dataclass
class CallOptions:
    headers: list[tuple[str, str]] = dataclasses.field(default_factory=list)
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
        self._gen: AsyncGenerator[T, None] | None = None

    def __aiter__(self) -> AsyncIterator[T]:
        if self._gen is not None:
            return self._gen
        return self._empty()

    async def _empty(self) -> AsyncIterator[T]:
        return
        yield

    def _set_gen(self, gen: AsyncGenerator[T, None]) -> None:
        self._gen = gen

    def _set_trailers(self, trailers: dict[str, str]) -> None:
        self.trailers = trailers


class ClientStreamHandle(Generic[T, TRes]):
    def __init__(
        self,
        ch: SpeconnChannel,
        req_codec: SpecCodec,
        req_fmt: str,
        res_codec: SpecCodec,
        res_fmt: str,
    ) -> None:
        self._ch = ch
        self._req_codec = req_codec
        self._req_fmt = req_fmt
        self._res_codec = res_codec
        self._res_fmt = res_fmt

    async def send(self, req: T) -> None:
        body = respond(self._req_codec, req, self._req_fmt).body
        await self._ch.send(body)

    async def close_and_receive(self) -> Response[TRes]:
        try:
            await self._ch.close_write()

            if self._ch.response_status >= 400:
                err_body = await self._ch.recv()
                raise SpeconnError(
                    Code.from_http_status(self._ch.response_status),
                    f"HTTP {self._ch.response_status}",
                )

            headers, trailers = split_headers_trailers(self._ch.response_headers)
            body = await self._ch.recv()
            if body is None:
                raise SpeconnError(Code.INTERNAL, "empty response")

            return Response(
                msg=dispatch(self._res_codec, body, self._res_fmt),
                headers=headers,
                trailers=trailers,
            )
        finally:
            self._ch.close()


class BidiStreamHandle(Generic[T, TRes]):
    def __init__(
        self,
        ch: SpeconnChannel,
        req_codec: SpecCodec,
        req_fmt: str,
        res_codec: SpecCodec,
        res_fmt: str,
    ) -> None:
        self._ch = ch
        self._req_codec = req_codec
        self._req_fmt = req_fmt
        self._res_codec = res_codec
        self._res_fmt = res_fmt
        self._gen: AsyncGenerator[TRes, None] | None = None

    async def send(self, req: T) -> None:
        body = respond(self._req_codec, req, self._req_fmt).body
        await self._ch.send(body)

    async def close_write(self) -> None:
        await self._ch.close_write()

    @property
    def response_headers(self) -> dict[str, str]:
        headers, _ = split_headers_trailers(self._ch.response_headers)
        return headers

    @property
    def response_status(self) -> int:
        return self._ch.response_status

    def __aiter__(self) -> AsyncIterator[TRes]:
        return self._iter_impl()

    async def _iter_impl(self) -> AsyncGenerator[TRes, None]:
        try:
            while True:
                payload = await self._ch.recv()
                if payload is None:
                    break
                yield dispatch(self._res_codec, payload, self._res_fmt)
        finally:
            self._ch.close()

    async def close(self) -> None:
        self._ch.close()


class SpeconnClient:
    def __init__(self, path: str, transport: SpeconnTransport) -> None:
        self._path = path
        self._transport = transport

    async def call(
        self,
        req_codec: SpecCodec,
        req,
        res_codec: SpecCodec,
        options: CallOptions = CallOptions(),
    ) -> Response:
        req_fmt = _req_fmt(options)
        res_fmt = _res_fmt(options)
        ch = self._transport.open(self._path, _unary_headers(req_fmt, res_fmt, options))

        try:
            await ch.send(respond(req_codec, req, req_fmt).body)
            await ch.close_write()

            if ch.response_status >= 400:
                err_body = await ch.recv()
                raise SpeconnError(
                    Code.from_http_status(ch.response_status),
                    f"HTTP {ch.response_status}",
                )

            headers, trailers = split_headers_trailers(ch.response_headers)
            body = await ch.recv()
            if body is None:
                raise SpeconnError(Code.INTERNAL, "empty response")

            return Response(
                msg=dispatch(res_codec, body, res_fmt),
                headers=headers,
                trailers=trailers,
            )
        finally:
            ch.close()

    async def server_stream(
        self,
        req_codec: SpecCodec,
        req,
        res_codec: SpecCodec,
        options: CallOptions = CallOptions(),
    ) -> StreamResponse:
        req_fmt = _req_fmt(options)
        res_fmt = _res_fmt(options)
        ch = self._transport.open(
            self._path, _stream_headers(req_fmt, res_fmt, options)
        )

        await ch.send(respond(req_codec, req, req_fmt).body)
        await ch.close_write()

        if ch.response_status >= 400:
            err_body = await ch.recv()
            ch.close()
            raise SpeconnError(
                Code.from_http_status(ch.response_status),
                f"HTTP {ch.response_status}",
            )

        headers, trailers = split_headers_trailers(ch.response_headers)
        resp = StreamResponse(headers)
        resp._set_trailers(trailers)

        async def _gen() -> AsyncGenerator:
            try:
                while True:
                    payload = await ch.recv()
                    if payload is None:
                        break
                    yield dispatch(res_codec, payload, res_fmt)
            finally:
                ch.close()

        resp._set_gen(_gen())
        return resp

    async def client_stream(
        self,
        req_codec: SpecCodec,
        res_codec: SpecCodec,
        options: CallOptions = CallOptions(),
    ) -> ClientStreamHandle:
        req_fmt = _req_fmt(options)
        res_fmt = _res_fmt(options)
        ch = self._transport.open(
            self._path, _stream_headers(req_fmt, res_fmt, options)
        )
        return ClientStreamHandle(ch, req_codec, req_fmt, res_codec, res_fmt)

    async def bidi(
        self,
        req_codec: SpecCodec,
        res_codec: SpecCodec,
        options: CallOptions = CallOptions(),
    ) -> BidiStreamHandle:
        req_fmt = _req_fmt(options)
        res_fmt = _res_fmt(options)
        ch = self._transport.open(
            self._path, _stream_headers(req_fmt, res_fmt, options)
        )
        return BidiStreamHandle(ch, req_codec, req_fmt, res_codec, res_fmt)

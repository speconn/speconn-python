from __future__ import annotations

import asyncio
from typing import Protocol, runtime_checkable

from .envelope import FLAG_END_STREAM, encode_envelope, decode_envelope


class HttpxTransport:
    def __init__(self, base_url: str, client=None) -> None:
        import httpx
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.AsyncClient()

    def open(self, path: str, headers: list[tuple[str, str]]) -> "HttpxChannel":
        return HttpxChannel(
            base_url=self._base_url,
            client=self._client,
            path=path,
            headers=headers,
        )


class HttpxChannel:
    def __init__(
        self,
        base_url: str,
        client,
        path: str,
        headers: list[tuple[str, str]],
    ) -> None:
        self._base_url = base_url
        self._client = client
        self._path = path
        self._headers = headers
        self._is_streaming = any(
            "connect+" in v for k, v in headers if k.lower() == "content-type"
        )
        self._status: int = 0
        self._resp_headers: list[tuple[str, str]] = []
        self._write_buf: list[bytes] = []
        self._write_closed = False
        self._resp = None
        self._reader_iter = None
        self._buf = b""
        self._resp_ready = asyncio.Event()
        self._http_started = False

    @property
    def response_status(self) -> int:
        if not self._resp_ready.is_set():
            raise RuntimeError("response not ready yet; call close_write() and recv() first")
        return self._status

    @property
    def response_headers(self) -> list[tuple[str, str]]:
        if not self._resp_ready.is_set():
            raise RuntimeError("response not ready yet; call close_write() and recv() first")
        return self._resp_headers

    async def send(self, body: bytes) -> None:
        if self._write_closed:
            raise RuntimeError("write side already closed")
        self._write_buf.append(body)

    async def close_write(self) -> None:
        if self._write_closed:
            return
        self._write_closed = True

        if not self._is_streaming:
            full_body = b"".join(self._write_buf)
            await self._do_unary_request(full_body)
        else:
            await self._do_stream_request()

    async def recv(self) -> bytes | None:
        if not self._resp_ready.is_set():
            await self._resp_ready.wait()

        if self._is_streaming:
            return await self._recv_envelope()

        if not self._buf:
            return None
        d = self._buf
        self._buf = b""
        return d

    def close(self) -> None:
        if self._resp is not None:
            try:
                asyncio.ensure_future(self._resp.aclose())
            except Exception:
                pass
            self._resp = None
        self._reader_iter = None

    async def _do_unary_request(self, body: bytes) -> None:
        url = self._base_url + self._path
        h = {k: v for k, v in self._headers}
        req = self._client.build_request("POST", url, content=body, headers=h)
        self._resp = await self._client.send(req, stream=True)
        self._status = self._resp.status_code
        self._resp_headers = list(self._resp.headers.items())
        await self._resp.aread()
        self._buf = self._resp.content
        self._resp_ready.set()

    async def _do_stream_request(self) -> None:
        url = self._base_url + self._path
        h = {k: v for k, v in self._headers}

        async def body_gen():
            while True:
                while not self._write_buf:
                    if self._write_closed:
                        return
                    await asyncio.sleep(0.001)
                while self._write_buf:
                    yield self._write_buf.pop(0)
                if self._write_closed:
                    return

        req = self._client.build_request(
            "POST", url, content=body_gen(), headers=h
        )
        self._resp = await self._client.send(req, stream=True)
        self._status = self._resp.status_code
        self._resp_headers = list(self._resp.headers.items())
        self._reader_iter = self._resp.aiter_bytes()
        self._buf = b""
        self._resp_ready.set()

    async def _recv_envelope(self) -> bytes | None:
        while True:
            if len(self._buf) >= 5:
                flags = self._buf[0]
                length = int.from_bytes(self._buf[1:5], "big")
                if len(self._buf) >= 5 + length:
                    payload = self._buf[5 : 5 + length]
                    self._buf = self._buf[5 + length :]
                    if flags & FLAG_END_STREAM:
                        self._reader_iter = None
                        return payload if payload else None
                    return payload
            if self._reader_iter is None:
                return None
            try:
                chunk = await self._reader_iter.__anext__()
                self._buf += chunk
            except StopAsyncIteration:
                self._reader_iter = None
                if self._buf:
                    result = self._buf
                    self._buf = b""
                    return result
                if self._resp is not None:
                    await self._resp.aclose()
                    self._resp = None
                return None

from __future__ import annotations

from collections.abc import Callable

from .transport import SpeconnChannel


class AsyncioServerChannel(SpeconnChannel):
    def __init__(
        self,
        reader: "asyncio.StreamReader",
        writer: "asyncio.StreamWriter",
        path: str,
        request_headers: dict[str, str],
        local_addr: str | None = None,
        remote_addr: str | None = None,
    ) -> None:
        self._reader = reader
        self._writer = writer
        self.path = path
        self.request_headers = request_headers
        self.local_addr = local_addr
        self.remote_addr = remote_addr
        self._status: int = 200
        self._headers: list[tuple[str, str]] = []
        self._req_read: bool = False
        self._head_sent: bool = False
        self._closed: bool = False

    @property
    def response_status(self) -> int:
        return self._status

    @property
    def response_headers(self) -> list[tuple[str, str]]:
        return list(self._headers)

    def set_status(self, status: int) -> None:
        self._status = status

    def set_headers(self, headers: list[tuple[str, str]]) -> None:
        self._headers = headers

    async def send(self, body: bytes) -> None:
        if self._closed:
            return
        if not self._head_sent:
            self._write_head()
        self._writer.write(body)
        await self._writer.drain()

    async def close_write(self) -> None:
        if self._closed:
            return
        if not self._head_sent:
            self._write_head()
        self._writer.close()
        self._closed = True

    async def recv(self) -> bytes | None:
        if self._req_read:
            return None
        self._req_read = True
        content_length = int(self.request_headers.get("content-length", "0"))
        if content_length > 0:
            return await self._reader.readexactly(content_length)
        return b""

    def close(self) -> None:
        if not self._closed:
            if not self._head_sent:
                self._write_head()
            self._writer.close()
            self._closed = True

    def _write_head(self) -> None:
        import asyncio
        status_text = {200: "OK", 400: "Bad Request", 404: "Not Found", 500: "Internal Server Error"}.get(self._status, "OK")
        self._writer.write(f"HTTP/1.1 {self._status} {status_text}\r\n".encode())
        for k, v in self._headers:
            self._writer.write(f"{k}: {v}\r\n".encode())
        self._head_sent = True


class ASGIServerChannel(SpeconnChannel):
    def __init__(
        self,
        receive: Callable,
        send: Callable,
        path: str,
        request_headers: dict[str, str],
        local_addr: str | None = None,
        remote_addr: str | None = None,
    ) -> None:
        self._receive = receive
        self._send = send
        self.path = path
        self.request_headers = request_headers
        self.local_addr = local_addr
        self.remote_addr = remote_addr
        self._status: int = 200
        self._headers: list[tuple[str, str]] = []
        self._req_read: bool = False
        self._head_sent: bool = False
        self._closed: bool = False

    @property
    def response_status(self) -> int:
        return self._status

    @property
    def response_headers(self) -> list[tuple[str, str]]:
        return list(self._headers)

    def set_status(self, status: int) -> None:
        self._status = status

    def set_headers(self, headers: list[tuple[str, str]]) -> None:
        self._headers = headers

    async def send(self, body: bytes) -> None:
        if self._closed:
            return
        if not self._head_sent:
            await self._send_head()
        await self._send({"type": "http.response.body", "body": body, "more_body": True})

    async def close_write(self) -> None:
        if self._closed:
            return
        if not self._head_sent:
            await self._send_head()
        await self._send({"type": "http.response.body", "body": b"", "more_body": False})
        self._closed = True

    async def recv(self) -> bytes | None:
        if self._req_read:
            return None
        self._req_read = True
        body = b""
        while True:
            event = await self._receive()
            if event["type"] == "http.request":
                body += event.get("body", b"")
                if not event.get("more", False):
                    break
        return body

    def close(self) -> None:
        self._closed = True

    async def _send_head(self) -> None:
        raw_headers = [(k.encode(), v.encode()) for k, v in self._headers]
        await self._send({"type": "http.response.start", "status": self._status, "headers": raw_headers})
        self._head_sent = True

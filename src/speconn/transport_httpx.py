from __future__ import annotations
from .transport import SpeconnMessage, HttpResponse
from .envelope import FLAG_END_STREAM

class HttpxChannel:
    def __init__(self, base_url: str, client=None) -> None:
        import httpx
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.AsyncClient()
        self._status = 0
        self._headers: list[tuple[str, str]] = []
        self._buf = b""
        self._iter = None
        self._streaming = False

    @property
    def response_status(self) -> int: return self._status
    @property
    def response_headers(self) -> list[tuple[str, str]]: return self._headers

    async def send(self, msg: SpeconnMessage) -> None:
        url = self._base_url + msg.path
        headers = {k: v for k, v in msg.headers}
        self._resp = await self._client.send(
            self._client.build_request("POST", url, content=msg.body, headers=headers), stream=True)
        await self._resp.aread()
        self._status = self._resp.status_code
        self._headers = list(self._resp.headers.items())
        ct = self._resp.headers.get("content-type", "")
        self._streaming = ct.startswith("application/connect+")
        if not self._streaming and not ct.startswith("application/"):
            raise ValueError(f"unsupported content-type: {ct}")
        if self._streaming:
            self._iter = self._resp.aiter_bytes()
            self._buf = b""
        else:
            self._buf = self._resp.content

    async def recv(self) -> bytes | None:
        if self._streaming:
            return await self._recv_envelope()
        if not self._buf:
            return None
        d = self._buf
        self._buf = b""
        return d

    async def _recv_envelope(self) -> bytes | None:
        while True:
            if len(self._buf) >= 5:
                flags = self._buf[0]
                length = int.from_bytes(self._buf[1:5], 'big')
                if len(self._buf) >= 5 + length:
                    payload = self._buf[5:5+length]
                    self._buf = self._buf[5+length:]
                    if flags & FLAG_END_STREAM:
                        self._iter = None
                        return payload if payload else None
                    return payload
            try:
                chunk = await self._iter.__anext__()
                self._buf += chunk
            except StopAsyncIteration:
                self._iter = None
                if self._buf:
                    result = self._buf
                    self._buf = b""
                    return result
                return None

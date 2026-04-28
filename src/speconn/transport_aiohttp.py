from __future__ import annotations

from .transport import HttpRequest, HttpResponse


class AiohttpTransport:
    def __init__(self, session=None) -> None:
        import aiohttp
        self._session = session
        self._owns_session = session is None
        if self._owns_session:
            self._session = aiohttp.ClientSession()

    async def send(self, request: HttpRequest) -> HttpResponse:
        headers = {k: v for k, v in request.headers}
        resp = await self._session.request(
            request.method,
            request.url,
            data=request.body,
            headers=headers,
        )
        body = await resp.read()
        return HttpResponse(status=resp.status, body=body)

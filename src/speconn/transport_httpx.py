from __future__ import annotations

from .transport import HttpRequest, HttpResponse


class HttpxTransport:
    def __init__(self, client=None) -> None:
        import httpx
        self._client = client or httpx.AsyncClient()

    async def send(self, request: HttpRequest) -> HttpResponse:
        headers = {k: v for k, v in request.headers}
        resp = await self._client.request(
            request.method,
            request.url,
            content=request.body,
            headers=headers,
        )
        return HttpResponse(status=resp.status_code, body=resp.content)

from __future__ import annotations

from .transport import SpeconnMessage, HttpResponse


class PyqwestChannel:
    def __init__(self, base_url: str, client=None) -> None:
        import pyqwest
        self._base_url = base_url.rstrip("/")
        self._client = client or pyqwest.Client()

    async def send(self, msg: SpeconnMessage) -> HttpResponse:
        url = self._base_url + msg.path
        headers = {k: v for k, v in msg.headers}
        resp = await self._client.request(
            "POST",
            url,
            content=msg.body,
            headers=headers,
        )
        return HttpResponse(
            status=resp.status_code,
            headers=list(resp.headers.items()),
            body=resp.content,
        )


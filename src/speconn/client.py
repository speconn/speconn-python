from __future__ import annotations

from specodec import dispatch, respond, SpecCodec

from .envelope import decode_envelope, FLAG_END_STREAM
from .error import Code, SpeconnError
from .transport import HttpRequest, HttpResponse



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
        *,
        headers: dict[str, str] | None = None,
    ) -> object:
        h = headers or {}
        req_fmt = _extract_format(_get_content_type(h))
        res_fmt = _extract_format(_get_accept(h))

        body = respond(req_codec, req, req_fmt).body

        req_headers = list(h.items())
        resp = await self._transport.send(
            HttpRequest(url=self._url, method="POST", headers=req_headers, body=body)
        )
        if resp.status >= 400:
            raise _parse_error(resp)
        return dispatch(res_codec, resp.body, res_fmt)

    async def stream(
        self,
        req_codec: SpecCodec,
        req: object,
        res_codec: SpecCodec,
        *,
        headers: dict[str, str] | None = None,
    ) -> list[object]:
        h = headers or {}
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

        results: list[object] = []
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
            results.append(dispatch(res_codec, payload, res_fmt))
        return results

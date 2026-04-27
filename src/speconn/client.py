from __future__ import annotations

import json
import dataclasses

from .envelope import decode_envelope, FLAG_END_STREAM
from .error import Code, SpeconnError
from .transport import Transport, TransportResponse, _create_default_transport


def _to_dict(obj: object) -> object:
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return dataclasses.asdict(obj)
    if isinstance(obj, dict):
        return obj
    return obj


def _instantiate(cls: type, data: dict) -> object:
    if dataclasses.is_dataclass(cls):
        return cls(**data)
    return data


def _parse_error(resp: TransportResponse) -> SpeconnError:
    try:
        err = json.loads(resp.body)
    except Exception:
        return SpeconnError(
            Code.from_http_status(resp.status), f"HTTP {resp.status}"
        )
    return SpeconnError(
        Code.from_str(err.get("code", "unknown")),
        err.get("message", ""),
    )


class SpeconnClient:
    def __init__(self, base_url: str, transport: Transport | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._transport = transport or _create_default_transport()

    async def call(self, path: str, req: object, res_type: type) -> object:
        url = self._base_url + path
        body = json.dumps(_to_dict(req) if req else {}).encode()
        resp = await self._transport.post(url, "application/json", body, {})

        if resp.status >= 400:
            raise _parse_error(resp)

        data = json.loads(resp.body)
        return _instantiate(res_type, data)

    async def stream(self, path: str, req: object, res_type: type) -> list[object]:
        url = self._base_url + path
        body = json.dumps(_to_dict(req) if req else {}).encode()
        resp = await self._transport.post(
            url,
            "application/connect+json",
            body,
            {"connect-protocol-version": "1"},
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
                trailer = json.loads(payload)
                error = trailer.get("error")
                if error:
                    raise SpeconnError(
                        Code.from_str(error.get("code", "unknown")),
                        error.get("message", ""),
                    )
                break

            msg = json.loads(payload)
            results.append(_instantiate(res_type, msg))

        return results

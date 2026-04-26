"""Speconn Python runtime — JSON unary RPC."""

from __future__ import annotations

import json
import dataclasses
from typing import Any, Callable, TypeVar

T = TypeVar("T")

CODE_TO_STATUS = {
    "invalid_argument": 400,
    "failed_precondition": 400,
    "out_of_range": 400,
    "unauthenticated": 401,
    "permission_denied": 403,
    "not_found": 404,
    "already_exists": 409,
    "aborted": 409,
    "resource_exhausted": 429,
    "canceled": 499,
    "unimplemented": 501,
    "unavailable": 503,
    "deadline_exceeded": 504,
}


class SpeconnError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


def unary_handler(req_type: type[T], res_type: type, fn: Callable[[T], Any]) -> dict:
    """Create a Speconn route descriptor."""

    async def asgi_handler(scope: dict, receive: Callable, send: Callable) -> None:
        headers = {}
        body = b""
        while True:
            event = await receive()
            if event["type"] == "http.request":
                body += event.get("body", b"")
                if not event.get("more", False):
                    break

        try:
            req = json.loads(body) if body else {}
            if dataclasses.is_dataclass(req_type):
                typed_req = req_type(**req)
            else:
                typed_req = req  # type: ignore
            result = fn(typed_req)
            if hasattr(result, "__await__"):
                result = await result
            res_body = json.dumps(dataclasses.asdict(result) if dataclasses.is_dataclass(result) else result).encode()
            await send({"type": "http.response.start", "status": 200, "headers": [[b"content-type", b"application/json"]]})
            await send({"type": "http.response.body", "body": res_body})
        except SpeconnError as e:
            status = CODE_TO_STATUS.get(e.code, 500)
            err_body = json.dumps({"code": e.code, "message": e.message}).encode()
            await send({"type": "http.response.start", "status": status, "headers": [[b"content-type", b"application/json"]]})
            await send({"type": "http.response.body", "body": err_body})
        except Exception as e:
            err_body = json.dumps({"code": "internal", "message": str(e)}).encode()
            await send({"type": "http.response.start", "status": 500, "headers": [[b"content-type", b"application/json"]]})
            await send({"type": "http.response.body", "body": err_body})

    return {"handler": asgi_handler}


class SpeconnRouter:
    def __init__(self):
        self._routes: dict[str, Callable] = {}

    def unary(self, path: str, req_type: type, res_type: type):
        def decorator(fn: Callable):
            route = unary_handler(req_type, res_type, fn)
            self._routes[path] = route["handler"]
            return fn
        return decorator

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        if scope["type"] != "http":
            return

        path = scope.get("path", "")
        handler = self._routes.get(path)
        if handler is None:
            await send({"type": "http.response.start", "status": 404, "headers": [[b"content-type", b"application/json"]]})
            await send({"type": "http.response.body", "body": b'{"code":"not_found","message":"no route"}'})
            return
        await handler(scope, receive, send)

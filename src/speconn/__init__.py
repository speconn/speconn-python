"""Speconn Python runtime — JSON/MsgPack unary + Connect streaming RPC."""

from __future__ import annotations

from .error import Code, SpeconnError, CODE_TO_STATUS
from .envelope import FLAG_COMPRESSED, FLAG_END_STREAM, encode_envelope, decode_envelope
from .transport import SpeconnTransport, HttpRequest, HttpResponse
from .transport_httpx import HttpxTransport
from .transport_pyqwest import PyqwestTransport
from .client import SpeconnClient
from .router import SpeconnRouter, SpeconnRequest, SpeconnResponse, Interceptor
from .context import SpeconnContext, create_context, create_context_from_asgi_scope
from .abort_signal import AbortSignal, create_abort_signal_with_timeout
from .context_key import ContextKey, set_value, get_value, delete_value, UserKey, RequestIDKey, UserIDKey

from specodec import (
    SpecCodec,
    JsonReader,
    JsonWriter,
    MsgPackReader,
    MsgPackWriter,
    dispatch,
    respond,
)

__all__ = [
    "Code",
    "SpeconnError",
    "CODE_TO_STATUS",
    "FLAG_COMPRESSED",
    "FLAG_END_STREAM",
    "encode_envelope",
    "decode_envelope",
    "SpeconnTransport",
    "HttpRequest",
    "HttpResponse",
    "HttpxTransport",
    "PyqwestTransport",
    "SpecCodec",
    "JsonReader",
    "JsonWriter",
    "MsgPackReader",
    "MsgPackWriter",
    "dispatch",
    "respond",
    "SpeconnClient",
    "SpeconnRouter",
    "SpeconnContext",
    "SpeconnRequest",
    "SpeconnResponse",
    "Interceptor",
    "AbortSignal",
    "create_abort_signal_with_timeout",
    "create_context",
    "create_context_from_asgi_scope",
    "ContextKey",
    "set_value",
    "get_value",
    "delete_value",
    "UserKey",
    "RequestIDKey",
    "UserIDKey",
]
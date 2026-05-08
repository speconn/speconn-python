"""Speconn Python runtime — JSON/MsgPack unary + Connect streaming RPC."""

from __future__ import annotations

from .error import Code, SpeconnError, CODE_TO_STATUS
from .envelope import FLAG_COMPRESSED, FLAG_END_STREAM, encode_envelope, decode_envelope
from .transport import SpeconnChannel, SpeconnMessage, HttpResponse
from .transport_httpx import HttpxChannel
from .transport_pyqwest import PyqwestChannel
from .client import SpeconnClient, CallOptions, Response, StreamResponse
from .router import SpeconnRouter, SpeconnServerRequest, SpeconnServerResponse, Interceptor
from .context import SpeconnContext, create_context, create_context_from_headers
from .adapters.asgi import create_asgi_adapter
from .server import listen
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
    "SpeconnMessage",
    "HttpResponse",
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
    "create_context_from_headers",
    "ContextKey",
    "set_value",
    "get_value",
    "delete_value",
    "UserKey",
    "RequestIDKey",
    "UserIDKey",
]
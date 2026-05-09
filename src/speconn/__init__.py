"""Speconn Python runtime — JSON/MsgPack unary + Connect streaming RPC."""

from __future__ import annotations

from .error import Code, SpeconnError, CODE_TO_STATUS
from .envelope import FLAG_COMPRESSED, FLAG_END_STREAM, encode_envelope, decode_envelope
from .transport import SpeconnChannel, SpeconnTransport, ServerChannel
from .transport_httpx import HttpxTransport, HttpxChannel
from .server_channel import AsyncioServerChannel, ASGIServerChannel
from .client import (
    SpeconnClient,
    CallOptions,
    Response,
    StreamResponse,
    ClientStreamHandle,
    BidiStreamHandle,
    split_headers_trailers,
)
from .router import SpeconnRouter, SpeconnServerRequest, SpeconnServerResponse, Interceptor
from .context import SpeconnContext, create_context
from .adapters.asgi import create_asgi_adapter, create_asgi_channel_adapter
from .server import listen
from .abort_signal import AbortSignal, create_abort_signal_with_timeout
from .context_key import ContextKey, set_value, get_value, delete_value, UserKey, RequestIDKey, UserIDKey
from .format import extract_format, format_to_mime

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
    "SpeconnChannel",
    "SpeconnTransport",
    "HttpxTransport",
    "HttpxChannel",
    "SpecCodec",
    "JsonReader",
    "JsonWriter",
    "MsgPackReader",
    "MsgPackWriter",
    "dispatch",
    "respond",
    "SpeconnClient",
    "CallOptions",
    "Response",
    "StreamResponse",
    "ClientStreamHandle",
    "BidiStreamHandle",
    "split_headers_trailers",
    "SpeconnRouter",
    "SpeconnContext",
    "SpeconnServerRequest",
    "SpeconnServerResponse",
    "Interceptor",
    "AbortSignal",
    "create_abort_signal_with_timeout",
    "create_context",
    "ContextKey",
    "set_value",
    "get_value",
    "delete_value",
    "UserKey",
    "RequestIDKey",
    "UserIDKey",
    "extract_format",
    "format_to_mime",
    "listen",
    "create_asgi_adapter",
    "create_asgi_channel_adapter",
    "AsyncioServerChannel",
    "ASGIServerChannel",
]

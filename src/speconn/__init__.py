"""Speconn Python runtime — JSON unary + Connect streaming RPC."""

from __future__ import annotations

from .error import Code, SpeconnError, CODE_TO_STATUS
from .envelope import FLAG_COMPRESSED, FLAG_END_STREAM, encode_envelope, decode_envelope
from .transport import Transport, TransportResponse, PyreqwestTransport, HttpxTransport
from .client import SpeconnClient
from .router import SpeconnRouter, SpeconnContext, SpeconnRequest, SpeconnResponse, Interceptor

__all__ = [
    "Code",
    "SpeconnError",
    "CODE_TO_STATUS",
    "FLAG_COMPRESSED",
    "FLAG_END_STREAM",
    "encode_envelope",
    "decode_envelope",
    "Transport",
    "TransportResponse",
    "PyreqwestTransport",
    "HttpxTransport",
    "SpeconnClient",
    "SpeconnRouter",
    "SpeconnContext",
    "SpeconnRequest",
    "SpeconnResponse",
    "Interceptor",
]

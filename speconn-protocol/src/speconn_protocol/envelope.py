from __future__ import annotations

import struct

FLAG_COMPRESSED: int = 0x01
FLAG_END_STREAM: int = 0x02


def encode_envelope(flags: int, payload: bytes) -> bytes:
    return struct.pack(">BI", flags, len(payload)) + payload


def decode_envelope(data: bytes) -> tuple[int, bytes]:
    if len(data) < 5:
        raise ValueError(f"envelope: frame too short ({len(data)} bytes)")
    flags = data[0]
    length = struct.unpack(">I", data[1:5])[0]
    if len(data) < 5 + length:
        raise ValueError(
            f"envelope: expected {length} payload bytes, got {len(data) - 5}"
        )
    return flags, data[5 : 5 + length]

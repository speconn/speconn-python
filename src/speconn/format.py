from __future__ import annotations


def extract_format(mime: str) -> str:
    ct = mime.lower()
    ct = ct[len("application/"):] if ct.startswith("application/") else ct
    ct = ct[len("connect+"):] if ct.startswith("connect+") else ct
    if ct == "msgpack":
        return "msgpack"
    if ct == "x-gron":
        return "gron"
    return "json"


def format_to_mime(fmt: str, stream: bool = False) -> str:
    sub = "msgpack" if fmt == "msgpack" else "x-gron" if fmt == "gron" else "json"
    return f"application/connect+{sub}" if stream else f"application/{sub}"

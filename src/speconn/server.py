from __future__ import annotations

import asyncio

from .router import SpeconnRouter, SpeconnServerRequest, SpeconnServerResponse
from .server_channel import AsyncioServerChannel


async def listen(router: SpeconnRouter, port: int = 8080, host: str = "127.0.0.1") -> None:

    async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        try:
            raw = await reader.readuntil(b"\r\n\r\n")
        except (asyncio.IncompleteReadError, Exception):
            writer.close()
            return

        req_text = raw.decode("utf-8", errors="replace")
        lines = req_text.split("\r\n")
        if not lines:
            writer.close()
            return

        request_line = lines[0]
        parts = request_line.split(" ")
        if len(parts) < 2:
            writer.close()
            return

        method = parts[0]
        path = parts[1]

        headers: dict[str, str] = {}
        for line in lines[1:]:
            if ":" in line:
                k, v = line.split(":", 1)
                headers[k.strip().lower()] = v.strip()

        content_length = 0
        try:
            content_length = int(headers.get("content-length", "0"))
        except ValueError:
            pass

        if content_length > 0:
            already = raw.split(b"\r\n\r\n", 1)
            if len(already) > 1:
                body_data = already[1]
            else:
                body_data = b""
            remaining = content_length - len(body_data)
            if remaining > 0:
                body_data += await reader.readexactly(remaining)
        else:
            body_data = b""

        if method == "OPTIONS":
            writer.write(b"HTTP/1.1 204 No Content\r\n\r\n")
            writer.close()
            return

        remote_addr = writer.get_extra_info("peername")
        remote = f"{remote_addr[0]}:{remote_addr[1]}" if remote_addr else None

        req = SpeconnServerRequest(path=path, headers=headers, body=body_data, remote_addr=remote)
        resp = await router.handle(req)

        status_text = {200: "OK", 400: "Bad Request", 404: "Not Found", 500: "Internal Server Error"}.get(resp.status, "OK")
        writer.write(f"HTTP/1.1 {resp.status} {status_text}\r\n".encode())
        for k, v in resp.headers.items():
            writer.write(f"{k}: {v}\r\n".encode())
        writer.write(f"content-length: {len(resp.body)}\r\n\r\n".encode())
        writer.write(resp.body)
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(handle_client, host, port)
    print(f"[speconn-python] listening on {host}:{port}")
    await server.serve_forever()

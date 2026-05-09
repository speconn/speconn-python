import pytest
import anyio
from speconn.context import SpeconnContext, create_context
from speconn.abort_signal import AbortSignal, create_abort_signal_with_timeout
from speconn.context_key import ContextKey, set_value, get_value, delete_value, UserKey, RequestIDKey, UserIDKey
from speconn.error import Code


@pytest.mark.anyio
async def test_context_fields():
    headers = {
        "Authorization": "Bearer token",
        "X-Custom": "value",
        "CONTENT-TYPE": "application/json",
    }

    ctx = create_context(
        headers=headers,
        method_name="/test.Service/Method",
        local_addr="localhost:8001",
        remote_addr="192.168.1.100:54321",
        timeout_ms=5000,
    )

    assert ctx.method_name == "/test.Service/Method"
    assert ctx.local_addr == "localhost:8001"
    assert ctx.remote_addr == "192.168.1.100:54321"

    assert ctx.headers["authorization"] == "Bearer token"
    assert ctx.headers["x-custom"] == "value"
    assert ctx.headers["content-type"] == "application/json"

    assert len(ctx.response_headers) == 0
    assert len(ctx.response_trailers) == 0


def test_response_headers():
    ctx = create_context({}, "/test", "localhost:8001", "client:123")

    ctx.set_response_header("X-Custom", "value1")
    assert ctx.response_headers["x-custom"] == "value1"

    ctx.set_response_header("X-Custom", "value2")
    assert ctx.response_headers["x-custom"] == "value2"

    ctx.add_response_header("X-Multi", "v1")
    ctx.add_response_header("X-Multi", "v2")
    assert ctx.response_headers["x-multi"] == "v1, v2"

    ctx.mark_headers_sent()

    with pytest.raises(RuntimeError, match="headers already sent"):
        ctx.set_response_header("X-Another", "value3")


def test_response_trailers():
    ctx = create_context({}, "/test", "localhost:8001", "client:123")

    ctx.set_response_trailer("X-Total-Count", "100")
    ctx.set_response_trailer("X-Request-Id", "abc-123")

    assert ctx.response_trailers["x-total-count"] == "100"
    assert ctx.response_trailers["x-request-id"] == "abc-123"


@pytest.mark.anyio
async def test_timeout_signal():
    signal = create_abort_signal_with_timeout(100)

    await anyio.sleep(0.15)

    assert signal.is_cancelled
    assert signal.reason == "timeout"
    remaining = signal.remaining_ms()
    assert remaining is not None
    assert remaining <= 0


@pytest.mark.anyio
async def test_manual_cancel():
    signal = AbortSignal()

    async def cancel_after_delay():
        await anyio.sleep(0.05)
        signal.set("manual cancel")

    async with anyio.create_task_group() as tg:
        tg.start_soon(cancel_after_delay)
        await signal.wait().wait()

    assert signal.is_cancelled
    assert signal.reason == "manual cancel"


@pytest.mark.anyio
async def test_context_timeout():
    ctx = create_context({}, "/test", "localhost:8001", "client:123", timeout_ms=100)

    await anyio.sleep(0.15)

    assert ctx.is_cancelled()

    with pytest.raises(anyio.get_cancelled_exc_class(), match="timeout"):
        await ctx.check_cancelled()


def test_context_key_typed():
    ctx = create_context({}, "/test", "localhost:8001", "client:123")

    TestKey = ContextKey(id="test", default_value="default")

    set_value(ctx, TestKey, "value1")
    value = get_value(ctx, TestKey)
    assert value == "value1"

    delete_value(ctx, TestKey)
    value = get_value(ctx, TestKey)
    assert value == "default"

    IntKey = ContextKey(id="int-test", default_value=0)
    set_value(ctx, IntKey, 42)
    int_value = get_value(ctx, IntKey)
    assert int_value == 42


def test_context_key_predefined():
    ctx = create_context({}, "/test", "localhost:8001", "client:123")

    ctx.set_user("alice")
    assert ctx.user() == "alice"
    assert get_value(ctx, UserKey) == "alice"

    ctx.set_request_id("req-123")
    assert ctx.request_id() == "req-123"
    assert get_value(ctx, RequestIDKey) == "req-123"

    user_id = get_value(ctx, UserIDKey)
    assert user_id == 0

    set_value(ctx, UserIDKey, 100)
    user_id = get_value(ctx, UserIDKey)
    assert user_id == 100


def test_headers_normalization():
    headers = {
        "Authorization": "Bearer token",
        "CONTENT-TYPE": "application/json",
        "X-Custom-Header": "value",
    }

    ctx = create_context(headers, "/test", "localhost:8001", "client:123")

    assert ctx.headers["authorization"] == "Bearer token"
    assert ctx.headers["content-type"] == "application/json"
    assert ctx.headers["x-custom-header"] == "value"


@pytest.mark.anyio
async def test_create_context_from_headers():
    headers = {
        "authorization": "Bearer token",
        "speconn-timeout-ms": "5000",
    }

    ctx = create_context(
        headers,
        method_name="/test.Service/Method",
        local_addr="localhost:8001",
        remote_addr="192.168.1.100:54321",
        timeout_ms=5000,
    )

    assert ctx.method_name == "/test.Service/Method"
    assert ctx.local_addr == "localhost:8001"
    assert ctx.remote_addr == "192.168.1.100:54321"
    assert ctx.headers["authorization"] == "Bearer token"


@pytest.mark.anyio
async def test_cleanup():
    ctx = create_context({}, "/test", "localhost:8001", "client:123", timeout_ms=1000)

    ctx.cleanup()

    assert ctx.is_cancelled()
    assert ctx.signal.reason == "cleanup"


@pytest.mark.anyio
async def test_throw_if_cancelled():
    signal = AbortSignal()
    signal.set("test reason")

    with pytest.raises(anyio.get_cancelled_exc_class(), match="test reason"):
        await signal.throw_if_cancelled()

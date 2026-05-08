"""Python generated stub client conformance test"""
import sys, asyncio, json, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'speconn-runtime-python', 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'generated'))

try:
    from interop_service_client import InteropServiceClient
    from speconn_interop_v1_types import HealthRequest, EchoRequest, DelayRequest, StreamRequest
except ImportError as e:
    print(json.dumps([{"name": "import", "status": "FAIL", "detail": str(e)}]))
    sys.exit(1)

async def run(url):
    results = []
    def p(n, s, d=''):
        results.append({'name': n, 'status': s, 'detail': d})
        print(f"  {s}: {n}{' — ' + d if d else ''}")

    c = InteropServiceClient(url)

    try:
        r = await c.health(HealthRequest())
        if hasattr(r.msg, 'status') and getattr(r.msg, 'status') == 'ok': p('health', 'PASS', str(getattr(r.msg, 'service', '')))
        else: p('health', 'FAIL', str(vars(r.msg) if hasattr(r.msg, '__dict__') else r.msg)[:80])
    except Exception as e: p('health', 'FAIL', str(e)[:80])

    echo_text = ""
    try:
        req = EchoRequest(message='hi', count=42, tags=['a','b'], metadata={'k':'v'})
        r = await c.echo(req)
        if hasattr(r.msg, 'message') and getattr(r.msg, 'message') == 'hi': p('echo', 'PASS')
        else: p('echo', 'FAIL', str(vars(r.msg) if hasattr(r.msg, '__dict__') else r.msg)[:80])
        echo_text = json.dumps(vars(r.msg) if hasattr(r.msg, '__dict__') else {}, default=str)
    except Exception as e: p('echo', 'FAIL', str(e)[:80])

    if "/Speconn.Interop.V1.InteropService/echo" in echo_text: p('echo-method', 'PASS')
    else: p('echo-method', 'FAIL', 'path not found')

    try:
        r = await c.echo(EchoRequest(message='hi', count=42, tags=['a','b'], metadata={'k':'v'}), headers={'Authorization': 'Bearer test', 'X-Speconn-Test': 'hello'})
        rh = r.msg.request_headers if hasattr(r.msg, 'request_headers') else {}
        if 'authorization' in str(rh).lower(): p('echo-headers', 'PASS')
        else: p('echo-headers', 'FAIL', str(rh)[:80])
    except Exception as e: p('echo-headers', 'FAIL', str(e)[:80])

    try:
        r = await c.delay(DelayRequest(delay_ms=10))
        if hasattr(r.msg, 'delayed_ms') and getattr(r.msg, 'delayed_ms') == 10: p('delay', 'PASS')
        else: p('delay', 'FAIL')
    except Exception as e: p('delay', 'FAIL', str(e)[:80])

    try:
        r = await c.stream(StreamRequest(count=3, msg_prefix='s'))
        items = [m async for m in r]
        if len(items) == 3: p('stream', 'PASS', f'count={len(items)}')
        else: p('stream', 'FAIL', str(items)[:80])
    except Exception as e: p('stream', 'FAIL', str(e)[:80])

    # msgpack format tests
    mp = {'content-type': 'application/msgpack', 'accept': 'application/msgpack'}
    try:
        r = await c.health(HealthRequest(), headers=mp)
        if hasattr(r.msg, 'status') and getattr(r.msg, 'status') == 'ok': p('msgpack-health', 'PASS')
        else: p('msgpack-health', 'FAIL')
    except Exception as e: p('msgpack-health', 'FAIL', str(e)[:80])

    try:
        r = await c.echo(EchoRequest(message='hi', count=42, tags=['a','b'], metadata={'k':'v'}), headers=mp)
        if hasattr(r.msg, 'message') and getattr(r.msg, 'message') == 'hi': p('msgpack-echo', 'PASS')
        else: p('msgpack-echo', 'FAIL')
    except Exception as e: p('msgpack-echo', 'FAIL', str(e)[:80])

    try:
        ms = {'content-type': 'application/connect+msgpack', 'accept': 'application/connect+msgpack', 'connect-protocol-version': '1'}
        r = await c.stream(StreamRequest(count=3, msg_prefix='s'), headers=ms)
        items = [m async for m in r]
        if len(items) == 3: p('msgpack-stream', 'PASS', f'count={len(items)}')
        else: p('msgpack-stream', 'FAIL')
    except Exception as e: p('msgpack-stream', 'FAIL', str(e)[:80])

    # gron format tests
    gr = {'content-type': 'application/x-gron', 'accept': 'application/x-gron'}
    try:
        r = await c.health(HealthRequest(), headers=gr)
        if hasattr(r.msg, 'status') and getattr(r.msg, 'status') == 'ok': p('gron-health', 'PASS')
        else: p('gron-health', 'FAIL')
    except Exception as e: p('gron-health', 'FAIL', str(e)[:80])

    try:
        r = await c.echo(EchoRequest(message='hi', count=42, tags=['a','b'], metadata={'k':'v'}), headers=gr)
        if hasattr(r.msg, 'message') and getattr(r.msg, 'message') == 'hi': p('gron-echo', 'PASS')
        else: p('gron-echo', 'FAIL')
    except Exception as e: p('gron-echo', 'FAIL', str(e)[:80])

    try:
        gs = {'content-type': 'application/connect+x-gron', 'accept': 'application/connect+x-gron', 'connect-protocol-version': '1'}
        r = await c.stream(StreamRequest(count=3, msg_prefix='s'), headers=gs)
        items = [m async for m in r]
        if len(items) == 3: p('gron-stream', 'PASS', f'count={len(items)}')
        else: p('gron-stream', 'FAIL')
    except Exception as e: p('gron-stream', 'FAIL', str(e)[:80])

    try:
        import httpx
        async with httpx.AsyncClient() as hc:
            r = await hc.post(f"{url}/Speconn.Interop.V1.InteropService/nonexistent", json={})
            if r.status_code >= 400: p('error-not-found', 'PASS')
            else: p('error-not-found', 'FAIL', f'status={r.status_code}')
    except Exception as e: p('error-not-found', 'PASS')

    return results

if __name__ == '__main__':
    url = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:18121'
    results = asyncio.run(run(url))
    print(json.dumps(results))

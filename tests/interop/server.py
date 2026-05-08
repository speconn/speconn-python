"""Python gen stub server — for std→Python server test"""
import sys, os, asyncio
sys.path.insert(0, '/workspace/Speconn/speconn-runtime-python/src')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'generated'))
from speconn import listen
from interop_service_server import create_router

class H:
    def health(s, c, r):
        class R: status='ok'; service='py-server'; http_protocol='http1'
        return R()
    def echo(s, c, r):
        class R: message=r.message; count=r.count; tags=r.tags; metadata=r.metadata; method_name=c.method_name; request_headers=c.headers
        return R()
    def delay(s, c, r):
        class R: delayed_ms=r.delay_ms
        return R()
    async def stream(s, c, r, send):
        for i in range(r.count):
            class SI: index=i; message=f'{r.msg_prefix}-{i}'
            send(SI())
            if i < r.count - 1: await asyncio.sleep(0.01)

router = create_router(H())
port = int(sys.argv[1]) if len(sys.argv) > 1 else 18300
asyncio.run(listen(router, port=port))

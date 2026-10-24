"""Talks to the ESP32 over WebSocket (ws://IP:5621) using protocol.py."""
import asyncio, json, struct, time
import websockets
from . import protocol as P

class RobotLink:
    def __init__(self, url, log=print):
        self.url, self.log = url, log
        self.ws = None; self.connected = False
        self._id = 0; self._pending = {}
        self.vel = (0.0, 0.0, 0.0); self.vel_t = 0.0   # latest wanted velocity
        self.latency_ms = None; self.pan = 0.0; self.distance_mm = None
        self._tasks = []

    async def connect(self):
        self.ws = await websockets.connect(self.url, max_size=None, open_timeout=4)
        self.connected = True
        self._tasks = [asyncio.create_task(self._reader()), asyncio.create_task(self._heartbeat())]

    async def close(self):
        self.connected = False
        for t in self._tasks: t.cancel()
        if self.ws: await self.ws.close()

    async def _reader(self):
        try:
            async for m in self.ws:
                if isinstance(m, bytes) and len(m) >= P.RES.size:
                    mid, status, payload = P.parse_response(m)
                    fut = self._pending.pop(mid, None)
                    if fut and not fut.done(): fut.set_result((status, payload))
        except Exception: pass
        self.connected = False
        for f in self._pending.values():
            if not f.done(): f.set_exception(ConnectionError("link closed"))
        self.log("robot link closed")

    async def _heartbeat(self):
        """Robot stops by itself if commands stop, so resend velocity 20x/s."""
        while True:
            await asyncio.sleep(0.05)
            if not self.connected: continue
            v = self.vel if time.monotonic() - self.vel_t < 0.4 else (0.0, 0.0, 0.0)
            try: await self.send(P.BODY, 2, P.f32(*v))
            except Exception: pass

    async def send(self, module, action, payload=b""):
        self._id = (self._id + 1) & 0xFFFF
        await self.ws.send(P.pack_request(self._id, module, action, payload, ack=False))

    async def call(self, module, action, payload=b"", timeout=2.0):
        self._id = (self._id + 1) & 0xFFFF
        fut = asyncio.get_running_loop().create_future(); self._pending[self._id] = fut
        await self.ws.send(P.pack_request(self._id, module, action, payload, ack=True))
        status, data = await asyncio.wait_for(fut, timeout)
        if status != P.OK: raise RuntimeError(f"robot status {status} (module {module}, action {action})")
        return data

    # ---- friendly helpers -------------------------------------------------
    def drive(self, vx, vy, wz): self.vel = (vx, vy, wz); self.vel_t = time.monotonic()
    async def stop(self):
        self.drive(0, 0, 0)
        try: await self.send(P.BODY, 2, P.f32(0, 0, 0))
        except Exception: pass
    async def ping(self):
        t = time.perf_counter(); await self.call(P.SYSTEM, 0)
        self.latency_ms = (time.perf_counter() - t) * 1000; return self.latency_ms
    async def set_gait(self, g): await self.send(P.GAIT, 0, bytes([g]))
    async def set_pan(self, deg): self.pan = deg; await self.send(P.HEAD, 0, P.f32(deg))
    async def get_pan(self): return struct.unpack("<f", await self.call(P.HEAD, 1))[0]
    async def get_distance(self):
        self.distance_mm = struct.unpack("<H", await self.call(P.DISTANCE, 0))[0]; return self.distance_mm
    async def pick(self): return (await self.call(P.ARM, 0, timeout=15))[0] == 1
    async def place(self): return (await self.call(P.ARM, 1, timeout=15))[0] == 1
    async def run_action(self, i): await self.send(P.ACTION, 0, bytes([i]))
    async def selftest(self): return json.loads(P.read_string(await self.call(P.SELFTEST, 0, timeout=8)))

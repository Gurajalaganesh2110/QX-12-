"""Pretend robot: speaks the same WebSocket protocol on :5621 and serves an MJPEG camera on :90.
Lets you develop and demo the whole app without hardware."""
import asyncio, json, math, struct, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import cv2, numpy as np
from websockets.asyncio.server import serve
from brain import protocol as P
from brain.vision import BGR, W, H, FX, CAM_H, TILT

SIZE = 0.06   # object size in metres

class FakeRobot:
    def __init__(self, ws_port=5621, video_port=8090, host="127.0.0.1"):
        self.ws_port, self.video_port, self.host = ws_port, video_port, host
        self.x = self.y = self.th = 0.0; self.pan = 0.0
        self.cmd = (0.0, 0.0, 0.0); self.cmd_t = 0.0; self.carried = None; self.gait = 1
        self.objects = [dict(colour="red", shape="circle", x=1.3, y=0.3), dict(colour="blue", shape="square", x=0.9, y=-0.7),
                        dict(colour="green", shape="triangle", x=1.7, y=1.0), dict(colour="yellow", shape="square", x=0.7, y=0.7),
                        dict(colour="orange", shape="circle", x=-1.0, y=0.4), dict(colour="purple", shape="triangle", x=-0.5, y=-1.2)]

    @property
    def cam_heading(self): return self.th - math.radians(self.pan)      # pan + = right

    async def start(self):
        self._server = await serve(self._handler, self.host, self.ws_port, max_size=None)
        sim = self
        class H_(BaseHTTPRequestHandler):
            def log_message(self, *a): pass
            def do_GET(self):
                self.send_response(200); self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
                self.send_header("Access-Control-Allow-Origin", "*"); self.end_headers()
                try:
                    while True:
                        jpg = cv2.imencode(".jpg", sim.render())[1].tobytes()
                        self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n" % len(jpg) + jpg + b"\r\n")
                        time.sleep(0.1)
                except Exception: pass
        self._http = ThreadingHTTPServer((self.host, self.video_port), H_)
        threading.Thread(target=self._http.serve_forever, daemon=True).start()
        self._phys = asyncio.create_task(self._physics())

    async def stop(self):
        self._phys.cancel(); self._http.shutdown(); self._server.close()

    async def _physics(self):
        dt = 0.02
        while True:
            await asyncio.sleep(dt)
            vx, vy, wz = self.cmd if time.time() - self.cmd_t < 0.3 else (0, 0, 0)      # watchdog like the real robot
            nx = self.x + (vx * math.cos(self.th) - vy * math.sin(self.th)) * dt
            ny = self.y + (vx * math.sin(self.th) + vy * math.cos(self.th)) * dt
            if all(math.hypot(o["x"] - nx, o["y"] - ny) > 0.10 for o in self.objects): self.x, self.y = nx, ny
            self.th += wz * dt

    def _rel(self, o):
        dx, dy = o["x"] - self.x, o["y"] - self.y
        rel = (math.atan2(dy, dx) - self.cam_heading + math.pi) % (2 * math.pi) - math.pi     # + = left
        return rel, math.hypot(dx, dy)

    def distance_mm(self):
        best = 2000
        for o in self.objects:
            rel, d = self._rel(o)
            if abs(rel) < math.radians(8): best = min(best, int(d * 1000))
        return best

    def render(self):
        img = np.zeros((H, W, 3), np.uint8); hz = int(H / 2 - FX * math.tan(TILT))
        img[:max(hz, 0)] = (200, 190, 175); img[max(hz, 0):] = (110, 120, 110)
        for o in sorted(self.objects, key=lambda o: -self._rel(o)[1]):
            rel, d = self._rel(o); depth = d * math.cos(rel)
            if abs(rel) > math.radians(45) or depth < 0.05: continue
            u = W / 2 - FX * math.tan(rel); v = H / 2 + FX * math.tan(math.atan(CAM_H / depth) - TILT); s = FX * SIZE / depth
            c = BGR[o["colour"]]
            if o["shape"] == "circle": cv2.circle(img, (int(u), int(v - s / 2)), max(1, int(s / 2)), c, -1)
            elif o["shape"] == "square": cv2.rectangle(img, (int(u - s / 2), int(v - s)), (int(u + s / 2), int(v)), c, -1)
            else: cv2.fillPoly(img, [np.array([(u, v - s), (u - s / 2, v), (u + s / 2, v)], np.int32)], c)
        cv2.putText(img, "SIM", (W - 40, H - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
        return img

    def _pick(self):
        if self.carried or abs(self.pan) > 10: return 0
        for o in self.objects:
            dx, dy = o["x"] - self.x, o["y"] - self.y
            rel = (math.atan2(dy, dx) - self.th + math.pi) % (2 * math.pi) - math.pi
            if 0.12 <= math.hypot(dx, dy) <= 0.24 and abs(rel) < math.radians(7):
                self.carried = o; self.objects.remove(o); return 1
        return 0

    def _place(self):
        if not self.carried: return 0
        o = self.carried; o["x"], o["y"] = self.x + 0.25 * math.cos(self.th), self.y + 0.25 * math.sin(self.th)
        self.objects.append(o); self.carried = None; return 1

    def handle(self, module, action, payload):
        """returns (status, payload)"""
        M = P
        if module == M.SYSTEM and action == 0: return 0, b""
        if module == M.GAIT and action == 0: self.gait = payload[0]; return 0, b""
        if module == M.BODY:
            if action == 2: self.cmd = struct.unpack("<fff", payload); self.cmd_t = time.time(); return 0, b""
            if action == 1: return 0, struct.pack("<H", 0x0FFF)
            if action in (6, 7): return 0, M.f32(0.0)
        if module == M.ERROR and action == 0: return 0, struct.pack("<H", 0)
        if module == M.DIAGNOSTIC and action == 0: return 0, b"\x00"
        if module == M.HEAD:
            if action == 0: self.pan = struct.unpack("<f", payload)[0]; return 0, b""
            if action == 1: return 0, M.f32(self.pan)
        if module == M.DISTANCE and action == 0: return 0, struct.pack("<H", self.distance_mm())
        if module == M.ARM and action == 0: return 0, bytes([self._pick()])
        if module == M.ARM and action == 1: return 0, bytes([self._place()])
        if module == M.ACTION and action == 0: return 0, b""
        if module == M.SELFTEST and action == 0:
            return 0, M.string(json.dumps(dict(pico_link=True, camera=True, tof=True, servos=True, battery_v=7.8, rssi=-52)))
        return (M.UNKNOWN_MODULE if module not in (0, 2, 3, 19, 20, 32, 33, 34, 35, 36) else M.UNKNOWN_ACTION), b""

    async def _handler(self, ws):
        try:
            async for m in ws:
                if not isinstance(m, bytes) or len(m) < P.REQ.size: continue
                flags, mid, module, action, payload = P.parse_request(m)
                try: status, out = self.handle(module, action, payload)
                except Exception: status, out = P.INVALID_PARAMS, b""
                if flags & P.ACK: await ws.send(P.pack_response(mid, status, out))
        except Exception: pass     # client closed

if __name__ == "__main__":
    async def main(): await FakeRobot().start(); await asyncio.Event().wait()
    asyncio.run(main())

"""Web server: serves ui/, pushes robot state to the browser, takes commands, re-streams annotated video."""
import asyncio, json, math, time
from contextlib import asynccontextmanager
from pathlib import Path
import cv2, numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from . import diagnostics
from .link import RobotLink
from .mission import Mission, Target
from .video import VideoWorker

UI = Path(__file__).resolve().parent.parent / "ui"
SPEED = dict(vx=0.15, vy=0.10, wz=0.8)       # UI sends -1..1, scaled here (m/s, m/s, rad/s)

class Brain:
    def __init__(self):
        self.link = self.video = self.mission = self.task = self.sweep_task = None
        self.logs, self.diag, self.ip, self.drive_t = [], None, None, 0.0
        self.sim = False; self.sim_obj = None
    def log(self, m): self.logs.append(f"{time.strftime('%H:%M:%S')}  {m}"); del self.logs[:-200]
    def auto_active(self): return self.task is not None and not self.task.done()

    async def connect(self, ip):
        await self.disconnect()
        link = RobotLink(f"ws://{ip}:5621", self.log)
        try: await link.connect()
        except Exception as e: return self.log(f"cannot reach {ip}: {e}")
        self.link, self.ip = link, ip
        vp = 8090 if self.sim and ip in ("127.0.0.1", "localhost") else 90      # real robot streams on :90
        self.video = VideoWorker(f"http://{ip}:{vp}/stream"); self.video.start()
        self.log(f"connected to {ip}")

    async def disconnect(self):
        await self.stop_auto()
        if self.video: self.video.stop_flag = True
        if self.link: await self.link.stop(); await self.link.close()
        self.link = self.video = None

    async def stop_auto(self):
        if self.task and not self.task.done(): self.task.cancel(); await asyncio.gather(self.task, return_exceptions=True)
        if self.sweep_task: self.sweep_task.cancel(); self.sweep_task = None

    async def sweep(self):
        a, d = 0.0, 1
        while True:
            a += 3 * d
            if abs(a) >= 70: d = -d
            await self.link.set_pan(a); await asyncio.sleep(0.1)

    async def command(self, m):
        t, L = m.get("t"), self.link
        if t == "connect": await self.connect(m["ip"].strip())
        elif t == "disconnect": await self.disconnect()
        elif t == "estop":
            await self.stop_auto()
            if L: await L.stop()
            self.log("EMERGENCY STOP")
        elif not (L and L.connected): return
        elif t == "drive" and not self.auto_active():
            L.drive(m["vx"] * SPEED["vx"], m["vy"] * SPEED["vy"], m["wz"] * SPEED["wz"])
        elif t == "gait": await L.set_gait(int(m["type"]))
        elif t == "action": await L.run_action(int(m["id"]))
        elif t == "pan": await L.set_pan(float(m["deg"]))
        elif t == "sweep":
            if self.sweep_task: self.sweep_task.cancel(); self.sweep_task = None
            if m["on"]: self.sweep_task = asyncio.create_task(self.sweep())
        elif t == "mission_start" and not self.auto_active():
            if self.sweep_task: self.sweep_task.cancel(); self.sweep_task = None
            tg = Target(m.get("label") or None, m.get("colour") or None, m.get("shape") or None)
            self.mission = Mission(L, self.video, self.log)
            self.task = asyncio.create_task(self.mission.run(tg))
        elif t == "mission_stop": await self.stop_auto(); await L.stop()
        elif t == "diag": self.diag = await diagnostics.run(L, self.video)

    def snapshot(self):
        L, V, M = self.link, self.video, self.mission
        dets = [dict(label=d.label, colour=d.colour, shape=d.shape) for d in (V.latest.dets if V and V.latest else [])]
        return dict(t="state", connected=bool(L and L.connected), ip=self.ip, latency=L.latency_ms if L else None,
                    pan=L.pan if L else 0, dist=L.distance_mm if L else None, fps=V.fps if V else 0, dets=dets,
                    auto=self.auto_active(), state=M.state if M else "IDLE", msg=M.msg if M else "",
                    logs=self.logs[-40:], diag=self.diag, sim=self.sim,
                    pose=[round(self.sim_obj.x, 2), round(self.sim_obj.y, 2), round(math.degrees(self.sim_obj.th))] if self.sim_obj else None)

def create_app(default_ip=None, sim=False):
    brain = Brain(); brain.sim = sim; clients = set()
    if sim and not default_ip: default_ip = "127.0.0.1"

    async def ticker():
        n = 0
        while True:
            await asyncio.sleep(0.2); n += 1
            L = brain.link
            if L and L.connected:
                try:
                    await L.get_distance()
                    if n % 10 == 0: await L.ping()
                except Exception: pass
            if brain.link and not brain.auto_active() and time.monotonic() - brain.link.vel_t > 0.4 and any(brain.link.vel):
                brain.link.drive(0, 0, 0)

    async def pusher():
        while True:
            await asyncio.sleep(0.1)
            if clients:
                msg = json.dumps(brain.snapshot())
                for c in list(clients):
                    try: await c.send_text(msg)
                    except Exception: clients.discard(c)

    @asynccontextmanager
    async def lifespan(app):
        if sim:
            from sim.fake_robot import FakeRobot
            app.state.sim = brain.sim_obj = FakeRobot(video_port=8090); await app.state.sim.start()
        if default_ip: await brain.connect(default_ip)
        tasks = [asyncio.create_task(ticker()), asyncio.create_task(pusher())]
        yield
        for t in tasks: t.cancel()
        await brain.disconnect()

    app = FastAPI(lifespan=lifespan); app.state.brain = brain

    @app.websocket("/ws")
    async def ws(sock: WebSocket):
        await sock.accept(); clients.add(sock)
        try:
            while True:
                try: await brain.command(json.loads(await sock.receive_text()))
                except WebSocketDisconnect: raise
                except Exception as e: brain.log(f"command error: {e}")
        except WebSocketDisconnect: pass
        finally:
            clients.discard(sock)
            if brain.link and not brain.auto_active(): await brain.link.stop()

    @app.get("/video")
    async def video():
        blank = cv2.imencode(".jpg", np.zeros((240, 320, 3), np.uint8))[1].tobytes()
        async def gen():
            last = -1
            while True:
                v = brain.video
                if v and v.jpeg and v.count != last: last = v.count; jpg = v.jpeg
                elif not v or not v.jpeg: jpg = blank; await asyncio.sleep(0.5)
                else: await asyncio.sleep(0.03); continue
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n"
        return StreamingResponse(gen(), media_type="multipart/x-mixed-replace; boundary=frame")

    app.mount("/", StaticFiles(directory=UI, html=True), name="ui")
    return app

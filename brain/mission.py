"""Automatic mode: SEARCH -> APPROACH -> ALIGN -> PICK -> DONE.
Convention: bearing + = right, wz + = turn left (CCW), vy + = left, vx + = forward."""
import asyncio, math, time
from dataclasses import dataclass
from typing import Optional
from .vision import bearing_deg, floor_distance, pick_target

PICK_DIST = 0.18          # metres: where the object must sit for the arm to reach it
clamp = lambda v, lo, hi: max(lo, min(hi, v))

@dataclass
class Target:
    label: Optional[str] = None
    colour: Optional[str] = None
    shape: Optional[str] = None
    def text(self): return " ".join(x for x in (self.label, self.colour, self.shape) if x) or "anything"

class Mission:
    def __init__(self, link, video, log=print):
        self.link, self.video, self.log = link, video, log
        self.state, self.msg, self.target = "IDLE", "", Target()
        self.pan, self.pan_t, self.state_t = 0.0, 0.0, time.time()

    def set_state(self, st, msg=""):
        self.state, self.msg, self.state_t = st, msg, time.time()
        self.video.hud = f"{st} {msg}".strip(); self.log(f"mission: {st} {msg}".strip())

    def _see(self, after):
        f = self.video.latest
        if f and f.t > after and time.time() - f.t < 0.6: return pick_target(f.dets, self.target), True
        return None, False        # (nothing, no fresh frame)

    async def _pan(self, deg):
        self.pan = deg; await self.link.set_pan(deg); self.pan_t = time.time()

    async def _move(self, vx, vy, wz, secs):
        for _ in range(int(secs * 10)): self.link.drive(vx, vy, wz); await asyncio.sleep(0.1)
        await self.link.stop()

    def _measure(self, det):
        err = self.pan + bearing_deg(det.cx)                  # body-relative bearing
        dist = floor_distance(det.cy + det.h / 2)
        tof = self.link.distance_mm
        if abs(bearing_deg(det.cx)) < 4 and tof and tof < 1500: dist = tof / 1000    # trust the ToF sensor
        return err, dist

    async def run(self, target):
        self.target = target; self.video.target = target
        try: await self._run()
        except asyncio.CancelledError: self.set_state("STOPPED"); raise
        except Exception as e: self.set_state("FAILED", str(e))
        finally: await self.link.stop()

    async def _run(self):
        t0 = time.time(); self.set_state("SEARCH", self.target.text())
        await self._pan(-80); step_t, dirn, lost, stable, tries = time.time(), 1, 0.0, 0, 0
        while True:
            await asyncio.sleep(0.1)
            if time.time() - t0 > 180: return self.set_state("FAILED", "timeout")
            st = self.state
            if st == "SEARCH":
                det, _ = self._see(self.pan_t + 0.4)
                if det: self.set_state("APPROACH", f"found {det.label}"); lost = 0; continue
                if time.time() - step_t > 0.7:
                    nxt = self.pan + 20 * dirn
                    if abs(nxt) > 80:      # one full pass done: turn the body 150 deg, then sweep back the other way
                        dirn = -dirn
                        await self._move(0, 0, 0.6, math.radians(150) / 0.6); self.pan_t = time.time()
                    else:
                        await self._pan(nxt)
                    step_t = time.time()
            elif st == "APPROACH":
                det, fresh = self._see(self.pan_t + 0.3)
                if not det:
                    if fresh:
                        self.link.drive(0, 0, 0); lost += 0.1
                        if lost > 2: self.set_state("SEARCH", "lost target"); lost = 0
                    continue
                lost = 0; err, dist = self._measure(det)
                tof = self.link.distance_mm
                if abs(bearing_deg(det.cx)) < 4 and tof and tof / 1000 < floor_distance(det.cy + det.h / 2) - 0.15:
                    self.link.drive(0, 0.08, 0); self.msg = "obstacle: side-step"; continue
                if abs(err) > 6:   # move-and-look: stop, face it (open loop), then measure again
                    await self.link.stop(); await self._pan(0)
                    await self._move(0, 0, -0.5 if err > 0 else 0.5, math.radians(min(abs(err), 90)) / 0.5)
                    await asyncio.sleep(0.4); continue
                elif abs(self.pan) > 2: self.link.drive(0, 0, 0); await self._pan(0)
                else:              self.link.drive(clamp(0.5 * (dist - PICK_DIST), 0.02, 0.12), 0, clamp(-math.radians(err), -0.3, 0.3))
                if dist <= PICK_DIST + 0.04 and abs(err) < 6 and abs(self.pan) <= 2: self.set_state("ALIGN"); stable = 0
            elif st == "ALIGN":
                det, fresh = self._see(self.pan_t + 0.3)
                if time.time() - self.state_t > 20: return self.set_state("FAILED", "could not align")
                if not det:
                    self.link.drive(0, 0, 0); lost += 0.1 if fresh else 0
                    if lost > 1.5: self.set_state("SEARCH", "lost target"); lost = 0
                    continue
                lost = 0; err, dist = self._measure(det)
                dv = dist - PICK_DIST
                self.link.drive(clamp(0.8 * dv, -0.05, 0.05) if abs(dv) > 0.02 else 0, 0, clamp(-math.radians(err), -0.25, 0.25))
                stable = stable + 1 if abs(err) < 2.5 and abs(dv) < 0.03 else 0
                if stable >= 6: self.set_state("PICK"); self.link.drive(0, 0, 0)
            elif st == "PICK":
                await self.link.stop()
                if await self.link.pick(): return self.set_state("DONE", "object picked")
                tries += 1
                if tries >= 2: return self.set_state("FAILED", "pick failed twice")
                self.set_state("ALIGN", "retry"); stable = 0

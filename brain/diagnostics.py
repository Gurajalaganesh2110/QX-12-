"""Self-diagnostic: returns [{name, status: ok|warn|fail, detail}]."""
import asyncio

def _r(name, ok, detail, warn=False): return {"name": name, "status": "ok" if ok else ("warn" if warn else "fail"), "detail": detail}

async def run(link, video):
    out = []
    if not link or not link.connected: return [_r("Robot link", False, "not connected")]
    try: ms = await link.ping(); out.append(_r("Robot link", ms < 400, f"{ms:.0f} ms round trip", warn=ms < 800))
    except Exception as e: return [_r("Robot link", False, str(e))]
    try:
        t = await link.selftest()
        out.append(_r("ESP32 -> Pico link", t.get("pico_link", False), "answers" if t.get("pico_link") else "no reply"))
        out.append(_r("Camera on robot", t.get("camera", False), "frames captured" if t.get("camera") else "no frame"))
        out.append(_r("Distance sensor", t.get("tof", False), "reading valid" if t.get("tof") else "no reading"))
        out.append(_r("Servos", t.get("servos", False), "commands accepted (no position feedback on MG996R)" if t.get("servos") else "error"))
        v = t.get("battery_v", 0); out.append(_r("Battery", v > 6.8, f"{v:.2f} V", warn=v > 6.4))
        r = t.get("rssi", -100); out.append(_r("Wi-Fi signal", r > -75, f"{r} dBm", warn=r > -85))
    except Exception as e: out.append(_r("Robot self-test", False, str(e)))
    f = video.latest if video else None
    if not f or video.fps < 2: out.append(_r("Video stream", False, "no frames reaching the laptop"))
    else: out.append(_r("Video stream", f.img.mean() > 12, f"{video.fps:.0f} fps, brightness {f.img.mean():.0f}", warn=True))
    try:
        await link.set_pan(25); await asyncio.sleep(0.3); p = await link.get_pan(); await link.set_pan(0)
        out.append(_r("Camera pan servo", abs(p - 25) < 3, f"asked 25 deg, reports {p:.0f} deg"))
    except Exception as e: out.append(_r("Camera pan servo", False, str(e)))
    return out

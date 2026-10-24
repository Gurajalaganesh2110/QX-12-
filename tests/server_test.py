"""Tests the running app through its WebSocket, like the browser does.
   Terminal 1:  python run.py --no-browser          Terminal 2:  python -m tests.server_test [port] [colour] [shape]"""
import asyncio, json, sys, websockets

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
COLOUR = sys.argv[2] if len(sys.argv) > 2 else "red"
SHAPE = sys.argv[3] if len(sys.argv) > 3 else "circle"
ok = lambda c, msg: (print(("PASS " if c else "FAIL ") + msg), c or sys.exit(1))

LAST = {}
async def reader(ws):
    async for raw in ws: LAST["m"] = json.loads(raw)
async def latest(ws):
    await asyncio.sleep(0.15); return LAST["m"]

async def main():
    async with websockets.connect(f"ws://127.0.0.1:{PORT}/ws") as ws:
        send = lambda **k: ws.send(json.dumps(k)); rd = asyncio.create_task(reader(ws)); await asyncio.sleep(0.5)
        m = await latest(ws)
        ok(m["connected"] and m["sim"] and m["fps"] > 2 and m["dets"], f"connected to simulator, video {m['fps']:.0f} fps, sees {[(d['label'], d['colour'], d['shape']) for d in m['dets']]}")
        x0 = m["pose"][0]
        for _ in range(30): await send(t="drive", vx=1, vy=0, wz=0); await asyncio.sleep(0.05)
        await asyncio.sleep(0.4); m = await latest(ws)
        ok(m["pose"][0] > x0 + 0.1, f"manual drive moved the robot forward ({x0} -> {m['pose'][0]} m)")
        await asyncio.sleep(0.7); a = (await latest(ws))["pose"]; await asyncio.sleep(0.5); b = (await latest(ws))["pose"]
        ok(a == b, "robot stops by itself when drive commands stop")
        await send(t="pan", deg=30); await send(t="gait", type=2); await send(t="action", id=1); await asyncio.sleep(0.5)
        m = await latest(ws); ok(m["pan"] == 30, "camera pan command applied")
        await send(t="diag"); await asyncio.sleep(2.5); m = await latest(ws)
        ok(m["diag"] and all(r["status"] == "ok" for r in m["diag"]), f"self-check: {len(m['diag'])} items all ok")
        await send(t="pan", deg=0)
        await send(t="mission_start", colour=COLOUR, shape=SHAPE); seen = []
        for _ in range(450):
            m = await latest(ws)
            if not seen or seen[-1] != m["state"]: seen.append(m["state"])
            if m["state"] in ("DONE", "FAILED"): break
            await asyncio.sleep(0.2)
        ok(m["state"] == "DONE", f"automatic mode picked the {COLOUR} {SHAPE}: {' > '.join(seen)}")
        await send(t="mission_start", colour="green", shape=""); await asyncio.sleep(2); await send(t="estop"); await asyncio.sleep(0.6)
        m = await latest(ws); p1 = m["pose"]; await asyncio.sleep(0.6); p2 = (await latest(ws))["pose"]
        ok(not m["auto"] and m["state"] == "STOPPED" and p1 == p2, "emergency stop cancels the mission and the robot stays still")
        ok(not any("error" in l for l in m["logs"]), "no errors in the log")
    print("SERVER TEST PASSED")
asyncio.run(main())

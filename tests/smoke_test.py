"""End-to-end check without hardware:  python -m tests.smoke_test"""
import asyncio, sys, time
from brain import protocol as P
from brain.link import RobotLink
from brain.video import VideoWorker
from brain.mission import Mission, Target
from brain import diagnostics
from sim.fake_robot import FakeRobot

async def main():
    f = P.parse_request(P.pack_request(7, 3, 2, P.f32(1, 2, 3)))
    assert f[1:4] == (7, 3, 2) and len(f[4]) == 12, "protocol framing"
    sim = FakeRobot(video_port=8090); await sim.start()
    link = RobotLink("ws://127.0.0.1:5621"); await link.connect()
    video = VideoWorker("http://127.0.0.1:8090/stream"); video.start()
    await asyncio.sleep(1.5)
    assert video.latest and any(d.colour == "red" and d.shape == "circle" for d in video.latest.dets), "vision sees the red circle"
    print("labels seen:", [(d.label, d.colour, d.shape) for d in video.latest.dets])
    print("diagnostics:", [(r["name"], r["status"]) for r in await diagnostics.run(link, video)])
    m = Mission(link, video, print); t0 = time.time()
    await m.run(Target(colour="orange", shape="circle"))      # object is BEHIND the robot: must search first
    print(f"mission ended {m.state} in {time.time() - t0:.0f}s, carried:", sim.carried)
    assert m.state == "DONE" and sim.carried and sim.carried["colour"] == "orange"
    await link.close(); await sim.stop(); print("SMOKE TEST PASSED")

asyncio.run(main())

"""Pulls the robot's MJPEG stream ONCE, runs detection, re-serves an annotated copy."""
import threading, time, urllib.request
from collections import namedtuple
import cv2, numpy as np
from .vision import Tracker, detect, annotate

Frame = namedtuple("Frame", "img dets t")

class VideoWorker(threading.Thread):
    def __init__(self, url):
        super().__init__(daemon=True)
        self.url, self.stop_flag = url, False
        self.latest = None; self.jpeg = None; self.count = 0; self.fps = 0.0
        self.target = None; self.hud = ""; self.tracker = Tracker()

    def run(self):
        while not self.stop_flag:
            try:
                with urllib.request.urlopen(self.url, timeout=5) as r:
                    buf = b""; t0 = time.time(); n = 0
                    while not self.stop_flag:
                        chunk = r.read1(65536)
                        if not chunk: break
                        buf += chunk; last = None
                        while True:                      # keep only the NEWEST complete frame (never build a backlog)
                            a = buf.find(b"\xff\xd8"); b = buf.find(b"\xff\xd9", a + 2) if a != -1 else -1
                            if a == -1 or b == -1: break
                            last = buf[a:b + 2]; buf = buf[b + 2:]
                        if len(buf) > 2_000_000: buf = b""
                        img = cv2.imdecode(np.frombuffer(last, np.uint8), cv2.IMREAD_COLOR) if last else None
                        if img is not None:
                            self._process(img); n += 1
                            if time.time() - t0 > 1: self.fps, n, t0 = n / (time.time() - t0), 0, time.time()
            except Exception:
                time.sleep(1)

    def _process(self, img):
        dets = self.tracker.update(detect(img))
        self.latest = Frame(img, dets, time.time())
        self.jpeg = cv2.imencode(".jpg", annotate(img, dets, self.target, self.hud), [cv2.IMWRITE_JPEG_QUALITY, 80])[1].tobytes()
        self.count += 1

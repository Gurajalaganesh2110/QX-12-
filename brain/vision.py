"""Colour + shape detection (no object names needed) and A/B/C labels."""
import math
from dataclasses import dataclass
import cv2, numpy as np

W, H, HFOV, CAM_H, TILT = 640, 480, 62.0, 0.12, math.radians(15)   # camera model: must match your stream (VGA here)
FX = (W / 2) / math.tan(math.radians(HFOV / 2))

COLOURS = {   # OpenCV HSV ranges (H 0-180)
    "red":    [((0, 120, 70), (10, 255, 255)), ((170, 120, 70), (180, 255, 255))],
    "orange": [((11, 120, 70), (22, 255, 255))],
    "yellow": [((23, 100, 70), (35, 255, 255))],
    "green":  [((40, 80, 50), (85, 255, 255))],
    "blue":   [((95, 100, 50), (130, 255, 255))],
    "purple": [((131, 60, 50), (160, 255, 255))],
}
BGR = {"red": (40, 40, 230), "orange": (0, 140, 255), "yellow": (0, 230, 230), "green": (60, 170, 60),
       "blue": (200, 80, 30), "purple": (170, 50, 130)}

@dataclass
class Det:
    colour: str; shape: str; cx: float; cy: float; w: float; h: float; area: float; label: str = ""

def bearing_deg(cx):            # + = right of image centre
    return math.degrees(math.atan((cx - W / 2) / FX))

def floor_distance(v_bottom):   # metres, object standing on a flat floor
    a = TILT + math.atan((v_bottom - H / 2) / FX)
    return CAM_H / math.tan(a) if a > 0.01 else 9.9

def _shape(c):
    """Rotation-independent: rect-fill ratio r (square ~0.95, circle ~0.79, triangle ~0.5) and radius spread q."""
    area = cv2.contourArea(c); m = cv2.moments(c)
    if area < 4 or m["m00"] == 0: return "polygon"
    (_, _), (rw, rh), _ = cv2.minAreaRect(c)
    if rw < 1 or rh < 1: return "polygon"
    r = area / (rw * rh)
    d = np.hypot(c[:, 0, 0] - m["m10"] / m["m00"], c[:, 0, 1] - m["m01"] / m["m00"]); q = d.max() / max(d.min(), 1e-3)
    boxy = "square" if min(rw, rh) / max(rw, rh) > 0.8 else "rectangle"
    if r < 0.66: return "triangle"
    if r >= 0.88: return boxy
    return "circle" if q < 1.25 else (boxy if r > 0.8 else "polygon")

def detect(frame, min_area=int(30 * (W / 320) ** 2)):
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV); out = []; k = np.ones((3, 3), np.uint8)
    for name, ranges in COLOURS.items():
        m = sum(cv2.inRange(hsv, np.array(lo), np.array(hi)) for lo, hi in ranges)
        m = cv2.morphologyEx(cv2.morphologyEx(m, cv2.MORPH_OPEN, k), cv2.MORPH_CLOSE, k)
        for c in cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)[0]:
            a = cv2.contourArea(c)
            if a < min_area: continue
            x, y, w, h = cv2.boundingRect(c)
            out.append(Det(name, _shape(c), x + w / 2, y + h / 2, w, h, a))
    return out

class Tracker:
    """Keeps the same letter on the same object, and the most common shape seen over the last frames."""
    def __init__(self): self.tracks = {}; self.next = 0   # label -> [Det, missed, shape history]
    def update(self, dets):
        used = set()
        for d in sorted(dets, key=lambda d: -d.area):
            best, bd = None, 80 * W / 320
            for lab, (t, _, _) in self.tracks.items():
                dist = math.hypot(t.cx - d.cx, t.cy - d.cy)
                if lab not in used and t.colour == d.colour and dist < bd: best, bd = lab, dist
            if best is None:
                best = chr(65 + self.next % 26); self.next += 1; self.tracks[best] = [d, 0, []]
            hist = self.tracks[best][2]
            if d.cx - d.w / 2 > 2 and d.cx + d.w / 2 < W - 2:      # shape is unreliable when cut by the image edge
                hist.append(d.shape); del hist[:-9]
            if hist: d.shape = max(set(hist), key=hist.count)
            d.label = best; used.add(best); self.tracks[best] = [d, 0, hist]
        for lab in list(self.tracks):
            if lab not in used:
                self.tracks[lab][1] += 1
                if self.tracks[lab][1] > 10: del self.tracks[lab]
        return sorted(dets, key=lambda d: d.label)

def pick_target(dets, target):
    c = [d for d in dets if (not target.label or d.label == target.label)
         and (not target.colour or d.colour == target.colour) and (not target.shape or d.shape == target.shape)]
    return max(c, key=lambda d: d.area) if c else None

def annotate(img, dets, target, text):
    img = img.copy(); hit = pick_target(dets, target) if target else None
    for d in dets:
        x, y, w, h = int(d.cx - d.w / 2), int(d.cy - d.h / 2), int(d.w), int(d.h)
        col, th = ((0, 255, 0), 2) if d is hit else ((255, 255, 255), 1)
        cv2.rectangle(img, (x, y), (x + w, y + h), col, th)
        cv2.putText(img, f"{d.label} {d.colour} {d.shape}", (x, max(10, y - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.4, col, 1)
    cv2.putText(img, text, (6, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
    cv2.line(img, (W // 2 - 6, H // 2), (W // 2 + 6, H // 2), (255, 255, 255), 1)
    cv2.line(img, (W // 2, H // 2 - 6), (W // 2, H // 2 + 6), (255, 255, 255), 1)
    return img

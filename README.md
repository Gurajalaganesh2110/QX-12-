# Q12-X console and brain

Laptop software for the Q12-X quadruped (ESP32-S3 CAM + Raspberry Pi Pico 2).
Runs from a USB stick. Browser UI + a Python "brain" that does the vision and the automatic mission.

## Run
    python run.py                       # simulation: built-in fake robot + camera (no robot needed)
    python run.py --robot 192.168.4.1   # real robot (ESP32 IP)
Windows: double-click `start.bat`   Linux/macOS: `./start.sh`   (first run installs packages)
Manual install if the scripts fail: `pip install -r requirements.txt` then `python run.py`
Add `--lan` to open the page from a phone on the same Wi-Fi.
Check everything works: `python -m tests.smoke_test`

## How it fits together
    Browser UI (ui/) <-> brain/server.py <-> brain/link.py --ws://ROBOT:5621--> ESP32 --UART--> Pico 2
                                   ^ brain/video.py <--MJPEG http://ROBOT:90/stream-- ESP32 camera
    brain/vision.py   colour + shape detection, A/B/C labels
    brain/mission.py  SEARCH -> APPROACH -> ALIGN -> PICK -> DONE
    brain/diagnostics.py  self-check table      sim/fake_robot.py  pretend robot for demos and tests

## What the ESP32 firmware must provide (binary frames, little-endian, see brain/protocol.py)
| Module (id) | Action | Payload |
|---|---|---|
| System (0) | 0 ping | empty reply |
| Gait (2) | 0 set type | u8: 0 creep, 1 walk, 2 run, 3 jump |
| Body (3) | 2 set velocity | 3 x f32: vx m/s forward, vy m/s left, wz rad/s turn-left. Stop if nothing arrives for 300 ms |
| Head (32) | 0 set pan / 1 get pan | f32 degrees, + = right |
| Distance (33) | 0 read | u16 mm (sensor mounted on the camera head) |
| Arm (34) | 0 pick / 1 place | reply u8: 1 = success |
| Action (35) | 0 run | u8: 1 stand, 2 sit, 3 bounce, 4 wave |
| Self-test (36) | 0 run | reply string (u16 length + JSON): pico_link, camera, tof, servos, battery_v, rssi |
Video: MJPEG on port 90, any path (the simulator uses 8090 so it needs no admin rights). Modules 0-20 follow the TNY-360 SDK (MIT); 32+ are ours.

## Tuning constants
Camera model: `brain/vision.py` (W, H, HFOV, CAM_H, TILT). W,H must equal your stream size (VGA 640x480 here). Pick distance: `brain/mission.py` (PICK_DIST).
Measure your own camera height and tilt, they decide how well distance is estimated.

## Known limits
Shape names are about 98% right from 0.2 to 1.8 m in the simulator (VGA); beyond ~2 m objects are too small to detect. Shape is unreliable when an object is cut by the image edge.
Search = sweep the camera -80..+80, turn the body 150 deg, sweep back (about 15 s worst case in the simulator).
Tested against the simulator only. The obstacle side-step is not covered by a test. Labels A/B/C can change
while the camera sweeps, so pick by colour/shape (the UI does). Colour ranges need tuning under your lighting.

## Licence note
The protocol matches the TNY-360 SDK (MIT). No code from the TNY-360-Web app (CC BY-NC-SA 4.0) is copied here.
If you later port its pages, keep the credit and the same licence. Add your own LICENSE file.

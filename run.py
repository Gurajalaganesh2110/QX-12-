"""Q12-X console + brain.
   python run.py                 -> simulation (no robot needed)
   python run.py --robot IP      -> real robot, e.g. python run.py --robot 192.168.4.1
   add --lan to open the page from a phone on the same Wi-Fi."""
import argparse, threading, webbrowser
import uvicorn
from brain.server import create_app

ap = argparse.ArgumentParser()
ap.add_argument("--sim", action="store_true", help="simulation (default when --robot is not given)")
ap.add_argument("--robot", help="robot IP or host name (the ESP32)")
ap.add_argument("--port", type=int, default=8000)
ap.add_argument("--lan", action="store_true", help="let other devices on your network open the page")
ap.add_argument("--no-browser", action="store_true")
a = ap.parse_args()
sim = a.sim or not a.robot
print("\n  Q12-X console:", "SIMULATION (fake robot)" if sim else f"robot at {a.robot}")
print(f"  Open  http://localhost:{a.port}   (Ctrl+C to quit)\n")
app = create_app(default_ip=None if sim else a.robot, sim=sim)
if not a.no_browser:
    threading.Timer(1.5, lambda: webbrowser.open(f"http://localhost:{a.port}")).start()
uvicorn.run(app, host="0.0.0.0" if a.lan else "127.0.0.1", port=a.port, log_level="warning")

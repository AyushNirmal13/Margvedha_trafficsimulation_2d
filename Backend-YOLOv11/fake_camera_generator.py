#!/usr/bin/env python3
"""
MargVedha: Fake Camera Data Generator
Generates realistic vehicle count data for 76 fake cameras (time-of-day aware).
Pushes data to Flask API every N seconds.
"""

import json
import random
import threading
import time
import argparse
from datetime import datetime

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    print("[WARNING] 'requests' not installed. Run: pip install requests")

# ─── Nashik intersection names for 76 fake cameras ───────────────────────────
NASHIK_INTERSECTIONS = [
    "CBS Chowk", "Gangapur Road Junction", "College Road Crossing",
    "Dwarka Circle", "Panchavati Circle", "Mahatma Nagar Chowk",
    "Satpur MIDC Gate", "Ambad MIDC Gate", "Nashik Road Station",
    "Deolali Camp Entry", "Sharanpur Road Cross", "Ashok Stambh",
    "MG Road Junction", "Cidco Square", "Trimbak Road Fork",
    "Sinnar Phata", "Dindori Road Entry", "Igatpuri Road Toll",
    "Gonde Dumala", "Ojhar Airport Road", "Adgaon Naka",
    "Pathardi Phata", "Borwand Junction", "Mhasrul Phata",
    "Nashik-Pune Highway Entry", "Nashik-Mumbai Highway Entry",
    "Manmad Road Junction", "Aurangabad Road Split",
    "Chandwad Phata", "Yeola Road Naka", "Nandgaon Cross",
    "Malegaon Road Entry", "Kalwan Gate", "Surgana Turn",
    "Igatpuri Ghat Top", "Ghatandevi turn", "Kasara Border",
    "Sinner Chowk", "Niphad Junction", "Vinchur Phata",
    "Lasalgaon Market", "Pimpalgaon Cross", "Chandori Naka",
    "Dabhadi Junction", "Satana Phata", "Malegaon Highway Toll",
    "Chandwad Old Naka", "Nandur Madhyameshwar Cross",
    "Rahuri Road Fork", "Kopargaon Junction",
    "Shivaji Nagar Gate", "Nashik East Station", "Cidco Bus Stop Cross",
    "Ganesh Wadi Junction", "Peth Road Circle", "Amberi Road",
    "Jailroad Circle", "Nashik West Plaza", "Dwarka Market Cross",
    "Tapovan Area", "Anandwali Gate", "Nashik Phata (Pune Road)",
    "Nashik Phata (Mumbai Road)", "Makrane Circle", "Rajiv Nagar Chowk",
    "Pandav Leni Road", "Nashik Village Entry", "Indira Nagar Gate",
    "Ramwadi Junction", "Jail Road Entry", "Bhagur Naka",
    "Panchak Circle", "Nashik Road Chowk 2", "Deolali Bus Stand",
    "Nashik Central Cross", "Vishrantwadi Gate",
]

# ─── Time-of-day traffic multipliers ─────────────────────────────────────────
def get_traffic_multiplier():
    """Returns a multiplier (0.1 to 1.0) based on current hour."""
    hour = datetime.now().hour
    if 8 <= hour <= 10:      # Morning rush
        return random.uniform(0.8, 1.0)
    elif 17 <= hour <= 20:   # Evening rush
        return random.uniform(0.75, 1.0)
    elif 12 <= hour <= 14:   # Lunch hour moderate
        return random.uniform(0.4, 0.6)
    elif 23 <= hour or hour <= 5:  # Night
        return random.uniform(0.05, 0.15)
    else:                    # Normal daytime
        return random.uniform(0.25, 0.5)

def generate_fake_count(cam_id: str, cam_name: str):
    """Generate a realistic vehicle count snapshot for one fake camera."""
    multiplier = get_traffic_multiplier()
    BASE = 60  # max vehicles in time window

    return {
        "camera_id": cam_id,
        "camera_name": cam_name,
        "type": "fake",
        "timestamp": time.time(),
        "timestamp_human": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "counts": {
            "incoming": {
                "car":   int(random.randint(5, BASE) * multiplier),
                "bus":   int(random.randint(0, 10)   * multiplier),
                "truck": int(random.randint(0, 5)    * multiplier),
            },
            "outgoing": {
                "car":   int(random.randint(5, BASE) * multiplier),
                "bus":   int(random.randint(0, 10)   * multiplier),
                "truck": int(random.randint(0, 5)    * multiplier),
            }
        }
    }

# ─── Single camera worker thread ─────────────────────────────────────────────
class FakeCameraWorker(threading.Thread):
    def __init__(self, cam_id, cam_name, api_url, interval=30):
        super().__init__(daemon=True)
        self.cam_id = cam_id
        self.cam_name = cam_name
        self.api_url = api_url
        self.interval = interval
        self.last_data = None
        self._stop_event = threading.Event()

    def run(self):
        while not self._stop_event.is_set():
            data = generate_fake_count(self.cam_id, self.cam_name)
            self.last_data = data  # store for local access

            # Push to Flask API
            if REQUESTS_AVAILABLE and self.api_url:
                try:
                    resp = requests.post(
                        f"{self.api_url}/submit_count",
                        json=data,
                        timeout=5
                    )
                    if resp.status_code != 200:
                        print(f"[FAKE][{self.cam_id}] API error: {resp.status_code}")
                except Exception as e:
                    print(f"[FAKE][{self.cam_id}] Could not reach API: {e}")
            else:
                # Print to console if no API
                print(f"[FAKE][{self.cam_id}] {data['counts']}")

            self._stop_event.wait(self.interval)

    def stop(self):
        self._stop_event.set()

# ─── Orchestrator: starts all 76 fake camera threads ─────────────────────────
class FakeCameraOrchestrator:
    def __init__(self, api_url: str = None, interval: int = 30, start_index: int = 4):
        """
        Args:
            api_url:     Flask API base URL (e.g., http://localhost:5001)
            interval:    How often to send data (seconds)
            start_index: Camera ID numbering starts here (default 4 = after 4 real cams)
        """
        self.api_url = api_url
        self.interval = interval
        self.start_index = start_index
        self.workers = []

    def start(self):
        print(f"[FakeCamGen] Starting {len(NASHIK_INTERSECTIONS)} fake camera workers...")
        for i, name in enumerate(NASHIK_INTERSECTIONS):
            cam_id = f"cam{self.start_index + i + 1}_fake"
            worker = FakeCameraWorker(cam_id, name, self.api_url, self.interval)
            worker.start()
            self.workers.append(worker)
        print(f"[FakeCamGen] All {len(self.workers)} fake cameras running. Sending data every {self.interval}s.")

    def stop(self):
        for w in self.workers:
            w.stop()
        print("[FakeCamGen] All fake cameras stopped.")

    def get_all_latest(self):
        """Returns the latest snapshot from all fake cameras (for local use)."""
        return {w.cam_id: w.last_data for w in self.workers if w.last_data}


# ─── Main entry point ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MargVedha Fake Camera Data Generator")
    parser.add_argument("--api",      default="http://localhost:5001", help="Flask API base URL")
    parser.add_argument("--interval", type=int, default=30,            help="Seconds between each send")
    args = parser.parse_args()

    orchestrator = FakeCameraOrchestrator(api_url=args.api, interval=args.interval)
    orchestrator.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[FakeCamGen] Shutting down...")
        orchestrator.stop()

#!/usr/bin/env python3
"""
SIH25050: Real time Traffic Optimization System for Urban Congestion.
Author: Team Marg Vedha 3.0
"""

import argparse
import json
import math
import os
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Dict, Tuple

import cv2
import numpy as np
import pandas as pd
from ultralytics import YOLO
from tqdm import tqdm

try:
    import requests as _requests
    _REQUESTS_OK = True
except ImportError:
    _REQUESTS_OK = False

# Flask API endpoint — set via --api-url arg or env variable
FLASK_API_URL = os.environ.get("MARGVEDHA_API_URL", "http://localhost:5001")

def push_result_to_api(result: Dict, api_url: str = FLASK_API_URL):
    """Push final camera count result to Flask API after processing."""
    if not _REQUESTS_OK or not api_url:
        return
    payload = {
        "camera_id":   result.get("camera_id"),
        "camera_name": result.get("camera_id"),  # name same as id if not set
        "type":        "real",
        "timestamp":   time.time(),
        "timestamp_human": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "counts":      result.get("counts", {})
    }
    try:
        resp = _requests.post(f"{api_url}/submit_count", json=payload, timeout=5)
        print(f"[API] Pushed {result.get('camera_id')} → {resp.status_code}")
    except Exception as e:
        print(f"[API] Push failed for {result.get('camera_id')}: {e}")

# ---------- Utilities ----------
def now_epoch():
    return float(time.time())

def epoch_to_hms(ts):
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

def point_side_of_line(pt: Tuple[float, float], a: Tuple[float, float], b: Tuple[float, float]) -> float:
    (x, y) = pt
    (x1, y1), (x2, y2) = a, b
    return (x2 - x1) * (y - y1) - (y2 - y1) * (x - x1)

def centroid_from_xyxy(xyxy):
    x1, y1, x2, y2 = xyxy
    return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)

# ---------- Camera Processor ----------
class CameraProcessor:
    def __init__(self, cam_cfg: Dict, output_dir: str):
        self.id = cam_cfg.get("id", f"cam_{int(time.time()*1000)%10000}")
        self.name = cam_cfg.get("name", self.id)
        self.source = cam_cfg["source"]
        self.weights = cam_cfg.get("weights", "yolov11m.pt")
        self.split_line = tuple(cam_cfg.get("split_line", [640, 0, 640, 720]))
        self.frame_scale = float(cam_cfg.get("frame_scale", 1.0))
        self.out_video = os.path.join(output_dir, cam_cfg.get("out_video", f"{self.id}_out.mp4"))
        self.model = YOLO(self.weights)

        # data
        self.track_last_side = {}
        self.counts = {'incoming': defaultdict(int), 'outgoing': defaultdict(int)}
        self.events = []  
        self.target_names = ['car', 'bus', 'truck']
        self.class_map = {}
        self.writer = None
        self.output_dir = output_dir

        # files
        self.events_ndjson = os.path.join(output_dir, f"{self.id}_events.ndjson")
        self.summary_json = os.path.join(output_dir, f"{self.id}_summary_live.json")
        self.summary_csv = os.path.join(output_dir, f"{self.id}_events.csv")

        Path(output_dir).mkdir(parents=True, exist_ok=True)

    def map_class_names(self, result):
        try:
            self.class_map = self.model.names if hasattr(self.model, 'names') else result.model.names
        except Exception:
            self.class_map = {2: 'car', 5: 'bus', 7: 'truck'}

    def side_label_from_signed(self, signed_value):
        return 'A' if signed_value > 0 else 'B'

    def side_to_direction(self, prev_side, new_side):
        if prev_side is None:
            return None
        if prev_side == 'A' and new_side == 'B':
            return 'outgoing'
        if prev_side == 'B' and new_side == 'A':
            return 'incoming'
        return None

    def initialize_writer(self, frame_shape, fps=20):
        h, w = frame_shape[:2]
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        self.writer = cv2.VideoWriter(self.out_video, fourcc, fps, (w, h))

    def persist_event_live(self, event: Dict):
        """Append event as single-line NDJSON and update live summary JSON."""
        # append to ndjson
        with open(self.events_ndjson, 'a') as f:
            f.write(json.dumps(event) + "\n")
        # update in-memory and write summary JSON
        self.events.append(event)
        # write summary JSON (overwrite)
        summary = {
            'camera_id': self.id,
            'camera_name': self.name,
            'counts': {
                'incoming': dict(self.counts['incoming']),
                'outgoing': dict(self.counts['outgoing'])
            },
            'last_event_time': epoch_to_hms(event['timestamp']),
            'events_logged': len(self.events)
        }
        with open(self.summary_json, 'w') as f:
            json.dump(summary, f, indent=2)

    def finalize(self):
        # release writer, dump csv
        if self.writer:
            self.writer.release()
        # dump final CSV of events
        if len(self.events) > 0:
            df = pd.DataFrame(self.events)
            df.to_csv(self.summary_csv, index=False)
        # final summary JSON
        final = {
            'camera_id': self.id,
            'camera_name': self.name,
            'counts': {
                'incoming': dict(self.counts['incoming']),
                'outgoing': dict(self.counts['outgoing'])
            },
            'events': self.events
        }
        with open(os.path.join(self.output_dir, f"{self.id}_final_summary.json"), 'w') as f:
            json.dump(final, f, indent=2)

    def process(self, max_frames: int = None, verbose: bool = True):

        if verbose:
            print(f"[{self.id}] Starting. source={self.source} weights={self.weights}")

        # stream=True yields per-frame results
        # stream = self.model.track(source=self.source, tracker='botsort', persist=True, stream=True, show=False)
        stream = self.model.track(source=self.source, tracker='botsort.yaml', persist=True, stream=True, show=False)

        first_frame = True
        frame_count = 0
        fps = 20
        a = (self.split_line[0], self.split_line[1])
        b = (self.split_line[2], self.split_line[3])

        try:
            for result in stream:
                # extract frame
                frame = None
                if hasattr(result, 'orig_img') and result.orig_img is not None:
                    frame = result.orig_img
                elif hasattr(result, 'orig_frame') and result.orig_frame is not None:
                    frame = result.orig_frame
                else:
                    # some ultralytics builds use result.imgs or similar, skip if not found
                    continue

                if frame is None:
                    continue

                frame_count += 1
                if first_frame:
                    # map classes and init writer
                    self.map_class_names(result)
                    try:
                        cap = cv2.VideoCapture(self.source)
                        if cap.isOpened():
                            fps_try = cap.get(cv2.CAP_PROP_FPS)
                            if fps_try and fps_try > 1:
                                fps = int(fps_try)
                            cap.release()
                    except Exception:
                        pass
                    self.initialize_writer(frame.shape, fps=fps)
                    first_frame = False

                # draw split line
                cv2.line(frame, (int(a[0]), int(a[1])), (int(b[0]), int(b[1])), (0,255,255), 2)

                # parse boxes
                boxes = []
                ids = []
                classes = []
                scores = []
                try:
                    for box in result.boxes:
                        # handle various ultralytics versions
                        try:
                            xyxy = box.xyxy.squeeze().tolist() if hasattr(box.xyxy, 'squeeze') else box.xyxy.tolist()
                        except Exception:
                            xyxy = box.xyxy.tolist() if hasattr(box, 'xyxy') else None
                        conf = float(getattr(box, 'conf', getattr(box, 'confidence', 0.0)))
                        cls = int(getattr(box, 'cls', getattr(box, 'cls_id', -1)))
                        tid = int(getattr(box, 'id', getattr(box, 'track_id', -1)))
                        if xyxy is None:
                            continue
                        boxes.append(xyxy)
                        ids.append(tid)
                        classes.append(cls)
                        scores.append(conf)
                except Exception:
                    # fallback to numpy arrays if available
                    try:
                        arr_xyxy = result.boxes.xyxy.cpu().numpy()
                        arr_cls = result.boxes.cls.cpu().numpy().astype(int)
                        arr_id = result.boxes.id.cpu().numpy().astype(int)
                        arr_conf = result.boxes.conf.cpu().numpy()
                        for xyxy, cls_, tid_, conf_ in zip(arr_xyxy, arr_cls, arr_id, arr_conf):
                            boxes.append(xyxy.tolist())
                            ids.append(int(tid_))
                            classes.append(int(cls_))
                            scores.append(float(conf_))
                    except Exception:
                        boxes, ids, classes, scores = [], [], [], []

                # for each detection of interest, evaluate crossing
                for xyxy, tid, cls_idx, conf in zip(boxes, ids, classes, scores):
                    cls_name = self.class_map.get(cls_idx, str(cls_idx))
                    if cls_name not in self.target_names:
                        continue
                    centroid = centroid_from_xyxy(xyxy)
                    signed = point_side_of_line(centroid, a, b)
                    new_side = self.side_label_from_signed(signed)
                    prev_side = self.track_last_side.get(tid, None)
                    self.track_last_side[tid] = new_side

                    # crossing detection
                    if prev_side is not None and prev_side != new_side:
                        direction = self.side_to_direction(prev_side, new_side)
                        if direction is not None:
                            self.counts[direction][cls_name] += 1
                            event = {
                                'frame': frame_count,
                                'timestamp': now_epoch(),
                                'timestamp_human': epoch_to_hms(now_epoch()),
                                'track_id': int(tid),
                                'class': cls_name,
                                'direction': direction,
                                'centroid': [float(centroid[0]), float(centroid[1])],
                                'confidence': float(conf),
                                'camera_id': self.id,
                                'camera_name': self.name
                            }
                            # persist live
                            self.persist_event_live(event)

                # draw boxes + labels
                for xyxy, tid, cls_idx, conf in zip(boxes, ids, classes, scores):
                    cls_name = self.class_map.get(cls_idx, str(cls_idx))
                    if cls_name not in self.target_names:
                        continue
                    x1,y1,x2,y2 = map(int, xyxy)
                    cv2.rectangle(frame, (x1,y1), (x2,y2), (0,255,0), 2)
                    label = f"{cls_name}:{tid}"
                    cv2.putText(frame, label, (x1, y1 - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 1)

                # overlay counts
                left = 10
                top = 20
                for direction in ['incoming','outgoing']:
                    text = f"{direction.upper()} - car:{self.counts[direction].get('car',0)} bus:{self.counts[direction].get('bus',0)} truck:{self.counts[direction].get('truck',0)}"
                    cv2.putText(frame, text, (left, top), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,0,0), 3)
                    cv2.putText(frame, text, (left, top), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255,255,255), 1)
                    top += 30

                # write frame to output
                if self.writer:
                    self.writer.write(frame)

                # stop if max_frames specified (for quick dev runs)
                if max_frames and frame_count >= max_frames:
                    break

        except KeyboardInterrupt:
            print(f"[{self.id}] Interrupted by user.")
        except Exception as e:
            print(f"[{self.id}] Error during processing: {e}")
        finally:
            # finalize outputs
            self.finalize()
            if os.path.exists(self.events_ndjson):
                print(f"[{self.id}] Events NDJSON: {self.events_ndjson}")
            print(f"[{self.id}] Final counts: {json.dumps({k:dict(v) for k,v in self.counts.items()})}")
            return {
                'camera_id': self.id,
                'counts': {k: dict(v) for k,v in self.counts.items()}
            }

# ---------- Orchestration ----------
def load_config(path):
    with open(path, 'r') as f:
        return json.load(f)

def _run_camera(cam, output_dir, max_frames, api_url):
    """Worker function for a single real camera — runs in its own thread."""
    proc = CameraProcessor(cam, output_dir=output_dir)
    res = proc.process(max_frames=max_frames, verbose=True)
    if res:
        # Set proper camera name from config
        res["camera_name"] = cam.get("name", res["camera_id"])
        push_result_to_api(res, api_url)
    return res


def main(config_path, output_dir, max_frames: int = None, api_url: str = FLASK_API_URL, max_workers: int = 4):
    cfg = load_config(config_path)
    # Only process cameras marked as 'real' (or without a type field)
    all_cameras = cfg.get('cameras', [])
    real_cameras = [c for c in all_cameras if c.get('type', 'real') == 'real']

    print(f"[Main] Found {len(real_cameras)} real cameras. Running up to {max_workers} in parallel.")
    results = []

    # ── Parallel execution with ThreadPoolExecutor ───────────────────────────
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_run_camera, cam, output_dir, max_frames, api_url): cam
            for cam in real_cameras
        }
        for future in as_completed(futures):
            cam = futures[future]
            try:
                res = future.result()
                if res:
                    results.append(res)
            except Exception as e:
                print(f"[Main] Camera {cam.get('id')} failed: {e}")

    # Aggregate all real camera results
    agg = {r['camera_id']: r['counts'] for r in results if r}
    agg_path = os.path.join(output_dir, "aggregate_counts_live.json")
    with open(agg_path, 'w') as f:
        json.dump(agg, f, indent=2)
    print(f"[Main] All real cameras processed. Aggregate saved to {agg_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="YOLOv11 + BoT-SORT traffic counting (live JSON)")
    parser.add_argument('--config',      required=True,                    help='Path to cameras_config.json')
    parser.add_argument('--out',         default='outputs',                help='Output directory')
    parser.add_argument('--max-frames',  type=int,   default=None,         help='Dev: stop after N frames per camera')
    parser.add_argument('--max-workers', type=int,   default=4,            help='Max parallel camera threads (default: 4)')
    parser.add_argument('--api-url',     default=FLASK_API_URL,            help='Flask API URL to push results')
    args = parser.parse_args()
    main(
        config_path=args.config,
        output_dir=args.out,
        max_frames=args.max_frames,
        api_url=args.api_url,
        max_workers=args.max_workers
    )

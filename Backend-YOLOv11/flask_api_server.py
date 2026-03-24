#!/usr/bin/env python3
"""
MargVedha: Flask API Server
Collects vehicle count data from real (YOLOv11) and fake cameras.
Stores in MongoDB. Exposes endpoints for RL model consumption.
"""

import json
import time
from datetime import datetime
from flask import Flask, request, jsonify

# ─── MongoDB Setup ─────────────────────────────────────────────────────────────
try:
    from pymongo import MongoClient, DESCENDING
    client = MongoClient("mongodb://localhost:27017/", serverSelectionTimeoutMS=3000)
    client.server_info()  # Test connection
    db = client["margvedha"]
    traffic_col = db["traffic_counts"]
    MONGO_AVAILABLE = True
    print("[API] Connected to MongoDB (local).")
except Exception as e:
    MONGO_AVAILABLE = False
    print(f"[API] MongoDB NOT available ({e}). Using in-memory fallback.")

# ─── In-memory fallback store ──────────────────────────────────────────────────
# Structure: { camera_id: {latest_snapshot} }
IN_MEMORY_STORE = {}

# ─── Flask App ─────────────────────────────────────────────────────────────────
app = Flask(__name__)

# ══════════════════════════════════════════════════════════════════════════════
# ENDPOINT 1: Receive count from any camera (real or fake)
# POST /submit_count
# Body: { camera_id, camera_name, type, timestamp, counts: {incoming, outgoing} }
# ══════════════════════════════════════════════════════════════════════════════
@app.route("/submit_count", methods=["POST"])
def submit_count():
    data = request.get_json(silent=True)
    if not data or "camera_id" not in data:
        return jsonify({"error": "Invalid payload. 'camera_id' is required."}), 400

    # Add server-received timestamp
    data["server_received_at"] = datetime.utcnow().isoformat()

    # Save to MongoDB (or in-memory)
    if MONGO_AVAILABLE:
        try:
            traffic_col.insert_one(data)
            # Remove MongoDB _id before response (not JSON serializable)
            data.pop("_id", None)
        except Exception as e:
            return jsonify({"error": f"MongoDB write failed: {e}"}), 500
    else:
        IN_MEMORY_STORE[data["camera_id"]] = data

    return jsonify({"status": "ok", "camera_id": data["camera_id"]}), 200


# ══════════════════════════════════════════════════════════════════════════════
# ENDPOINT 2: Get latest snapshot for ALL cameras (for RL model)
# GET /traffic_data
# Returns: { camera_id: {counts}, ... } for all 80 cameras
# ══════════════════════════════════════════════════════════════════════════════
@app.route("/traffic_data", methods=["GET"])
def traffic_data():
    if MONGO_AVAILABLE:
        # Get the latest record per camera_id using aggregation
        pipeline = [
            {"$sort": {"server_received_at": -1}},
            {"$group": {
                "_id": "$camera_id",
                "camera_name": {"$first": "$camera_name"},
                "type":        {"$first": "$type"},
                "counts":      {"$first": "$counts"},
                "timestamp":   {"$first": "$timestamp_human"},
            }},
            {"$project": {"_id": 0, "camera_id": "$_id",
                          "camera_name": 1, "type": 1,
                          "counts": 1, "timestamp": 1}}
        ]
        results = list(traffic_col.aggregate(pipeline))
        return jsonify({"total_cameras": len(results), "data": results}), 200
    else:
        # In-memory fallback
        out = []
        for cam_id, snap in IN_MEMORY_STORE.items():
            snap_clean = {k: v for k, v in snap.items() if k != "_id"}
            out.append(snap_clean)
        return jsonify({"total_cameras": len(out), "data": out}), 200


# ══════════════════════════════════════════════════════════════════════════════
# ENDPOINT 3: Human-readable live dashboard summary
# GET /live_dashboard
# ══════════════════════════════════════════════════════════════════════════════
@app.route("/live_dashboard", methods=["GET"])
def live_dashboard():
    if MONGO_AVAILABLE:
        pipeline = [
            {"$sort": {"server_received_at": -1}},
            {"$group": {
                "_id": "$camera_id",
                "camera_name": {"$first": "$camera_name"},
                "type":        {"$first": "$type"},
                "counts":      {"$first": "$counts"},
                "last_seen":   {"$first": "$timestamp_human"},
            }}
        ]
        results = list(traffic_col.aggregate(pipeline))
    else:
        results = [
            {
                "_id": snap["camera_id"],
                "camera_name": snap.get("camera_name", "?"),
                "type":        snap.get("type", "?"),
                "counts":      snap.get("counts", {}),
                "last_seen":   snap.get("timestamp_human", "?"),
            }
            for snap in IN_MEMORY_STORE.values()
        ]

    # Build summary
    total_incoming = {"car": 0, "bus": 0, "truck": 0}
    total_outgoing = {"car": 0, "bus": 0, "truck": 0}
    real_count = 0
    fake_count = 0

    for r in results:
        counts = r.get("counts", {})
        inc = counts.get("incoming", {})
        out = counts.get("outgoing", {})
        for v in ["car", "bus", "truck"]:
            total_incoming[v] += inc.get(v, 0)
            total_outgoing[v] += out.get(v, 0)
        if r.get("type") == "fake":
            fake_count += 1
        else:
            real_count += 1

    dashboard = {
        "as_of": datetime.utcnow().isoformat(),
        "cameras_reporting": len(results),
        "real_cameras": real_count,
        "fake_cameras": fake_count,
        "city_total_incoming": total_incoming,
        "city_total_outgoing": total_outgoing,
        "grand_total_vehicles": {
            "incoming": sum(total_incoming.values()),
            "outgoing": sum(total_outgoing.values()),
        },
        "per_camera": [
            {
                "camera_id":   r.get("_id", r.get("camera_id")),
                "camera_name": r.get("camera_name"),
                "type":        r.get("type"),
                "last_seen":   r.get("last_seen"),
                "incoming":    r.get("counts", {}).get("incoming", {}),
                "outgoing":    r.get("counts", {}).get("outgoing", {}),
            }
            for r in results
        ]
    }
    return jsonify(dashboard), 200


# ══════════════════════════════════════════════════════════════════════════════
# ENDPOINT 4: Health check
# GET /health
# ══════════════════════════════════════════════════════════════════════════════
@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "running",
        "mongo": "connected" if MONGO_AVAILABLE else "in-memory fallback",
        "time": datetime.utcnow().isoformat()
    }), 200


# ══════════════════════════════════════════════════════════════════════════════
# ENDPOINT 5: RL Model input — aggregated per intersection (20 intersections)
# GET /rl_input
# Returns city-level aggregated data grouped by intersection (for RL model)
# ══════════════════════════════════════════════════════════════════════════════
@app.route("/rl_input", methods=["GET"])
def rl_input():
    """
    Designed for the Reinforcement Learning model.
    Returns per-camera snapshot that the RL model can use as state.
    Format: list of { camera_id, total_vehicles_incoming, total_vehicles_outgoing, timestamp }
    """
    if MONGO_AVAILABLE:
        pipeline = [
            {"$sort": {"server_received_at": -1}},
            {"$group": {
                "_id":       "$camera_id",
                "camera_name": {"$first": "$camera_name"},
                "counts":    {"$first": "$counts"},
                "last_seen": {"$first": "$timestamp_human"},
            }}
        ]
        results = list(traffic_col.aggregate(pipeline))
    else:
        results = [
            {
                "_id":  snap["camera_id"],
                "camera_name": snap.get("camera_name"),
                "counts": snap.get("counts", {}),
                "last_seen": snap.get("timestamp_human"),
            }
            for snap in IN_MEMORY_STORE.values()
        ]

    rl_state = []
    for r in results:
        inc = r.get("counts", {}).get("incoming", {})
        out = r.get("counts", {}).get("outgoing", {})
        rl_state.append({
            "camera_id":              r.get("_id", r.get("camera_id")),
            "camera_name":            r.get("camera_name"),
            "total_vehicles_incoming": sum(inc.values()),
            "total_vehicles_outgoing": sum(out.values()),
            "incoming_breakdown":      inc,
            "outgoing_breakdown":      out,
            "last_seen":              r.get("last_seen"),
        })

    return jsonify({
        "rl_state_vector": rl_state,
        "camera_count":    len(rl_state),
        "generated_at":    datetime.utcnow().isoformat(),
    }), 200


# ─── Run ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("\n" + "="*55)
    print("  MargVedha Flask API Server")
    print("  Endpoints:")
    print("    POST /submit_count   ← cameras push data here")
    print("    GET  /traffic_data   ← all camera latest data")
    print("    GET  /live_dashboard ← human readable summary")
    print("    GET  /rl_input       ← for RL model consumption")
    print("    GET  /health         ← API health check")
    print("="*55 + "\n")
    app.run(host="0.0.0.0", port=5001, debug=False)

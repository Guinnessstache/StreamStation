#!/usr/bin/env python3
"""
StreamStation Web Server
Serves the management UI, TV guide, phone remote, and REST API.
"""

import os
import json
import socket
import logging
import subprocess
from pathlib import Path
from datetime import datetime
from functools import wraps

from flask import (
    Flask, render_template, jsonify, request,
    redirect, url_for, send_from_directory
)
from flask_socketio import SocketIO, emit

# ── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR       = Path(__file__).parent.parent
CHANNELS_FILE  = BASE_DIR / "streams" / "channels.json"
CONFIG_FILE    = BASE_DIR / "config" / "system.json"
RUNTIME_DIR    = BASE_DIR / "runtime"
STATUS_FILE    = RUNTIME_DIR / "current_channel.json"
CONTROL_SOCKET = RUNTIME_DIR / "control.socket"

app = Flask(__name__)
app.secret_key = os.urandom(24)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

log = logging.getLogger("streamstation.web")


# ── Helpers ───────────────────────────────────────────────────────────────────
def load_json(path):
    with open(path, "r") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def send_engine_command(cmd):
    """Send command to the running engine via UNIX socket."""
    if not CONTROL_SOCKET.exists():
        return None, "Engine not running"
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(3)
            s.connect(str(CONTROL_SOCKET))
            s.sendall((cmd + "\n").encode())
            resp = s.recv(4096).decode().strip()
            return resp, None
    except Exception as e:
        return None, str(e)


def get_status():
    try:
        return load_json(STATUS_FILE)
    except Exception:
        return {"channel": None, "state": "unknown", "name": None}


def get_channels_data():
    try:
        return load_json(CHANNELS_FILE)
    except Exception:
        return {"channels": [], "categories": []}


def get_config():
    try:
        return load_json(CONFIG_FILE)
    except Exception:
        return {}


def next_channel_id(channels):
    if not channels:
        return 1
    return max(ch.get("id", 0) for ch in channels) + 1


def engine_running():
    return CONTROL_SOCKET.exists()


# ── Page Routes ───────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return redirect(url_for("manage"))


@app.route("/manage")
def manage():
    data     = get_channels_data()
    status   = get_status()
    config   = get_config()
    return render_template(
        "manage.html",
        channels=data["channels"],
        categories=data["categories"],
        status=status,
        config=config,
        engine_running=engine_running(),
    )


@app.route("/guide")
def guide():
    data   = get_channels_data()
    status = get_status()
    channels = sorted(
        [ch for ch in data["channels"] if ch.get("enabled", True)],
        key=lambda c: c["number"],
    )
    return render_template(
        "guide.html",
        channels=channels,
        categories=data["categories"],
        status=status,
        engine_running=engine_running(),
        now=datetime.now(),
    )


@app.route("/remote")
def remote():
    data   = get_channels_data()
    status = get_status()
    channels = sorted(
        [ch for ch in data["channels"] if ch.get("enabled", True)],
        key=lambda c: c["number"],
    )
    categories = data["categories"]
    return render_template(
        "remote.html",
        channels=channels,
        categories=categories,
        status=status,
        engine_running=engine_running(),
    )


# ── REST API: Status ──────────────────────────────────────────────────────────
@app.route("/api/status")
def api_status():
    status = get_status()
    status["engine_running"] = engine_running()
    return jsonify(status)


# ── REST API: Control ─────────────────────────────────────────────────────────
@app.route("/api/tune/<int:channel>", methods=["POST"])
def api_tune(channel):
    resp, err = send_engine_command(f"TUNE {channel}")
    if err:
        return jsonify({"ok": False, "error": err}), 503
    ok = resp and resp.startswith("OK")
    if ok:
        socketio.emit("channel_changed", get_status())
    return jsonify({"ok": ok, "response": resp})


@app.route("/api/channel/up", methods=["POST"])
def api_channel_up():
    resp, err = send_engine_command("UP")
    if err:
        return jsonify({"ok": False, "error": err}), 503
    if resp and resp.startswith("OK"):
        socketio.emit("channel_changed", get_status())
    return jsonify({"ok": resp and resp.startswith("OK")})


@app.route("/api/channel/down", methods=["POST"])
def api_channel_down():
    resp, err = send_engine_command("DOWN")
    if err:
        return jsonify({"ok": False, "error": err}), 503
    if resp and resp.startswith("OK"):
        socketio.emit("channel_changed", get_status())
    return jsonify({"ok": resp and resp.startswith("OK")})


@app.route("/api/channel/last", methods=["POST"])
def api_channel_last():
    resp, err = send_engine_command("LAST")
    if err:
        return jsonify({"ok": False, "error": err}), 503
    if resp and resp.startswith("OK"):
        socketio.emit("channel_changed", get_status())
    return jsonify({"ok": resp and resp.startswith("OK")})


@app.route("/api/volume/<int:level>", methods=["POST"])
def api_volume(level):
    resp, err = send_engine_command(f"VOLUME {level}")
    if err:
        return jsonify({"ok": False, "error": err}), 503
    return jsonify({"ok": resp and resp.startswith("OK"), "volume": level})


# ── REST API: Channels CRUD ───────────────────────────────────────────────────
@app.route("/api/channels", methods=["GET"])
def api_get_channels():
    return jsonify(get_channels_data())


@app.route("/api/channels", methods=["POST"])
def api_add_channel():
    body = request.get_json()
    if not body:
        return jsonify({"ok": False, "error": "No JSON body"}), 400
    required = ["number", "name", "url", "category"]
    missing = [f for f in required if not body.get(f)]
    if missing:
        return jsonify({"ok": False, "error": f"Missing fields: {missing}"}), 400

    data = get_channels_data()
    # Check for duplicate channel number
    existing_numbers = [ch["number"] for ch in data["channels"]]
    if int(body["number"]) in existing_numbers:
        return jsonify({"ok": False, "error": "Channel number already in use"}), 409

    new_channel = {
        "id":       next_channel_id(data["channels"]),
        "number":   int(body["number"]),
        "name":     body["name"].strip(),
        "category": body["category"],
        "url":      body["url"].strip(),
        "logo":     body.get("logo", ""),
        "enabled":  bool(body.get("enabled", True)),
        "notes":    body.get("notes", ""),
        "added_at": datetime.now().isoformat(),
    }
    data["channels"].append(new_channel)
    save_json(CHANNELS_FILE, data)
    return jsonify({"ok": True, "channel": new_channel}), 201


@app.route("/api/channels/<int:channel_id>", methods=["PUT"])
def api_update_channel(channel_id):
    body = request.get_json()
    if not body:
        return jsonify({"ok": False, "error": "No JSON body"}), 400

    data = get_channels_data()
    for i, ch in enumerate(data["channels"]):
        if ch.get("id") == channel_id:
            # Check number conflict
            if "number" in body:
                new_num = int(body["number"])
                conflict = any(
                    c["number"] == new_num and c.get("id") != channel_id
                    for c in data["channels"]
                )
                if conflict:
                    return jsonify({"ok": False, "error": "Channel number in use"}), 409

            updatable = ["number", "name", "category", "url", "logo", "enabled", "notes"]
            for field in updatable:
                if field in body:
                    val = body[field]
                    if field == "number":
                        val = int(val)
                    elif field == "enabled":
                        val = bool(val)
                    data["channels"][i][field] = val
            data["channels"][i]["updated_at"] = datetime.now().isoformat()
            save_json(CHANNELS_FILE, data)
            return jsonify({"ok": True, "channel": data["channels"][i]})

    return jsonify({"ok": False, "error": "Channel not found"}), 404


@app.route("/api/channels/<int:channel_id>", methods=["DELETE"])
def api_delete_channel(channel_id):
    data = get_channels_data()
    original = len(data["channels"])
    data["channels"] = [ch for ch in data["channels"] if ch.get("id") != channel_id]
    if len(data["channels"]) == original:
        return jsonify({"ok": False, "error": "Channel not found"}), 404
    save_json(CHANNELS_FILE, data)
    return jsonify({"ok": True})


@app.route("/api/channels/<int:channel_id>/toggle", methods=["POST"])
def api_toggle_channel(channel_id):
    data = get_channels_data()
    for i, ch in enumerate(data["channels"]):
        if ch.get("id") == channel_id:
            data["channels"][i]["enabled"] = not ch.get("enabled", True)
            save_json(CHANNELS_FILE, data)
            return jsonify({"ok": True, "enabled": data["channels"][i]["enabled"]})
    return jsonify({"ok": False, "error": "Not found"}), 404


# ── REST API: M3U Import ──────────────────────────────────────────────────────
@app.route("/api/import/m3u", methods=["POST"])
def api_import_m3u():
    body = request.get_json()
    m3u_url = body.get("url", "").strip() if body else ""
    m3u_text = body.get("text", "").strip() if body else ""

    if m3u_url:
        import urllib.request
        try:
            with urllib.request.urlopen(m3u_url, timeout=15) as resp:
                m3u_text = resp.read().decode("utf-8", errors="replace")
        except Exception as e:
            return jsonify({"ok": False, "error": f"Failed to fetch M3U: {e}"}), 400

    if not m3u_text:
        return jsonify({"ok": False, "error": "No M3U content provided"}), 400

    # Parse M3U
    imported = []
    lines = m3u_text.strip().splitlines()
    current_info = {}
    for line in lines:
        line = line.strip()
        if line.startswith("#EXTINF"):
            current_info = {"name": "Unknown", "logo": "", "group": "Uncategorized"}
            # Extract name
            if "," in line:
                current_info["name"] = line.split(",", 1)[1].strip()
            # Extract attributes
            for attr in ["tvg-logo", "group-title"]:
                import re
                m = re.search(rf'{attr}="([^"]*)"', line)
                if m:
                    key = "logo" if attr == "tvg-logo" else "group"
                    current_info[key] = m.group(1)
        elif line and not line.startswith("#") and current_info:
            current_info["url"] = line
            imported.append(current_info)
            current_info = {}

    if not imported:
        return jsonify({"ok": False, "error": "No streams found in M3U"}), 400

    # Add to channels
    data = get_channels_data()
    existing_numbers = {ch["number"] for ch in data["channels"]}
    start_num = max(existing_numbers, default=0) + 1
    added = 0
    categories_seen = set(data["categories"])

    for i, entry in enumerate(imported):
        category = entry.get("group", "Uncategorized")
        if category not in categories_seen:
            data["categories"].append(category)
            categories_seen.add(category)
        new_ch = {
            "id":       next_channel_id(data["channels"]),
            "number":   start_num + i,
            "name":     entry["name"],
            "category": category,
            "url":      entry["url"],
            "logo":     entry.get("logo", ""),
            "enabled":  True,
            "notes":    "Imported from M3U",
            "added_at": datetime.now().isoformat(),
        }
        data["channels"].append(new_ch)
        added += 1

    save_json(CHANNELS_FILE, data)
    return jsonify({"ok": True, "imported": added, "total": len(data["channels"])})


# ── REST API: Categories ──────────────────────────────────────────────────────
@app.route("/api/categories", methods=["GET"])
def api_get_categories():
    data = get_channels_data()
    return jsonify(data["categories"])


@app.route("/api/categories", methods=["POST"])
def api_add_category():
    body = request.get_json()
    name = body.get("name", "").strip() if body else ""
    if not name:
        return jsonify({"ok": False, "error": "Name required"}), 400
    data = get_channels_data()
    if name not in data["categories"]:
        data["categories"].append(name)
        save_json(CHANNELS_FILE, data)
    return jsonify({"ok": True, "categories": data["categories"]})


# ── REST API: Config ──────────────────────────────────────────────────────────
@app.route("/api/config", methods=["GET"])
def api_get_config():
    return jsonify(get_config())


@app.route("/api/config", methods=["PUT"])
def api_update_config():
    body = request.get_json()
    if not body:
        return jsonify({"ok": False, "error": "No body"}), 400
    config = get_config()
    safe_keys = [
        "volume", "fullscreen", "buffer_seconds", "stream_retries",
        "startup_channel", "retry_delay_seconds", "video_output"
    ]
    for k in safe_keys:
        if k in body:
            config[k] = body[k]
    save_json(CONFIG_FILE, config)
    return jsonify({"ok": True, "config": config})


# ── REST API: Stream Test ─────────────────────────────────────────────────────
@app.route("/api/test_stream", methods=["POST"])
def api_test_stream():
    body = request.get_json()
    url  = body.get("url", "").strip() if body else ""
    if not url:
        return jsonify({"ok": False, "error": "URL required"}), 400
    try:
        result = subprocess.run(
            ["yt-dlp", "--simulate", "--quiet", url],
            capture_output=True, text=True, timeout=15
        )
        reachable = result.returncode == 0
    except Exception as e:
        reachable = False
    return jsonify({"ok": reachable, "url": url})


# ── WebSocket ─────────────────────────────────────────────────────────────────
@socketio.on("connect")
def ws_connect():
    emit("status", get_status())


@socketio.on("request_status")
def ws_request_status():
    emit("status", get_status())


# ── Static ────────────────────────────────────────────────────────────────────
@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory(BASE_DIR / "web" / "static", filename)


# ── Run ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)
    socketio.run(app, host=args.host, port=args.port, debug=args.debug, allow_unsafe_werkzeug=True)


# ── REST API: Updates ─────────────────────────────────────────────────────────
@app.route("/api/update/check", methods=["GET"])
def api_check_update():
    try:
        subprocess.run(
            ["git", "-C", str(BASE_DIR), "fetch"],
            capture_output=True, text=True, timeout=15
        )
        local = subprocess.run(
            ["git", "-C", str(BASE_DIR), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5
        ).stdout.strip()[:7]
        remote = subprocess.run(
            ["git", "-C", str(BASE_DIR), "rev-parse", "origin/main"],
            capture_output=True, text=True, timeout=5
        ).stdout.strip()[:7]
        up_to_date = (local == remote)
        return jsonify({
            "ok": True,
            "up_to_date": up_to_date,
            "local":  local,
            "remote": remote,
            "message": "Already up to date" if up_to_date else "Update available!"
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/update/apply", methods=["POST"])
def api_apply_update():
    try:
        pull = subprocess.run(
            ["git", "-C", str(BASE_DIR), "pull", "--force"],
            capture_output=True, text=True, timeout=60
        )
        if pull.returncode != 0:
            return jsonify({"ok": False, "error": pull.stderr.strip()}), 500
        output = pull.stdout.strip()
        venv_pip = BASE_DIR / "venv" / "bin" / "pip"
        req_file = BASE_DIR / "requirements.txt"
        if venv_pip.exists() and req_file.exists():
            subprocess.run(
                [str(venv_pip), "install", "-r", str(req_file), "-q"],
                capture_output=True, timeout=120
            )
        subprocess.Popen(
            ["sudo", "systemctl", "restart",
             "streamstation", "streamstation-web",
             "streamstation-display", "streamstation-keypad"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        return jsonify({
            "ok": True,
            "message": "Update applied — services restarting",
            "output": output
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

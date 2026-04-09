#!/usr/bin/env python3
"""
StreamStation - Main Channel Engine
Manages live stream playback via MPV and handles channel switching.
"""

import os
import sys
import json
import time
import signal
import socket
import logging
import argparse
import subprocess
import threading
from pathlib import Path
from datetime import datetime

# ── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR       = Path(__file__).parent
CHANNELS_FILE  = BASE_DIR / "streams" / "channels.json"
CONFIG_FILE    = BASE_DIR / "config" / "system.json"
RUNTIME_DIR    = BASE_DIR / "runtime"
STATUS_FILE    = RUNTIME_DIR / "current_channel.json"
CONTROL_SOCKET = RUNTIME_DIR / "control.socket"
LOG_FILE       = RUNTIME_DIR / "streamstation.log"
STATIC_DIR     = BASE_DIR / "web" / "static"
SIGNAL_VIDEO   = STATIC_DIR / "img" / "no_signal.mp4"

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("streamstation")


def load_json(path):
    with open(path, "r") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


class ChannelEngine:
    def __init__(self):
        self.config        = load_json(CONFIG_FILE)
        self.mpv_process   = None
        self.current_ch    = None
        self.channel_history = []
        self.retry_count   = 0
        self.max_retries   = self.config.get("stream_retries", 3)
        self.retry_delay   = self.config.get("retry_delay_seconds", 5)
        self._lock         = threading.Lock()
        self._running      = True
        RUNTIME_DIR.mkdir(exist_ok=True)
        self._write_status(None, "idle")

    # ── Channel Data ─────────────────────────────────────────────────────────
    def get_channels(self):
        data = load_json(CHANNELS_FILE)
        return sorted(
            [ch for ch in data["channels"] if ch.get("enabled", True)],
            key=lambda c: c["number"],
        )

    def get_channel_by_number(self, number):
        for ch in self.get_channels():
            if ch["number"] == number:
                return ch
        return None

    def get_adjacent_channel(self, direction):
        channels = self.get_channels()
        if not channels:
            return None
        numbers = [ch["number"] for ch in channels]
        if self.current_ch is None:
            return channels[0]["number"] if direction == 1 else channels[-1]["number"]
        try:
            idx = numbers.index(self.current_ch)
        except ValueError:
            return numbers[0]
        idx = (idx + direction) % len(numbers)
        return numbers[idx]

    # ── MPV Control ──────────────────────────────────────────────────────────
    def _build_mpv_cmd(self, url):
        cfg = self.config
        cmd = [
            "mpv",
            url,
            "--no-terminal",
            "--no-input-default-bindings",
            f"--volume={cfg.get('volume', 80)}",
            "--cache=yes",
            f"--cache-secs={cfg.get('buffer_seconds', 10)}",
            "--demuxer-max-bytes=50M",
            "--demuxer-readahead-secs=10",
            "--stream-lavf-o=reconnect=1",
            "--stream-lavf-o=reconnect_streamed=1",
            "--stream-lavf-o=reconnect_delay_max=5",
        ]
        if cfg.get("fullscreen", True):
            cmd.append("--fullscreen")
        if cfg.get("video_output"):
            cmd += [f"--vo={cfg['video_output']}"]
        return cmd

    def _kill_mpv(self):
        if self.mpv_process:
            try:
                self.mpv_process.terminate()
                self.mpv_process.wait(timeout=3)
            except Exception:
                try:
                    self.mpv_process.kill()
                except Exception:
                    pass
            self.mpv_process = None
            log.info("MPV stopped")

    def _resolve_url(self, url):
        """Use yt-dlp to resolve non-direct URLs (YouTube Live, Twitch, etc.)"""
        direct_prefixes = ("http", "rtmp", "rtsp", "udp", "rtp")
        likely_direct   = any(url.endswith(ext) for ext in (".m3u8", ".ts", ".mp4", ".mpd"))
        if likely_direct:
            return url
        try:
            result = subprocess.run(
                ["yt-dlp", "--get-url", "-f", "best[ext=mp4]/best", url],
                capture_output=True, text=True, timeout=20
            )
            resolved = result.stdout.strip().split("\n")[0]
            if resolved and resolved.startswith(direct_prefixes):
                log.info(f"Resolved URL via yt-dlp: {resolved[:80]}...")
                return resolved
        except Exception as e:
            log.warning(f"yt-dlp resolution failed ({e}), using raw URL")
        return url

    def _play_no_signal(self):
        """Show no-signal fallback."""
        self._kill_mpv()
        fallback_url = str(SIGNAL_VIDEO) if SIGNAL_VIDEO.exists() else "color://black"
        cmd = ["mpv", fallback_url, "--loop", "--no-terminal", "--no-osc"]
        if self.config.get("fullscreen", True):
            cmd.append("--fullscreen")
        try:
            self.mpv_process = subprocess.Popen(cmd)
        except Exception as e:
            log.error(f"Could not start fallback player: {e}")

    def _monitor_mpv(self, channel_number):
        """Background thread: watch for MPV crash and retry."""
        while self._running and self.current_ch == channel_number:
            if self.mpv_process and self.mpv_process.poll() is not None:
                log.warning(f"MPV exited unexpectedly on ch {channel_number}, retry {self.retry_count+1}/{self.max_retries}")
                self.retry_count += 1
                if self.retry_count <= self.max_retries:
                    time.sleep(self.retry_delay)
                    if self.current_ch == channel_number:
                        ch = self.get_channel_by_number(channel_number)
                        if ch:
                            self._launch_stream(ch, monitor=False)
                else:
                    log.error(f"Max retries reached for ch {channel_number}, showing no-signal")
                    self._write_status(channel_number, "no_signal")
                    self._play_no_signal()
                    break
            time.sleep(2)

    def _launch_stream(self, channel, monitor=True):
        self._kill_mpv()
        url = self._resolve_url(channel["url"])
        cmd = self._build_mpv_cmd(url)
        log.info(f"Launching stream: ch {channel['number']} — {channel['name']}")
        try:
            self.mpv_process = subprocess.Popen(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            self._write_status(channel["number"], "playing", channel)
            self.retry_count = 0
            if monitor:
                t = threading.Thread(
                    target=self._monitor_mpv,
                    args=(channel["number"],),
                    daemon=True,
                )
                t.start()
        except FileNotFoundError:
            log.error("MPV not found — is it installed?")
            self._write_status(channel["number"], "error")
        except Exception as e:
            log.error(f"Failed to launch MPV: {e}")
            self._write_status(channel["number"], "error")

    # ── Public API ───────────────────────────────────────────────────────────
    def tune(self, channel_number):
        with self._lock:
            ch = self.get_channel_by_number(channel_number)
            if not ch:
                log.warning(f"Channel {channel_number} not found")
                return False
            if self.current_ch is not None:
                self.channel_history.append(self.current_ch)
                self.channel_history = self.channel_history[-20:]
            self.current_ch = channel_number
            self._launch_stream(ch)
            return True

    def channel_up(self):
        next_ch = self.get_adjacent_channel(1)
        if next_ch is not None:
            return self.tune(next_ch)
        return False

    def channel_down(self):
        prev_ch = self.get_adjacent_channel(-1)
        if prev_ch is not None:
            return self.tune(prev_ch)
        return False

    def last_channel(self):
        if self.channel_history:
            last = self.channel_history.pop()
            return self.tune(last)
        return False

    def set_volume(self, level):
        level = max(0, min(100, level))
        self.config["volume"] = level
        save_json(CONFIG_FILE, self.config)
        # Send volume command via MPV's IPC if available
        log.info(f"Volume set to {level}")
        return level

    def stop(self):
        self._running = False
        self._kill_mpv()
        self._write_status(None, "stopped")
        if CONTROL_SOCKET.exists():
            CONTROL_SOCKET.unlink()
        log.info("StreamStation stopped")

    # ── Status ───────────────────────────────────────────────────────────────
    def _write_status(self, channel_number, state, channel_data=None):
        status = {
            "channel":    channel_number,
            "state":      state,
            "name":       channel_data["name"]     if channel_data else None,
            "category":   channel_data["category"] if channel_data else None,
            "logo":       channel_data.get("logo") if channel_data else None,
            "updated_at": datetime.now().isoformat(),
        }
        save_json(STATUS_FILE, status)

    def get_status(self):
        try:
            return load_json(STATUS_FILE)
        except Exception:
            return {"channel": None, "state": "unknown"}

    # ── Socket Server ─────────────────────────────────────────────────────────
    def run_socket_server(self):
        """Listen on UNIX socket for control commands from web/hardware."""
        if CONTROL_SOCKET.exists():
            CONTROL_SOCKET.unlink()
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(str(CONTROL_SOCKET))
        srv.listen(5)
        srv.settimeout(1.0)
        log.info(f"Control socket listening at {CONTROL_SOCKET}")
        while self._running:
            try:
                conn, _ = srv.accept()
            except socket.timeout:
                continue
            except Exception:
                break
            try:
                data = conn.recv(256).decode().strip()
                response = self._handle_command(data)
                conn.sendall((response + "\n").encode())
            except Exception as e:
                log.warning(f"Socket error: {e}")
            finally:
                conn.close()
        srv.close()

    def _handle_command(self, cmd):
        parts = cmd.split()
        if not parts:
            return "ERROR empty"
        action = parts[0].upper()
        if action == "TUNE" and len(parts) == 2:
            try:
                ok = self.tune(int(parts[1]))
                return "OK" if ok else "ERROR not_found"
            except ValueError:
                return "ERROR bad_number"
        elif action == "UP":
            return "OK" if self.channel_up() else "ERROR"
        elif action == "DOWN":
            return "OK" if self.channel_down() else "ERROR"
        elif action == "LAST":
            return "OK" if self.last_channel() else "ERROR"
        elif action == "STATUS":
            return json.dumps(self.get_status())
        elif action == "VOLUME" and len(parts) == 2:
            try:
                v = self.set_volume(int(parts[1]))
                return f"OK {v}"
            except ValueError:
                return "ERROR bad_volume"
        elif action == "STOP":
            self.stop()
            return "OK"
        else:
            return f"ERROR unknown_command:{cmd}"

    # ── Main Loop ─────────────────────────────────────────────────────────────
    def run(self):
        log.info("StreamStation engine starting...")
        channels = self.get_channels()
        if not channels:
            log.warning("No channels configured — add some via the web UI")
        else:
            start_ch = self.config.get("startup_channel", channels[0]["number"])
            self.tune(start_ch)

        def _shutdown(sig, frame):
            log.info("Shutdown signal received")
            self._running = False

        signal.signal(signal.SIGINT,  _shutdown)
        signal.signal(signal.SIGTERM, _shutdown)

        socket_thread = threading.Thread(target=self.run_socket_server, daemon=True)
        socket_thread.start()

        log.info("StreamStation running. Send commands via control socket.")
        while self._running:
            time.sleep(1)

        self.stop()


# ── CLI ───────────────────────────────────────────────────────────────────────
def send_command(cmd):
    """Send a command to a running engine via the control socket."""
    if not CONTROL_SOCKET.exists():
        print("ERROR: StreamStation is not running (socket not found)")
        sys.exit(1)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.connect(str(CONTROL_SOCKET))
        s.sendall((cmd + "\n").encode())
        resp = s.recv(4096).decode().strip()
        print(resp)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="StreamStation Channel Engine")
    parser.add_argument("--run",     action="store_true", help="Start the channel engine")
    parser.add_argument("--tune",    type=int,            help="Tune to channel number")
    parser.add_argument("--up",      action="store_true", help="Channel up")
    parser.add_argument("--down",    action="store_true", help="Channel down")
    parser.add_argument("--last",    action="store_true", help="Last channel")
    parser.add_argument("--status",  action="store_true", help="Print current status")
    parser.add_argument("--volume",  type=int,            help="Set volume 0-100")
    args = parser.parse_args()

    if args.run:
        engine = ChannelEngine()
        engine.run()
    elif args.tune:
        send_command(f"TUNE {args.tune}")
    elif args.up:
        send_command("UP")
    elif args.down:
        send_command("DOWN")
    elif args.last:
        send_command("LAST")
    elif args.status:
        send_command("STATUS")
    elif args.volume is not None:
        send_command(f"VOLUME {args.volume}")
    else:
        parser.print_help()

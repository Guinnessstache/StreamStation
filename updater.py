#!/usr/bin/env python3
"""
StreamStation Auto-Updater
Checks GitHub Releases for a newer version, downloads the zip, extracts it
in-place, and restarts the systemd service.

Flow:
  1. GET https://api.github.com/repos/Guinnessstache/StreamStation/releases/latest
  2. Compare tag_name (e.g. "v1.2.0") against local VERSION file
  3. If newer: download the release zip asset, extract to a staging dir,
     rsync-style copy new files over the install dir, restart service.
  4. Expose check/install results via simple callable API used by app.py.
"""

import json
import logging
import os
import re
import shutil
import subprocess
import threading
import time
import urllib.request
import zipfile
from pathlib import Path
from datetime import datetime

log = logging.getLogger("streamstation.updater")

# ── Config ────────────────────────────────────────────────────────────────────

GITHUB_REPO     = "Guinnessstache/StreamStation"
GITHUB_API_URL  = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
CHECK_INTERVAL  = 6 * 60 * 60   # check every 6 hours
INSTALL_DIR     = Path(__file__).parent
VERSION_FILE    = INSTALL_DIR / "VERSION"
STAGING_DIR     = INSTALL_DIR / "runtime" / "update_staging"
SERVICE_NAME    = "streamstation"  # systemctl service name

# Files/dirs never overwritten during an update (user data)
PRESERVE = {
    "streams/channels.json",
    "config/system.json",
    "runtime",
}


# ── Version helpers ───────────────────────────────────────────────────────────

def _parse_version(v: str) -> tuple:
    """Turn 'v1.2.0' or '1.2.0' into (1, 2, 0) for comparison."""
    v = v.strip().lstrip("v")
    parts = re.findall(r"\d+", v)
    return tuple(int(x) for x in parts[:3])


def read_local_version() -> str:
    try:
        return VERSION_FILE.read_text().strip()
    except Exception:
        return "0.0.0"


# ── State (shared between background thread and Flask routes) ─────────────────

_state = {
    "local_version":    read_local_version(),
    "latest_version":   None,
    "update_available": False,
    "release_notes":    None,
    "release_url":      None,
    "asset_url":        None,
    "asset_name":       None,
    "last_checked":     None,
    "checking":         False,
    "installing":       False,
    "install_status":   None,   # None | "ok" | "error"
    "install_message":  None,
    "error":            None,
}
_state_lock = threading.Lock()


def get_state() -> dict:
    with _state_lock:
        return dict(_state)


def _update_state(**kwargs):
    with _state_lock:
        _state.update(kwargs)


# ── GitHub check ─────────────────────────────────────────────────────────────

def check_for_update() -> dict:
    """
    Hit the GitHub API and compare versions.
    Returns the current state dict.
    Raises nothing — all errors are captured into state.
    """
    _update_state(checking=True, error=None)
    try:
        req = urllib.request.Request(
            GITHUB_API_URL,
            headers={
                "Accept":     "application/vnd.github+json",
                "User-Agent": f"StreamStation/{read_local_version()}",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())

        tag      = data.get("tag_name", "")
        notes    = data.get("body", "")
        html_url = data.get("html_url", "")
        assets   = data.get("assets", [])

        # Find the zip asset (prefer one named StreamStation_*.zip)
        asset_url  = None
        asset_name = None
        for a in assets:
            name = a.get("name", "")
            if name.endswith(".zip") and "StreamStation" in name:
                asset_url  = a["browser_download_url"]
                asset_name = name
                break
        # Fallback: any zip
        if not asset_url:
            for a in assets:
                if a.get("name", "").endswith(".zip"):
                    asset_url  = a["browser_download_url"]
                    asset_name = a["name"]
                    break

        local  = _parse_version(read_local_version())
        remote = _parse_version(tag)
        available = remote > local

        _update_state(
            latest_version   = tag,
            update_available = available,
            release_notes    = notes[:2000] if notes else None,
            release_url      = html_url,
            asset_url        = asset_url,
            asset_name       = asset_name,
            last_checked     = datetime.now().isoformat(),
            checking         = False,
            error            = None,
        )
        log.info(
            f"Update check: local={read_local_version()} "
            f"latest={tag} available={available}"
        )

    except Exception as e:
        _update_state(checking=False, error=str(e))
        log.warning(f"Update check failed: {e}")

    return get_state()


# ── Install ───────────────────────────────────────────────────────────────────

def _download(url: str, dest: Path, progress_cb=None):
    """Download url to dest, calling progress_cb(pct) periodically."""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": f"StreamStation/{read_local_version()}"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        total = int(resp.headers.get("Content-Length", 0))
        done  = 0
        with open(dest, "wb") as f:
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if progress_cb and total:
                    progress_cb(int(done * 100 / total))


def _safe_copy_tree(src: Path, dst: Path):
    """
    Copy files from src into dst, skipping anything in PRESERVE.
    New files are added; existing files are overwritten; user data is untouched.
    """
    for item in src.rglob("*"):
        if not item.is_file():
            continue
        rel = item.relative_to(src)
        rel_str = str(rel)

        # Skip preserved paths
        skip = False
        for p in PRESERVE:
            if rel_str == p or rel_str.startswith(p + os.sep):
                skip = True
                break
        if skip:
            log.debug(f"Preserving: {rel_str}")
            continue

        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target)
        log.debug(f"Updated: {rel_str}")


def install_update(progress_cb=None) -> bool:
    """
    Download and install the latest release.
    Returns True on success, False on failure.
    progress_cb(message: str) is called with status strings during install.
    """
    state = get_state()
    if not state["asset_url"]:
        _update_state(
            install_status="error",
            install_message="No release asset found — install manually from GitHub.",
            installing=False,
        )
        return False

    _update_state(installing=True, install_status=None, install_message=None)

    def emit(msg):
        log.info(f"Updater: {msg}")
        if progress_cb:
            progress_cb(msg)

    try:
        # ── 1. Prepare staging dir ──────────────────────────────────────────
        if STAGING_DIR.exists():
            shutil.rmtree(STAGING_DIR)
        STAGING_DIR.mkdir(parents=True)
        zip_path = STAGING_DIR / (state["asset_name"] or "update.zip")

        # ── 2. Download ─────────────────────────────────────────────────────
        emit(f"Downloading {state['asset_name']} …")
        _download(state["asset_url"], zip_path)
        emit(f"Download complete ({zip_path.stat().st_size // 1024} KB)")

        # ── 3. Extract ──────────────────────────────────────────────────────
        extract_dir = STAGING_DIR / "extracted"
        extract_dir.mkdir()
        emit("Extracting…")
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(extract_dir)

        # The zip may have a top-level folder (e.g. StreamStation_v1_2/)
        # Find the directory that contains streamstation.py
        src_root = None
        for candidate in [extract_dir] + list(extract_dir.iterdir()):
            if candidate.is_dir() and (candidate / "streamstation.py").exists():
                src_root = candidate
                break
        if src_root is None:
            raise FileNotFoundError("Could not find streamstation.py in release zip")

        emit(f"Installing from {src_root.name} …")

        # ── 4. Copy new files over install dir ──────────────────────────────
        _safe_copy_tree(src_root, INSTALL_DIR)

        # ── 5. Update VERSION file ───────────────────────────────────────────
        new_version = state["latest_version"].lstrip("v")
        VERSION_FILE.write_text(new_version + "\n")
        emit(f"Version updated to {new_version}")

        # ── 6. Cleanup staging ───────────────────────────────────────────────
        shutil.rmtree(STAGING_DIR, ignore_errors=True)

        # ── 7. Restart service ───────────────────────────────────────────────
        emit("Restarting StreamStation service…")
        try:
            subprocess.run(
                ["sudo", "systemctl", "restart", SERVICE_NAME],
                timeout=15,
                check=True,
            )
            emit("Service restarted successfully.")
        except Exception as e:
            emit(f"Service restart failed ({e}) — restart manually with: sudo systemctl restart {SERVICE_NAME}")

        _update_state(
            local_version    = new_version,
            update_available = False,
            installing       = False,
            install_status   = "ok",
            install_message  = f"Updated to {new_version} successfully.",
        )
        return True

    except Exception as e:
        log.error(f"Update install failed: {e}")
        shutil.rmtree(STAGING_DIR, ignore_errors=True)
        _update_state(
            installing      = False,
            install_status  = "error",
            install_message = str(e),
        )
        return False


# ── Background checker ────────────────────────────────────────────────────────

def _background_check_loop():
    """Runs in a daemon thread. Checks for updates on startup and every 6 hours."""
    time.sleep(30)   # let the engine settle before first check
    while True:
        check_for_update()
        time.sleep(CHECK_INTERVAL)


def start_background_checker():
    t = threading.Thread(target=_background_check_loop, daemon=True, name="updater")
    t.start()
    log.info("Auto-updater background checker started (interval: 6h)")

"""Phase 4 - read the result (screenshots, optional OCR).

Feedback from the PCW core is visual only. shot() triggers a screenshot,
finds the newest one for the running core, and saves the PNG locally.
read_screen() runs tesseract if available (optional; degrades to None).
"""

import os
import shutil
import subprocess
import time

import requests

import config
import device


def _list_shots():
    """GET /api/screenshots -> normalised list of dicts.

    The API shape varies by version; accept either a bare list or an object
    wrapping a 'screenshots' list, and keep whatever fields are present.
    """
    data = device._get("/api/screenshots").json()
    if isinstance(data, dict):
        data = data.get("screenshots") or data.get("data") or []
    return [s for s in data if isinstance(s, dict)]


def _sort_key(s):
    """Best-effort 'newest' ordering: prefer a timestamp, fall back to name."""
    for k in ("modified", "timestamp", "time", "date"):
        if k in s:
            return str(s[k])
    return str(s.get("filename") or s.get("path") or "")


def shot(save_dir=config.SHOTS_DIR, wait=config.SHOT_WAIT):
    """Take a screenshot and save the newest PNG for the running core.

    Returns the local file path, or None if no screenshot could be found.
    """
    os.makedirs(save_dir, exist_ok=True)
    device._post("/api/screenshots")          # trigger capture
    time.sleep(wait)

    shots = _list_shots()
    if not shots:
        return None

    # Prefer screenshots whose core looks like the PCW; else take the newest.
    pcw = [s for s in shots
           if "pcw" in str(s.get("core", "")).lower()
           or "pcw" in str(s.get("game", "")).lower()]
    pool = pcw or shots
    newest = sorted(pool, key=_sort_key)[-1]

    core = newest.get("core") or newest.get("game") or ""
    fname = newest.get("filename") or os.path.basename(newest.get("path", ""))
    if not fname:
        return None

    r = requests.get(f"{config.BASE}/api/screenshots/{core}/{fname}", timeout=20)
    r.raise_for_status()
    local = os.path.join(save_dir, fname)
    with open(local, "wb") as f:
        f.write(r.content)
    return local


def read_screen(png_path):
    """OCR a screenshot to text using tesseract, or None if unavailable."""
    if not png_path or not os.path.exists(png_path):
        return None
    tess = shutil.which("tesseract")
    if not tess:
        return None
    cp = subprocess.run([tess, png_path, "stdout"],
                        capture_output=True, text=True)
    if cp.returncode != 0:
        return None
    return cp.stdout.strip()

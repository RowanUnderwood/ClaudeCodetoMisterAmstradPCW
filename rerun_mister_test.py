#!/usr/bin/env python3
"""Rerun the MiSTer Amstrad PCW boot test.

Two steps, mirroring the manual test:
  1. Write a .mgl over SSH (plink) that points the Amstrad-PCW core at the
     boot disk. Launching only mounts the disk read-only; it never writes to it.
  2. POST to the MiSTer remote API to launch that .mgl.
"""

import json
import shutil
import subprocess
import sys
import urllib.request

# --- Config ----------------------------------------------------------------
HOST = "192.168.2.56"
SSH_USER = "root"
SSH_PASS = "1"
API_PORT = 8182

MGL_PATH = "/media/fat/games/Amstrad PCW/DEV.mgl"
MGL_CONTENT = """\
<mistergamedescription>
    <rbf>_Computer/Amstrad-PCW</rbf>
    <file delay="1" type="s" index="0" path="games/Amstrad PCW/cpm 2,11 boot PCW9512+ eng.dsk"/>
</mistergamedescription>
"""
# ---------------------------------------------------------------------------


def find_plink():
    """Locate plink.exe (PuTTY) on PATH or in the default install dir."""
    plink = shutil.which("plink")
    if plink:
        return plink
    fallback = r"C:\Program Files\PuTTY\plink.exe"
    if shutil.os.path.exists(fallback):
        return fallback
    sys.exit("ERROR: plink not found. Install PuTTY or add plink to PATH.")


def run_plink(remote_cmd):
    """Run a command on the MiSTer over SSH via plink, returning stdout."""
    plink = find_plink()
    result = subprocess.run(
        [plink, "-ssh", "-pw", SSH_PASS, "-batch",
         f"{SSH_USER}@{HOST}", remote_cmd],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        sys.exit(f"ERROR: SSH command failed (exit {result.returncode}):\n"
                 f"{result.stderr.strip()}")
    return result.stdout


def write_mgl():
    """Write the .mgl on the MiSTer using a heredoc, then read it back."""
    print(f"Writing {MGL_PATH} ...")
    heredoc = f'cat > "{MGL_PATH}" << "EOF"\n{MGL_CONTENT}EOF'
    run_plink(heredoc)

    print("Verifying contents ...")
    written = run_plink(f'cat "{MGL_PATH}"')
    if written.strip() != MGL_CONTENT.strip():
        sys.exit("ERROR: .mgl on device does not match expected content:\n"
                 + written)
    print("OK: .mgl written and verified.")


def launch():
    """POST the .mgl path to the MiSTer remote launch API."""
    url = f"http://{HOST}:{API_PORT}/api/launch"
    payload = json.dumps({"path": MGL_PATH}).encode()
    print(f"Launching via {url} ...")
    req = urllib.request.Request(
        url, data=payload, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode().strip()
            print(f"OK: launch returned HTTP {resp.status}"
                  + (f" — {body}" if body else " (empty body = success)."))
    except urllib.error.URLError as e:
        sys.exit(f"ERROR: launch request failed: {e}")


def main():
    write_mgl()
    launch()
    print("Done. MiSTer should be booting the Amstrad-PCW core.")


if __name__ == "__main__":
    main()

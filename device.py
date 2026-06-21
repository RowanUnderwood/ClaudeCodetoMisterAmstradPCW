"""Phase 2 - the .mgl, file transfer, and launch.

Transport uses PuTTY's plink/pscp (password auth works where OpenSSH's did
not on this machine). The Remote (mrext) HTTP API handles launch/menu/status.
"""

import json
import os
import shutil
import subprocess
import sys
import time

import requests

import config

MGL_XML = f"""\
<mistergamedescription>
    <rbf>{config.RBF}</rbf>
    <file delay="5" type="s" index="0" path="{config.WORK_REL}"/>
</mistergamedescription>
"""


# --- PuTTY transport -------------------------------------------------------
def _putty(name):
    """Locate a PuTTY tool (plink/pscp) on PATH or in the default dir."""
    found = shutil.which(name)
    if found:
        return found
    fallback = rf"C:\Program Files\PuTTY\{name}.exe"
    if os.path.exists(fallback):
        return fallback
    sys.exit(f"ERROR: '{name}' not found. Install PuTTY or add it to PATH.")


def ssh(remote_cmd):
    """Run a command on the MiSTer over SSH; return stdout (exit on failure)."""
    plink = _putty("plink")
    cp = subprocess.run(
        [plink, "-ssh", "-pw", config.SSH_PASS, "-batch",
         f"{config.SSH_USER}@{config.HOST}", remote_cmd],
        capture_output=True, text=True,
    )
    if cp.returncode != 0:
        sys.exit(f"ERROR: SSH failed (exit {cp.returncode}): {cp.stderr.strip()}")
    return cp.stdout


def _remote_spec(remote):
    """user@host:"/path" - double quotes survive to the remote shell so that
    spaces, the comma, and '+' in the path are preserved."""
    return f'{config.SSH_USER}@{config.HOST}:"{remote}"'


def upload(local, remote):
    """scp a local file to the device (quotes the spaced/'+' remote path)."""
    pscp = _putty("pscp")
    cp = subprocess.run(
        [pscp, "-scp", "-pw", config.SSH_PASS, "-batch", local,
         _remote_spec(remote)],
        capture_output=True, text=True,
    )
    if cp.returncode != 0:
        sys.exit(f"ERROR: upload failed (exit {cp.returncode}): {cp.stderr.strip()}")


def download(remote, local):
    """scp a file off the device to the dev machine (used for backups)."""
    pscp = _putty("pscp")
    cp = subprocess.run(
        [pscp, "-scp", "-pw", config.SSH_PASS, "-batch",
         _remote_spec(remote), local],
        capture_output=True, text=True,
    )
    if cp.returncode != 0:
        sys.exit(f"ERROR: download failed (exit {cp.returncode}): {cp.stderr.strip()}")


def backup_master(local=config.LOCAL_MASTER):
    """Phase 0 #6 - copy the master boot .dsk off-device (read-only safety)."""
    download(config.MASTER, local)
    return local


def write_mgl():
    """Write the static DEV.mgl on the device via a heredoc (Phase 2)."""
    heredoc = f'cat > "{config.MGL}" << "EOF"\n{MGL_XML}EOF'
    ssh(heredoc)
    back = ssh(f'cat "{config.MGL}"')
    if config.RBF not in back or config.WORK_REL not in back:
        sys.exit("ERROR: DEV.mgl on device does not match expected content:\n" + back)
    return back


# --- Remote HTTP API -------------------------------------------------------
def _post(path, payload=None):
    url = f"{config.BASE}{path}"
    r = requests.post(url, json=payload, timeout=15)
    r.raise_for_status()
    return r


def _get(path):
    url = f"{config.BASE}{path}"
    r = requests.get(url, timeout=15)
    r.raise_for_status()
    return r


def sysinfo():
    """Phase 0 #1 - reachability check; returns parsed JSON."""
    return _get("/api/sysinfo").json()


def playing():
    """GET /api/games/playing -> dict describing the running core/game."""
    try:
        return _get("/api/games/playing").json()
    except Exception:
        return {}


def to_menu():
    """POST /api/launch/menu - exit the current core to the MiSTer menu."""
    _post("/api/launch/menu")


def boot_mgl():
    """POST /api/launch {path: DEV.mgl} - cold boot the PCW core."""
    _post("/api/launch", {"path": config.MGL})


def cold_boot(menu_pause=2):
    """Bounce to menu then launch the .mgl, forcing a clean cold boot."""
    to_menu()
    time.sleep(menu_pause)
    boot_mgl()


def _is_pcw(info):
    blob = json.dumps(info).lower()
    return "amstradpcw" in blob or "amstrad-pcw" in blob or "pcw" in blob


def wait_until_running(timeout=30, settle=config.SETTLE):
    """Poll /api/games/playing until the PCW core appears, then settle."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _is_pcw(playing()):
            time.sleep(settle)
            return True
        time.sleep(1)
    # Core may still be up even if the field is empty; settle and continue.
    time.sleep(settle)
    return False

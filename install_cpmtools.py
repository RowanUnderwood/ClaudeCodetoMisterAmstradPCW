#!/usr/bin/env python3
"""Install a libdsk-enabled cpmtools for this project (Windows / native).

Companion to diskimg.py. The boot image is a CPCEMU .DSK container, so cpmtools
MUST be built WITH libdsk (so `-T dsk` works). No prebuilt native-Windows build
ships libdsk (the "Wild Turkey" cpmtoolsWin32.zip does not), and Homebrew only
runs on macOS/Linux -- so on this machine we compile from source inside MSYS2.

What this does:
  1. Find MSYS2 (or install it via winget).
  2. Run build_cpmtools.sh through MSYS2's bash: it pacman-installs a toolchain,
     downloads + builds libdsk and cpmtools (--with-libdsk), and stages a
     self-contained copy into <project>\\cpmtools\\bin (exes + DLLs + diskdefs).
  3. Point the project at it: persist CPMTOOLS_DIR (setx) -- diskimg.py reads it.
  4. Verify end to end by auto-detecting the master image's CP/M format.

Usage:
    python install_cpmtools.py            # full install + verify
    python install_cpmtools.py --check    # only verify an existing staged build
    python install_cpmtools.py --no-winget   # fail (don't auto-install) if no MSYS2

After it prints the detected format, pin it into config.CPM_FORMAT.
"""

import argparse
import os
import subprocess
import sys

import config

HERE = config.HERE
STAGE_ROOT = os.path.join(HERE, "cpmtools")
STAGE_BIN = os.path.join(STAGE_ROOT, "bin")
BUILD_SCRIPT = os.path.join(HERE, "build_cpmtools.sh")

# Versions kept in sync with build_cpmtools.sh defaults; override via env.
LIBDSK_VER = os.environ.get("LIBDSK_VER", "1.5.22")
CPMTOOLS_VER = os.environ.get("CPMTOOLS_VER", "2.23")

# Common MSYS2 install locations to probe before resorting to winget.
MSYS2_CANDIDATES = [
    r"C:\msys64",
    r"C:\tools\msys64",
    os.path.join(os.environ.get("USERPROFILE", ""), "msys64"),
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "msys64"),
]


def _msys_path(win_path):
    """Convert a Windows path to an MSYS2 path: Z:\\a\\b -> /z/a/b."""
    win_path = os.path.abspath(win_path)
    drive, rest = os.path.splitdrive(win_path)
    return "/" + drive[0].lower() + rest.replace("\\", "/")


def find_msys2_bash():
    """Return the path to MSYS2's bash.exe, or '' if MSYS2 isn't installed."""
    for root in MSYS2_CANDIDATES:
        if not root:
            continue
        bash = os.path.join(root, "usr", "bin", "bash.exe")
        if os.path.exists(bash):
            return bash
    return ""


def install_msys2():
    """Install MSYS2 via winget. Returns the bash path or exits."""
    if not _which("winget"):
        sys.exit(
            "ERROR: MSYS2 not found and winget is unavailable to install it.\n"
            "       Install MSYS2 from https://www.msys2.org/ then re-run, or\n"
            "       run with an existing MSYS2 at one of:\n         "
            + "\n         ".join(c for c in MSYS2_CANDIDATES if c)
        )
    print(">> Installing MSYS2 via winget (this downloads ~100 MB)...")
    subprocess.run(
        ["winget", "install", "-e", "--id", "MSYS2.MSYS2",
         "--accept-source-agreements", "--accept-package-agreements"],
        check=False,
    )
    bash = find_msys2_bash()
    if not bash:
        sys.exit(
            "ERROR: winget finished but MSYS2's bash.exe was not found at the\n"
            "       expected locations. If it installed elsewhere, add that path\n"
            "       to MSYS2_CANDIDATES in this script and re-run."
        )
    return bash


def _which(name):
    from shutil import which
    return which(name)


def run_build(bash):
    """Drive build_cpmtools.sh through MSYS2 bash with the right environment."""
    if not os.path.exists(BUILD_SCRIPT):
        sys.exit(f"ERROR: missing build script: {BUILD_SCRIPT}")
    os.makedirs(STAGE_BIN, exist_ok=True)

    env = dict(os.environ)
    env["MSYSTEM"] = "MSYS"          # MSYS subsystem toolchain (relocatable root)
    env["CHERE_INVOKING"] = "1"      # don't cd to $HOME on login
    env["STAGE_BIN"] = _msys_path(STAGE_BIN)
    env["STAGE_ROOT"] = _msys_path(STAGE_ROOT)
    env["LIBDSK_VER"] = LIBDSK_VER
    env["CPMTOOLS_VER"] = CPMTOOLS_VER

    # -l: login shell so pacman/gcc are on PATH. The script path can contain
    # spaces, so quote it inside the -c string.
    cmd = [bash, "-lc", 'exec bash "%s"' % _msys_path(BUILD_SCRIPT)]
    print(">> Building libdsk + cpmtools inside MSYS2 (several minutes)...")
    cp = subprocess.run(cmd, env=env)
    if cp.returncode != 0:
        sys.exit(f"ERROR: build failed (exit {cp.returncode}). See output above.")


def persist_cpmtools_dir():
    """Persist CPMTOOLS_DIR for future shells, and set it for this process."""
    os.environ["CPMTOOLS_DIR"] = STAGE_BIN
    # setx writes to the user environment (future processes only).
    subprocess.run(["setx", "CPMTOOLS_DIR", STAGE_BIN],
                   stdout=subprocess.DEVNULL, check=False)


def verify():
    """Import diskimg against the staged tools and auto-detect the disk format."""
    os.environ["CPMTOOLS_DIR"] = STAGE_BIN  # diskimg reads this at import time
    cpmls = os.path.join(STAGE_BIN, "cpmls.exe")
    if not os.path.exists(cpmls):
        sys.exit(f"ERROR: {cpmls} not present -- build did not produce cpmls.")

    import importlib
    import diskimg
    importlib.reload(diskimg)  # pick up CPMTOOLS_DIR if it was imported earlier

    print(">> Verifying tools resolve...")
    print("   cpmls:", diskimg._tool("cpmls"))
    print("   cpmcp:", diskimg._tool("cpmcp"))

    master = config.LOCAL_MASTER
    if not os.path.exists(master):
        print(f"!! {master} not found -- skipping format auto-detect.")
        print("   (Run device.backup_master() first, then re-run --check.)")
        return None

    print(f">> Auto-detecting CP/M format against {os.path.basename(master)} ...")
    try:
        fmt = diskimg.detect_format(master)
    except Exception as exc:  # noqa: BLE001 -- surface whatever cpmtools said
        sys.exit(
            "ERROR: tools built but format auto-detect failed:\n"
            f"  {exc}\n"
            "  This usually means libdsk (-T dsk) or diskdefs isn't wired up.\n"
            "  Inspect: "
            f'"{cpmls}" -f pcw -T dsk "{master}"'
        )
    print(f"\n   DETECTED FORMAT: {fmt}")
    print("   -> pin it in config.py:  CPM_FORMAT = %r" % fmt)
    return fmt


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true",
                    help="only verify an existing staged build; don't (re)build")
    ap.add_argument("--no-winget", action="store_true",
                    help="don't auto-install MSYS2; fail if it's missing")
    args = ap.parse_args()

    if args.check:
        verify()
        return

    bash = find_msys2_bash()
    if not bash:
        if args.no_winget:
            sys.exit("ERROR: MSYS2 not found and --no-winget given.")
        bash = install_msys2()
    print(f">> Using MSYS2 bash: {bash}")

    run_build(bash)
    persist_cpmtools_dir()
    fmt = verify()

    print("\n" + "=" * 60)
    print("cpmtools is installed and wired up.")
    print(f"  CPMTOOLS_DIR = {STAGE_BIN}  (persisted via setx)")
    if fmt:
        print(f"  Next: set config.CPM_FORMAT = {fmt!r}, then: python pcwdev.py run <prog>.bas")
    print("  Open a NEW shell for CPMTOOLS_DIR to take effect everywhere.")
    print("=" * 60)


if __name__ == "__main__":
    main()

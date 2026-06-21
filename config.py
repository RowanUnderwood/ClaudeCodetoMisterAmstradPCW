"""Shared configuration for the MiSTer Amstrad PCW dev loop.

Edit values here; every other module imports from this file. See
mister-pcw-basic-plan.md for the rationale behind each constant.
"""

import os

# --- Device / network ------------------------------------------------------
HOST = "192.168.2.56"
SSH_USER = "root"
SSH_PASS = "1"                      # stock MiSTer; change if yours differs
API_PORT = 8182
# Root URL WITHOUT /api; helpers and callers add the /api/... path themselves.
BASE = f"http://{HOST}:{API_PORT}"

# --- Paths on the MiSTer SD card (note spaces, comma, and '+') -------------
GAMES = "/media/fat/games/Amstrad PCW"
MASTER = f"{GAMES}/cpm 2,11 boot PCW9512+ eng.dsk"   # read-only master
WORK = f"{GAMES}/DEV_work.dsk"                        # regenerated each run
MGL = f"{GAMES}/DEV.mgl"                              # static launcher
RBF = "_Computer/Amstrad-PCW"                         # hyphen, not space

# .mgl <file path=...> is relative to the .mgl's OWN folder (the games/Amstrad
# PCW dir), NOT /media/fat. Confirmed: a bare filename mounts; a full path does
# not. Keep this a bare filename.
WORK_REL = "DEV_work.dsk"

# --- Local files on the dev machine ----------------------------------------
HERE = os.path.dirname(os.path.abspath(__file__))
LOCAL_MASTER = os.path.join(HERE, "master_backup.dsk")   # off-device backup
LOCAL_WORK = os.path.join(HERE, "DEV_work.dsk")          # built locally, then scp'd
SHOTS_DIR = os.path.join(HERE, "screenshots")

# --- CP/M filenames (8.3, uppercase) ---------------------------------------
PROG_NAME = "PROG.BAS"
PROFILE_NAME = "PROFILE.SUB"
# Mallard BASIC loads AND runs the named program. Qualify with A: because
# PROFILE.SUB's `setdef m:,*` makes M: (the RAM disk) the default drive, where
# PROG.BAS doesn't exist -> an unqualified `BASIC PROG` would start BASIC empty.
RUN_LINE = "BASIC A:PROG"

# --- cpmtools disk format --------------------------------------------------
# The boot image is a CPCEMU .DSK container -> cpmtools must use libdsk
# (-T dsk). The filesystem format (-f) is unconfirmed; detect_format() in
# diskimg.py tries these candidates against the master until one lists files.
CPM_TYPE = "dsk"                    # libdsk container type
# Pinned after install_cpmtools.py auto-detected it against the master:
# the boot disk is 720K (80 cyl x 2 heads x 9 x 512). cf2dd = Amstrad 3"
# double-density (libdsk:format pcw720, blocksize 2048, maxdir 256, boottrk 1).
CPM_FORMAT = "cf2dd"                # None => auto-detect via candidates below
CPM_FORMAT_CANDIDATES = [
    "cf2dd",                        # <- the one that reads this master
    "pcw", "pcw180", "pcw720", "amstrad-pcw", "pcw9512",
    "cpcdata", "cpcsys", "ampro",
]

# --- Disk space limits -----------------------------------------------------
# The boot disk is 720K but mostly full of CP/M + Mallard system files. Free
# space on A: is small: CP/M's `SHOW A:` reports ~84K; cpmtools' fsck.cpm reports
# 43/357 free blocks * 2048 = ~86K (and 174/256 free directory entries). An
# injected PROG.BAS must fit there -- we delete the previous PROG.BAS first, so
# it's a replace-in-place. MAX_PROG_BYTES caps the source below measured free
# space, leaving room for the PROFILE.SUB rewrite and directory slack.
# diskimg.free_space() measures the live figure; this is the static guard.
# NOTE: Mallard BASIC's own workspace (~31K, the "free bytes" at its banner) is
# a TIGHTER limit for a *runnable* program than disk space is.
CPM_BLOCK_SIZE = 2048          # cf2dd allocation block size (free-space math)
MAX_PROG_BYTES = 80 * 1024     # reject .bas sources larger than this (~84K free)

# --- Timing ----------------------------------------------------------------
# Cold boot + the master's verbose PROFILE.SUB (setdef echo + pip copies to M:)
# + Mallard BASIC start takes ~35-40s before the program's output is on screen.
# (Well under MiSTer SAM's idle-attract timeout, so capturing here is safe.)
SETTLE = 40        # seconds to wait after boot for PROFILE.SUB + BASIC A:PROG
SHOT_WAIT = 4      # seconds between POST /api/screenshots and listing it
                   # (a fresh capture isn't always written within 2s)

# --- z88dk / .COM cross-compilation ----------------------------------------
# A second artifact kind: C/asm -> Z80 .COM, native machine code that loads at
# 0x0100 and runs directly (much faster than Mallard; ceiling is the ~61K TPA,
# not Mallard's ~31K workspace). The .COM is injected BINARY via diskimg.put_file
# (never put_text -- LF->CRLF would corrupt machine code) and run as "A:PROG".
#
# Staged to a SPACE-FREE path: z88dk is fragile with spaces in its install /
# ZCCCFG path, and this project lives under a path full of spaces. Z88DK_DIR and
# ZCCCFG are persisted by install_z88dk.py (via setx) and read here; ccom.py
# injects {Z88DK_DIR}\bin + ZCCCFG into the subprocess env (it never relies on a
# global PATH), mirroring how diskimg pins cwd=CPMTOOLS_DIR.
Z88DK_DIR = os.environ.get("Z88DK_DIR", r"C:\z88dk")   # staged toolchain root
ZCCCFG = os.environ.get("ZCCCFG", os.path.join(Z88DK_DIR, "lib", "config"))
# Official GitHub release zip (prebuilt win32). The nightly host
# (nightly.z88dk.org) is often unreachable, so default to the stable release;
# override with install_z88dk.py --url for a newer build.
Z88DK_URL = "https://github.com/z88dk/z88dk/releases/download/v2.4/z88dk-win32-2.4.zip"

ZCC_TARGET = "+cpm"
# Use the GENERIC CP/M subtype ("default" => -Cz.com): a portable .COM that does
# console I/O through the BDOS, which the PCW's CP/M Plus serves. The "pcw80"
# subtype instead builds a PCW-native *disk image* (+cpmdisk) with the heavy
# -lpcw banked runtime (REGISTER_SP=61000) -- that is NOT a drop-on-an-existing-
# disk .COM and crashes when injected + run as A:PROG. Generic = correct here.
ZCC_SUBTYPE = "default"        # plain .COM via BDOS (not the pcw80 disk build)
ZCC_COMPILER = "sccz80"        # robust default; "sdcc" (zsdcc) = smaller/faster
ZCC_FLAGS = ["-create-app"]    # appmake emits the .COM (add "-lm" only for floats)

COM_NAME = "PROG.COM"          # fixed injected name -> stable PROFILE.SUB
COM_RUN_CMD = "A:PROG"         # drive-qualified (default drive is M: via setdef)
COM_TPA_BYTES = 61 * 1024      # runtime size ceiling (CP/M Plus TPA on the PCW)

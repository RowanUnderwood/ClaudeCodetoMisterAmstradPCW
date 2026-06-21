"""Phase 1 - disk tooling.

Wraps cpmtools (built with libdsk) to inject Mallard BASIC programs into a
COPY of the CP/M boot disk. The master image is never modified here; callers
operate on a working copy produced by make_working_copy().

Requires cpmtools on PATH: cpmcp, cpmls (and libdsk so -T dsk works).
On Windows these are not bundled; install a cpmtools build with libdsk and
ensure the executables are reachable, or set CPMTOOLS_DIR below.
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile

import config

# Optional explicit location for cpmtools binaries (else rely on PATH).
CPMTOOLS_DIR = os.environ.get("CPMTOOLS_DIR", "")


def _tool(name):
    """Resolve a cpmtools executable, or exit with install guidance."""
    if CPMTOOLS_DIR:
        cand = os.path.join(CPMTOOLS_DIR, name)
        for c in (cand, cand + ".exe"):
            if os.path.exists(c):
                return c
    found = shutil.which(name)
    if found:
        return found
    sys.exit(
        f"ERROR: '{name}' not found. Install cpmtools built WITH libdsk and put it\n"
        f"       on PATH (or set CPMTOOLS_DIR). Verify with: {name} -h\n"
        f"       (libdsk is required so the CPCEMU .DSK container can be read.)"
    )


def _run(args):
    """Run a cpmtools command; return CompletedProcess (text captured).

    cwd is pinned to CPMTOOLS_DIR when set: cpmtools looks for its `diskdefs`
    format database in the current directory first, and install_cpmtools.py
    stages a `diskdefs` copy alongside the staged exes. This makes the format
    lookup work no matter where the caller runs from (the relocated MSYS exe's
    compiled-in diskdefs path doesn't resolve when launched from Windows). All
    image paths we pass are absolute, so cwd is otherwise irrelevant.
    """
    return subprocess.run(args, capture_output=True, text=True,
                          cwd=CPMTOOLS_DIR or None)


def _check(args, what):
    cp = _run(args)
    if cp.returncode != 0:
        raise RuntimeError(
            f"{what} failed (exit {cp.returncode}):\n"
            f"  cmd: {' '.join(args)}\n"
            f"  err: {cp.stderr.strip() or cp.stdout.strip()}"
        )
    return cp.stdout


def _fmt(fmt):
    """Resolve the cpmtools -f format, auto-detecting if unset."""
    fmt = fmt or config.CPM_FORMAT
    if fmt:
        return fmt
    raise RuntimeError(
        "No CP/M format set. Run detect_format(master) first and pin the "
        "result in config.CPM_FORMAT (or pass fmt=...)."
    )


def make_working_copy(master=config.LOCAL_MASTER, work=config.LOCAL_WORK):
    """Copy the master .dsk to a fresh working image. Never writes the master."""
    if not os.path.exists(master):
        sys.exit(f"ERROR: master image not found: {master}\n"
                 "       Back it up off-device first (device.backup_master()).")
    shutil.copyfile(master, work)
    return work


def detect_format(image, candidates=None):
    """Try cpmls with each candidate -f until one cleanly lists files.

    Returns the first format whose listing mentions a known boot file, else
    raises. Implements Phase 0 #7.
    """
    cpmls = _tool("cpmls")
    markers = ("BASIC", "PROFILE", "J14CPM3", "SUBMIT", "EMS", "COM")
    tried = []
    for fmt in (candidates or config.CPM_FORMAT_CANDIDATES):
        cp = _run([cpmls, "-f", fmt, "-T", config.CPM_TYPE, image])
        out = cp.stdout.upper()
        tried.append(f"{fmt}: rc={cp.returncode}")
        if cp.returncode == 0 and any(m in out for m in markers):
            return fmt
    raise RuntimeError(
        "Could not auto-detect a CP/M format. Tried:\n  "
        + "\n  ".join(tried)
        + "\nInspect the .DSK header geometry and add a diskdefs entry, then "
          "pin config.CPM_FORMAT."
    )


def list_dir(work, fmt=None):
    """Return a directory listing of the image (post-write sanity check)."""
    cpmls = _tool("cpmls")
    return _check([cpmls, "-f", _fmt(fmt), "-T", config.CPM_TYPE, work],
                  "cpmls")


def free_space(image, fmt=None):
    """Free space on the image as (bytes, blocks), via fsck.cpm's block report.

    fsck.cpm (-n = read-only) prints e.g.
        image: 82/256 files (...), 314/357 blocks
    so free blocks = total - used, times config.CPM_BLOCK_SIZE for bytes.
    """
    fmt = _fmt(fmt)
    fsck = _tool("fsck.cpm")
    cp = _run([fsck, "-f", fmt, "-n", image])
    out = (cp.stdout or "") + (cp.stderr or "")
    m = re.search(r"(\d+)\s*/\s*(\d+)\s+blocks", out)
    if not m:
        raise RuntimeError("could not parse free space from fsck.cpm:\n" + out)
    used, total = int(m.group(1)), int(m.group(2))
    free_blocks = total - used
    return free_blocks * config.CPM_BLOCK_SIZE, free_blocks


def put_file(work, host_name, local_path, fmt=None):
    """Copy a local file into drive A: (user 0) of the image, overwriting."""
    cpmcp = _tool("cpmcp")
    fmt = _fmt(fmt)
    # _run pins cwd to CPMTOOLS_DIR, so resolve the host path to absolute or
    # cpmcp would look for it next to the exe instead of the caller's dir.
    local_path = os.path.abspath(local_path)
    # cpmtools' cpmcp refuses to overwrite ("file already exists"), so delete
    # any existing copy first (best-effort -- ignore "not found").
    cpmrm = _tool("cpmrm")
    _run([cpmrm, "-f", fmt, "-T", config.CPM_TYPE, work, f"0:{host_name}"])
    _check([cpmcp, "-f", fmt, "-T", config.CPM_TYPE, work,
            local_path, f"0:{host_name}"],
           f"cpmcp put {host_name}")


def put_text(work, host_name, text, fmt=None, crlf=True):
    """Write in-memory text into the image as host_name (8.3 uppercase)."""
    data = text.replace("\r\n", "\n")
    if crlf:
        data = data.replace("\n", "\r\n")
    tmp = tempfile.NamedTemporaryFile("w", delete=False, newline="")
    try:
        tmp.write(data)
        tmp.close()
        put_file(work, host_name, tmp.name, fmt)
    finally:
        os.unlink(tmp.name)


def read_file(work, host_name, fmt=None):
    """Read a file back out of drive A: as text.

    This cpmcp build has no stdout ('-') mode -- passing '-' just creates a file
    literally named '-'. So copy to a temp host file and read that back.
    """
    cpmcp = _tool("cpmcp")
    fmt = _fmt(fmt)
    tmpdir = tempfile.mkdtemp()
    dest = os.path.join(tmpdir, "out.bin")
    try:
        _check([cpmcp, "-f", fmt, "-T", config.CPM_TYPE, work,
                f"0:{host_name}", dest], f"cpmcp read {host_name}")
        with open(dest, "r", newline="") as fh:
            return fh.read()
    finally:
        for path in (dest, tmpdir):
            try:
                os.unlink(path) if os.path.isfile(path) else os.rmdir(path)
            except OSError:
                pass


def read_file_bin(work, host_name, fmt=None):
    """Read a file back out of drive A: as raw bytes (for binaries like .COM).

    Like read_file but binary -- never decodes. NOTE: CP/M stores files in
    128-byte records, so a .COM read back is the original PADDED to a record
    boundary; compare with roundtrip[:len(original)] == original, not equality.
    """
    cpmcp = _tool("cpmcp")
    fmt = _fmt(fmt)
    tmpdir = tempfile.mkdtemp()
    dest = os.path.join(tmpdir, "out.bin")
    try:
        _check([cpmcp, "-f", fmt, "-T", config.CPM_TYPE, work,
                f"0:{host_name}", dest], f"cpmcp read {host_name}")
        with open(dest, "rb") as fh:
            return fh.read()
    finally:
        for path in (dest, tmpdir):
            try:
                os.unlink(path) if os.path.isfile(path) else os.rmdir(path)
            except OSError:
                pass


def has_file(work, host_name, fmt=None):
    """True if host_name exists on the image (case-insensitive)."""
    try:
        listing = list_dir(work, fmt).upper()
    except RuntimeError:
        return False
    return host_name.upper() in listing


def ensure_profile(work, fmt=None, run_line=config.RUN_LINE):
    """Append run_line to PROFILE.SUB (preserving existing lines).

    Returns True if PROFILE.SUB was written, False if auto-run isn't viable
    (no SUBMIT.COM on disk) and the caller should use the keystroke fallback.
    """
    fmt = _fmt(fmt)
    if not has_file(work, "SUBMIT.COM", fmt):
        return False
    existing = ""
    if has_file(work, config.PROFILE_NAME, fmt):
        try:
            existing = read_file(work, config.PROFILE_NAME, fmt)
        except RuntimeError:
            existing = ""
    # CP/M text files end with a 0x1A (Ctrl-Z) EOF, often followed by NUL record
    # padding. SUBMIT stops processing at that EOF, so anything appended after it
    # never runs -- truncate there before adding our run line.
    eof = existing.find("\x1a")
    if eof != -1:
        existing = existing[:eof]
    lines = [ln.rstrip("\r\n") for ln in existing.splitlines() if ln.strip()]
    if run_line not in lines:
        lines.append(run_line)
    put_text(work, config.PROFILE_NAME, "\r\n".join(lines) + "\r\n", fmt)
    return True

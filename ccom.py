"""Phase 1 (.COM path) - z88dk compile wrapper.

Compiles C (later asm) to a Z80 CP/M `.COM` for the PCW. Mirrors diskimg's
discipline: never relies on a global PATH -- it reads the toolchain location from
config (Z88DK_DIR / ZCCCFG, persisted by install_z88dk.py) and injects bin +
ZCCCFG into the *subprocess* env only. Builds in a space-free temp dir because
z88dk is fragile with spaces in its paths and litters .map/.lis/.o files; only
the resulting .COM is copied back out.

The .COM is then injected BINARY via diskimg.put_file (NEVER put_text -- LF->CRLF
would corrupt machine code) and run as config.COM_RUN_CMD ("A:PROG").
"""

import os
import shutil
import subprocess
import sys
import tempfile

import config


def _zcc(z88dk_dir):
    """Resolve the zcc launcher under <z88dk_dir>/bin, or exit with guidance."""
    for name in ("zcc.exe", "zcc"):
        cand = os.path.join(z88dk_dir, "bin", name)
        if os.path.exists(cand):
            return cand
    sys.exit(
        f"ERROR: zcc not found under {os.path.join(z88dk_dir, 'bin')}.\n"
        f"       Run: python install_z88dk.py   (or set Z88DK_DIR)."
    )


def _env(z88dk_dir, zcccfg):
    """Subprocess env with z88dk's bin on PATH and ZCCCFG set (this proc only)."""
    env = dict(os.environ)
    env["PATH"] = os.path.join(z88dk_dir, "bin") + os.pathsep + env.get("PATH", "")
    env["ZCCCFG"] = zcccfg
    return env


def _find_com(bdir):
    """Locate the produced .COM in the build dir (appmake casing varies)."""
    exact = os.path.join(bdir, "PROG.COM")
    if os.path.exists(exact):
        return exact
    for f in os.listdir(bdir):
        if f.lower().endswith(".com"):
            return os.path.join(bdir, f)
    return None


def compile_c(src, out_com, *, target=None, subtype=None, compiler=None,
              flags=None, defines=None, z88dk_dir=None, zcccfg=None,
              tpa_limit=None):
    """Compile a C source to a PCW .COM. Returns (out_com_path, size_bytes).

    Raises RuntimeError on a compile failure (the captured zcc stderr is the
    useful signal) or if the result is empty / over the TPA ceiling.
    """
    z88dk_dir = z88dk_dir or config.Z88DK_DIR
    zcccfg = zcccfg or config.ZCCCFG
    target = target or config.ZCC_TARGET
    subtype = subtype or config.ZCC_SUBTYPE
    compiler = compiler or config.ZCC_COMPILER
    flags = list(config.ZCC_FLAGS if flags is None else flags)
    tpa_limit = config.COM_TPA_BYTES if tpa_limit is None else tpa_limit

    src = os.path.abspath(src)
    if not os.path.exists(src):
        sys.exit(f"ERROR: source not found: {src}")
    zcc = _zcc(z88dk_dir)

    bdir = tempfile.mkdtemp(prefix="ccom_")     # space-free (under %LOCALAPPDATA%)
    try:
        shutil.copyfile(src, os.path.join(bdir, "prog.c"))
        args = [zcc, target, f"-subtype={subtype}", f"-compiler={compiler}"]
        args += [f"-D{d}" for d in (defines or [])]
        args += flags
        args += ["-o", "PROG.COM", "prog.c"]
        cp = subprocess.run(args, cwd=bdir, env=_env(z88dk_dir, zcccfg),
                            capture_output=True, text=True)
        com = _find_com(bdir)
        if cp.returncode != 0 or not com:
            raise RuntimeError(
                f"zcc failed (exit {cp.returncode}):\n"
                f"  cmd: {' '.join(args)}\n"
                f"  err: {(cp.stderr or cp.stdout).strip()}"
            )
        size = os.path.getsize(com)
        if size == 0:
            raise RuntimeError("zcc produced an empty .COM")
        if size > tpa_limit:
            raise RuntimeError(
                f".COM is {size} bytes, over the {tpa_limit}-byte TPA ceiling"
            )
        out_com = os.path.abspath(out_com)
        shutil.copyfile(com, out_com)
        return out_com, size
    finally:
        shutil.rmtree(bdir, ignore_errors=True)

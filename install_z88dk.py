#!/usr/bin/env python3
r"""Install the z88dk Z80 cross-compiler for the PCW .COM path.

The z88dk win32 nightly is a PREBUILT package (compiler, libraries, DLLs) -- so
unlike cpmtools there is nothing to compile. This installer is pure Python: it
downloads the zip, extracts to a SPACE-FREE dir (default C:\z88dk, because z88dk
is fragile with spaces in its install/ZCCCFG path and this project lives under a
spaced path), persists Z88DK_DIR + ZCCCFG via setx, and verifies by compiling a
tiny C program to a .COM (reusing ccom.compile_c).

Usage:
    python install_z88dk.py            # download + install + verify
    python install_z88dk.py --check    # verify an existing install (no download)
    python install_z88dk.py --dir D    # stage to D instead of C:\z88dk
    python install_z88dk.py --url U     # override the nightly URL
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

import config


def download(url, dest):
    print(f">> downloading {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "pcwdev-installer"})
    with urllib.request.urlopen(req, timeout=180) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f)
    print(f"   got {os.path.getsize(dest) // (1024 * 1024)} MB")


def extract(zip_path, stage):
    print(f">> extracting into {stage}")
    os.makedirs(stage, exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(stage)


def find_root(stage):
    """The dir that actually contains lib/config and a bin/zcc launcher."""
    if not os.path.isdir(stage):
        return None
    cands = [stage] + [os.path.join(stage, d) for d in os.listdir(stage)]
    for d in cands:
        if not os.path.isdir(d):
            continue
        has_cfg = os.path.isdir(os.path.join(d, "lib", "config"))
        has_zcc = (os.path.exists(os.path.join(d, "bin", "zcc.exe"))
                   or os.path.exists(os.path.join(d, "bin", "zcc")))
        if has_cfg and has_zcc:
            return d
    return None


def persist(name, value):
    """Set for this process and persist for future shells (user env)."""
    os.environ[name] = value
    subprocess.run(["setx", name, value], stdout=subprocess.DEVNULL, check=False)


def verify(root, zcccfg):
    print(">> verifying with a test compile ...")
    import ccom  # imported here so --check works after env is set
    tmp = tempfile.mkdtemp(prefix="z88dkchk_")
    try:
        csrc = os.path.join(tmp, "chk.c")
        with open(csrc, "w") as f:
            f.write('#include <stdio.h>\n'
                    'int main(void){printf("Z88DK-OK\\n");return 0;}\n')
        com, size = ccom.compile_c(csrc, os.path.join(tmp, "CHK.COM"),
                                   z88dk_dir=root, zcccfg=zcccfg)
        print(f"   compiled {os.path.basename(com)}: {size} bytes "
              f"(<= {config.COM_TPA_BYTES} TPA)")
    except Exception as exc:  # noqa: BLE001 -- surface zcc's message
        sys.exit(f"ERROR: z88dk staged but the test compile failed:\n  {exc}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true",
                    help="verify an existing install; don't download")
    ap.add_argument("--dir", default=config.Z88DK_DIR,
                    help=r"stage dir (default %(default)s)")
    ap.add_argument("--url", default=config.Z88DK_URL, help="nightly zip URL")
    args = ap.parse_args()

    stage = os.path.abspath(args.dir)
    if " " in stage:
        print(f"WARNING: stage path has spaces:\n  {stage}\n"
              "         z88dk is fragile with spaces -- prefer e.g. C:\\z88dk.")

    if args.check:
        root = find_root(stage)
        if not root:
            sys.exit(f"ERROR: no z88dk (lib/config + bin/zcc) found under {stage}.")
        verify(root, os.path.join(root, "lib", "config"))
        print("z88dk: OK")
        return

    tmp = tempfile.mkdtemp(prefix="z88dkdl_")
    try:
        zpath = os.path.join(tmp, "z88dk.zip")
        download(args.url, zpath)
        extract(zpath, stage)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    root = find_root(stage)
    if not root:
        sys.exit(f"ERROR: extracted, but couldn't locate the z88dk root "
                 f"(lib/config + bin/zcc) under {stage}.")
    zcccfg = os.path.join(root, "lib", "config")
    persist("Z88DK_DIR", root)
    persist("ZCCCFG", zcccfg)
    verify(root, zcccfg)

    print("\n" + "=" * 60)
    print("z88dk installed and wired up.")
    print(f"  Z88DK_DIR = {root}")
    print(f"  ZCCCFG    = {zcccfg}  (both persisted via setx)")
    print("  Open a NEW shell for these to be visible everywhere.")
    print("  Next: python pcwdev.py cc hello.c   (compile-only smoke test)")
    print("=" * 60)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""pcwdev - drive Mallard BASIC on a MiSTer Amstrad PCW core from the dev loop.

Subcommands:
  preflight            Phase 0 checks (API, SSH, master backup, format, mgl).
  run PROG.BAS [opts]  Inject -> upload -> cold boot -> run -> screenshot.
  launch               Cold-boot DEV.mgl as-is (no disk rebuild).
  shot                 Take + fetch a screenshot of the current screen.

Examples:
  python pcwdev.py preflight
  python pcwdev.py run hello.bas
  python pcwdev.py run hello.bas --no-autorun --settle 12
"""

import argparse
import os
import random
import sys

import ccom
import config
import device
import diskimg
import feedback


def _resolve_format(image):
    """Return a working cpmtools -f format, detecting + caching if needed."""
    if config.CPM_FORMAT:
        return config.CPM_FORMAT
    fmt = diskimg.detect_format(image)
    print(f"  detected CP/M format: {fmt} "
          f"(pin it in config.CPM_FORMAT to skip detection)")
    config.CPM_FORMAT = fmt
    return fmt


def cmd_preflight(args):
    ok = True

    print("[1] API /sysinfo ...")
    try:
        info = device.sysinfo()
        print(f"    OK: {info.get('version') or info}")
    except Exception as e:
        ok = False
        print(f"    FAIL: {e}")

    print("[2] SSH + games folder listing ...")
    try:
        out = device.ssh(f'ls -la "{config.GAMES}/"')
        print("    OK (first lines):")
        for line in out.splitlines()[:6]:
            print("      " + line)
    except SystemExit as e:
        ok = False
        print(f"    FAIL: {e}")

    print("[3] Back up master .dsk off-device ...")
    try:
        path = device.backup_master()
        size = os.path.getsize(path)
        print(f"    OK: {path} ({size} bytes)")
    except SystemExit as e:
        ok = False
        print(f"    FAIL: {e}")

    print("[4] cpmtools + CP/M format detection ...")
    if not os.path.exists(config.LOCAL_MASTER):
        print("    SKIP: no local master backup (step 3 must pass first)")
    else:
        try:
            fmt = _resolve_format(config.LOCAL_MASTER)
            listing = diskimg.list_dir(config.LOCAL_MASTER, fmt)
            free_b, free_blk = diskimg.free_space(config.LOCAL_MASTER, fmt)
            print(f"    OK: format={fmt}; free {free_b // 1024}K "
                  f"({free_blk} blocks); MAX_PROG_BYTES={config.MAX_PROG_BYTES // 1024}K")
            print("    sample listing:")
            for line in listing.splitlines()[:8]:
                print("      " + line)
        except (RuntimeError, SystemExit) as e:
            ok = False
            print(f"    FAIL: {e}")

    print("[5] Write DEV.mgl on device ...")
    try:
        device.write_mgl()
        print("    OK: DEV.mgl written + verified")
    except SystemExit as e:
        ok = False
        print(f"    FAIL: {e}")

    print()
    print("PREFLIGHT:", "ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED")
    return 0 if ok else 1


def _capture():
    """Take + fetch a screenshot and report (shared by run/runc/shot)."""
    print("[boot] capturing screenshot ...")
    png = feedback.shot()
    if png:
        print(f"    saved: {png}")
        text = feedback.read_screen(png)
        if text:
            print("    --- OCR ---")
            print("    " + text.replace("\n", "\n    "))
        else:
            print("    (OCR unavailable; open the PNG to read the screen)")
    else:
        print("    WARN: no screenshot retrieved")
    return png


def _deploy_and_capture(work, settle, after_boot=None):
    """Shared tail for both artifact kinds: upload -> mgl -> cold-boot -> shot.

    `after_boot` (optional) runs once the core is up + settled, before the shot
    (used by the .bas keystroke fallback). Identical for .bas and .COM.
    """
    print("[boot] uploading working disk to device ...")
    device.upload(work, config.WORK)
    print("[boot] ensuring DEV.mgl exists ...")
    device.write_mgl()
    print("[boot] cold booting PCW core ...")
    device.cold_boot()
    device.wait_until_running(settle=settle)
    if after_boot:
        after_boot()
    return _capture()


def cmd_run(args):
    src = args.prog
    if not os.path.exists(src):
        sys.exit(f"ERROR: source not found: {src}")

    size = os.path.getsize(src)
    if size > config.MAX_PROG_BYTES:
        sys.exit(f"ERROR: {src} is {size} bytes, over the {config.MAX_PROG_BYTES}-byte "
                 f"limit (the boot disk has only ~84K free on A:). Shrink the program.")

    print(f"[1] Building working disk from master ...")
    if not os.path.exists(config.LOCAL_MASTER):
        print("    no local master backup; fetching from device ...")
        device.backup_master()
    fmt = _resolve_format(config.LOCAL_MASTER)
    work = diskimg.make_working_copy()

    # Dynamic guard: confirm the program actually fits this disk's free space
    # (the master copy has no PROG.BAS yet, so this is the real budget).
    try:
        free_b, free_blk = diskimg.free_space(work, fmt)
        print(f"    disk free: {free_b // 1024}K ({free_blk} blocks); "
              f"program is {size} bytes")
        if size > free_b:
            sys.exit(f"ERROR: {src} ({size} B) does not fit the {free_b} B free on A:.")
    except RuntimeError as e:
        print(f"    (free-space check skipped: {e})")

    print(f"[2] Injecting {src} as {config.PROG_NAME} (LF->CRLF) ...")
    # BASIC source must use CP/M CRLF line endings, not Unix LF -- otherwise
    # the screen "staircases" and Mallard can't parse/run the program. put_text
    # normalizes any mix to CRLF; put_file (raw byte copy) would not.
    with open(src, "r", newline="") as fh:
        text = fh.read()
    # Inject entropy: the PCW cold-boots deterministically and Mallard's
    # RANDOMIZE with no argument PROMPTS (which would hang), so a program that
    # wants randomness puts the {{SEED}} token (e.g. `RANDOMIZE {{SEED}}`) and we
    # substitute a fresh value here. No-op for programs without the token.
    if "{{SEED}}" in text:
        seed = random.randint(1, 32767)
        text = text.replace("{{SEED}}", str(seed))
        print(f"    seeded RNG with {seed}")
    diskimg.put_text(work, config.PROG_NAME, text, fmt)

    autorun = not args.no_autorun
    if autorun:
        print("[3] Setting PROFILE.SUB to auto-run ...")
        autorun = diskimg.ensure_profile(work, fmt)
        if not autorun:
            print("    SUBMIT.COM absent -> falling back to keystrokes")

    after = None
    if not autorun:
        def after():
            print("[boot] sending run command via keystrokes ...")
            import keyboard
            import time
            drive = "B:" if args.drive_b else ""
            keyboard.run_basic(prog="PROG", drive=drive)
            time.sleep(args.settle)

    _deploy_and_capture(work, args.settle, after)
    print("Done.")
    return 0


def cmd_cc(args):
    """Compile a .c to a .COM locally (no device) -- fast iteration."""
    src = args.prog
    if not os.path.exists(src):
        sys.exit(f"ERROR: source not found: {src}")
    out = args.out or os.path.join(config.HERE, config.COM_NAME)
    try:
        com, size = ccom.compile_c(src, out, compiler=args.compiler,
                                   defines=list(args.define or []))
    except RuntimeError as e:
        sys.exit(f"ERROR: compile failed:\n{e}")
    print(f"compiled {com}: {size} bytes (TPA ceiling {config.COM_TPA_BYTES})")
    return 0


def cmd_runc(args):
    """Compile a .c -> .COM, inject BINARY, boot, run as A:PROG, screenshot."""
    src = args.prog
    if not os.path.exists(src):
        sys.exit(f"ERROR: source not found: {src}")

    print(f"[1] Compiling {src} -> {config.COM_NAME} (z88dk {args.compiler}) ...")
    com_path = os.path.join(config.HERE, config.COM_NAME)

    # Auto-seed randomness -- mirror cmd_run's {{SEED}} substitution for .bas.
    defines = list(args.define or [])
    if not any(d.startswith("PCW_SEED") or d.startswith("PCW_SEED=") for d in defines):
        seed = random.randint(1, 32767)
        defines.append(f"PCW_SEED={seed}")
        print(f"    seeded RNG with PCW_SEED={seed}")

    try:
        com_path, size = ccom.compile_c(src, com_path, compiler=args.compiler,
                                        defines=defines)
    except RuntimeError as e:
        sys.exit(f"ERROR: compile failed:\n{e}")
    print(f"    {config.COM_NAME}: {size} bytes (TPA ceiling {config.COM_TPA_BYTES})")
    if size > config.MAX_PROG_BYTES:
        sys.exit(f"ERROR: {config.COM_NAME} ({size} B) over the {config.MAX_PROG_BYTES}-byte "
                 "disk cap.")

    print("[2] Building working disk from master ...")
    if not os.path.exists(config.LOCAL_MASTER):
        print("    no local master backup; fetching from device ...")
        device.backup_master()
    fmt = _resolve_format(config.LOCAL_MASTER)
    work = diskimg.make_working_copy()
    try:
        free_b, _ = diskimg.free_space(work, fmt)
        print(f"    disk free: {free_b // 1024}K; .COM is {size} bytes")
        if size > free_b:
            sys.exit(f"ERROR: {config.COM_NAME} ({size} B) does not fit {free_b} B free.")
    except RuntimeError as e:
        print(f"    (free-space check skipped: {e})")

    # BINARY inject -- never put_text (LF->CRLF would corrupt machine code).
    print(f"[3] Injecting {config.COM_NAME} (BINARY) ...")
    diskimg.put_file(work, config.COM_NAME, com_path, fmt)

    print(f"[4] Setting PROFILE.SUB to auto-run '{config.COM_RUN_CMD}' ...")
    if not diskimg.ensure_profile(work, fmt, run_line=config.COM_RUN_CMD):
        sys.exit("ERROR: SUBMIT.COM absent on disk; .COM auto-run needs it.")

    _deploy_and_capture(work, args.settle)
    print("Done.")
    return 0


def cmd_launch(args):
    device.write_mgl()
    device.cold_boot()
    device.wait_until_running(settle=args.settle)
    print("Launched DEV.mgl.")
    return 0


def cmd_shot(args):
    png = feedback.shot()
    if not png:
        sys.exit("ERROR: no screenshot retrieved")
    print(f"saved: {png}")
    text = feedback.read_screen(png)
    if text:
        print(text)
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("preflight", help="run Phase 0 checks")
    sp.set_defaults(func=cmd_preflight)

    sr = sub.add_parser("run", help="inject a .bas, boot, run, screenshot")
    sr.add_argument("prog", help="path to a local Mallard BASIC source file")
    sr.add_argument("--no-autorun", action="store_true",
                    help="run via keystrokes instead of PROFILE.SUB")
    sr.add_argument("--drive-b", action="store_true",
                    help="Option 2: run from drive B: (keystroke path)")
    sr.add_argument("--settle", type=int, default=config.SETTLE,
                    help="seconds to wait after boot/run")
    sr.set_defaults(func=cmd_run)

    scc = sub.add_parser("cc", help="compile a .c to a .COM (no device)")
    scc.add_argument("prog", help="path to a C source file")
    scc.add_argument("--compiler", default=config.ZCC_COMPILER,
                     help="z88dk compiler: sccz80 (default) or sdcc")
    scc.add_argument("--out", help="output .COM path (default PROG.COM)")
    scc.add_argument("--define", action="append",
                     help="-D NAME[=VALUE] passed to zcc (repeatable)")
    scc.set_defaults(func=cmd_cc)

    sc = sub.add_parser("runc", help="compile a .c, inject, boot, run, screenshot")
    sc.add_argument("prog", help="path to a C source file")
    sc.add_argument("--compiler", default=config.ZCC_COMPILER,
                    help="z88dk compiler: sccz80 (default) or sdcc")
    sc.add_argument("--define", action="append",
                    help="-D NAME[=VALUE] passed to zcc (repeatable)")
    sc.add_argument("--settle", type=int, default=config.SETTLE,
                    help="seconds to wait after boot before screenshot")
    sc.set_defaults(func=cmd_runc)

    sl = sub.add_parser("launch", help="cold-boot DEV.mgl without rebuilding")
    sl.add_argument("--settle", type=int, default=config.SETTLE)
    sl.set_defaults(func=cmd_launch)

    ss = sub.add_parser("shot", help="take + fetch a screenshot")
    ss.set_defaults(func=cmd_shot)

    args = p.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()

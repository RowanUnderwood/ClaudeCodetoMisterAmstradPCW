# Plan — Add `.COM` cross-compilation to the PCW dev loop

Guidance for a Claude Code instance. Read `CLAUDE.md`, `README.md`, and
`mister-pcw-basic-plan.md` first. This plan ADDS a C/assembly → `.COM` path
alongside the existing `.bas` path. It reuses the proven transport, launch, and
screenshot machinery unchanged.

## 0. What this adds

A second kind of artifact. Today: write `.bas` → inject (CRLF text) → boot →
`BASIC A:PROG`. New: write `.c` (or `.asm`) → **compile to a Z80 `.COM`** →
inject (BINARY) → boot → run the `.COM` by name. A `.COM` is native Z80 machine
code that loads into the TPA at `0x0100` and runs directly — no interpreter,
much faster than Mallard, and the runtime size ceiling is the 61K TPA rather
than Mallard's ~31K workspace.

## 1. Design principle: reuse, don't rebuild

Everything from `DEV_work.dsk` onward is identical to the `.bas` path:

```
write .c  ->  compile to PROG.COM            (NEW: ccom.py + z88dk)
          ->  inject PROG.COM into a COPY     (diskimg.put_file — BINARY)
          ->  PROFILE.SUB run line = "A:PROG" (ensure_profile, parametrised)
          ->  upload + cold-boot + screenshot (device.py / feedback.py — unchanged)
```

So `device.py`, `feedback.py`, the `.mgl`, cold-boot, and `shot()` need **no
changes**. The new surface is: a compiler installer, a compile wrapper, a few
`config` values, a CLI command, and a C-dialect skill.

## 2. Compiler: z88dk (prebuilt Windows nightly)

Use **z88dk** — Z80 C compiler + assembler + linker with a real Amstrad PCW
target. Two compilers ship in it: `sccz80` (native, robust, default) and
`zsdcc` (patched sdcc, smaller/faster output). Known-good PCW invocation:

```
zcc +cpm -subtype=pcw80 -compiler=sccz80 -create-app -o PROG.COM prog.c
```

> Why download, not build (unlike cpmtools): the win32 nightly is a
> self-contained package that already includes the `zsdcc`/`zsdcpp` binaries,
> the libraries, and required DLLs. There is nothing to compile, so the
> installer just downloads, unzips, sets two env vars, and verifies. This is
> simpler than `build_cpmtools.sh` (which needed a from-source libdsk build).

- Download: `http://nightly.z88dk.org/z88dk-win32-latest.zip`
- Env (Windows): `ZCCCFG = {z88dk}\lib\config`, add `{z88dk}\bin` to PATH.

## 3. New / changed files

| File | Status | Purpose |
| --- | --- | --- |
| `build_z88dk.sh` | NEW | Download + stage the z88dk win32 nightly into `z88dk\`. Mirrors `build_cpmtools.sh`'s role (runs under Git Bash/MSYS2, prints machine-readable result lines). |
| `install_z88dk.py` | NEW | Orchestrator. Mirrors `install_cpmtools.py`: find bash, run the `.sh`, persist `Z88DK_DIR` + `ZCCCFG` via `setx`, verify with a test compile. `--check` re-verifies; `--url` overrides. |
| `ccom.py` | NEW | `zcc` wrapper: `compile_c()` (and later `compile_asm()`), locate z88dk from `config`, inject `bin`+`ZCCCFG` into the subprocess env, capture stderr, size-check the `.COM`. |
| `config.py` | EDIT | Add the `Z88DK_*` / `ZCC_*` / `.COM` constants (see §4). |
| `diskimg.py` | MINOR | Confirm `put_file` is the BINARY path (no CRLF). Add `put_com()` convenience if helpful. Confirm `ensure_profile()` takes the run command as a parameter. |
| `pcwdev.py` | EDIT | New subcommands `cc` (compile only) and `runc` (compile→inject→boot→shot). Factor the shared inject→profile→boot→shot tail out of `run` so both artifact kinds use it. |
| `.claude/skills/z88dk-pcw/SKILL.md` | NEW | C-for-PCW dialect/gotchas reference (pragmas, console, BDOS), mirroring the `mallard-basic` skill. |
| `hello.c` (+ maybe `feature.c`) | NEW | Example programs / smoke tests. |

## 4. `config.py` additions

```
# --- z88dk / .COM ---
Z88DK_DIR     = None          # staged dir, e.g. <project>\z88dk ; persisted by installer
ZCCCFG        = None          # {Z88DK_DIR}\lib\config ; persisted by installer
ZCC_TARGET    = "+cpm"
ZCC_SUBTYPE   = "pcw80"       # PCW 80-col console
ZCC_COMPILER  = "sccz80"      # or "sdcc" (zsdcc) for smaller/faster output
ZCC_FLAGS     = ["-create-app"]   # appmake emits the .COM ; add "-lm" only if floats used
COM_NAME      = "PROG.COM"    # fixed injected name (keeps PROFILE.SUB stable)
COM_RUN_CMD   = "A:PROG"      # drive-qualified (default drive is M: via setdef m:,*)
COM_TPA_BYTES = 61 * 1024     # runtime size ceiling (TPA from the boot banner)
Z88DK_URL     = "http://nightly.z88dk.org/z88dk-win32-latest.zip"
```

`Z88DK_DIR`/`ZCCCFG` follow the same pattern as `CPMTOOLS_DIR`: persisted by the
installer, picked up by a *new* shell. `ccom.py` should not rely on global PATH —
read `config.Z88DK_DIR`, then set `ZCCCFG` and prepend `{Z88DK_DIR}\bin` to
`PATH` **in the subprocess env only** (exactly like `diskimg` pins
`cwd=CPMTOOLS_DIR`).

## 5. `build_z88dk.sh` — the installer the user asked for

Same shape as `build_cpmtools.sh`: runnable under the Bash tool, strict mode,
takes the stage dir as an argument, prints machine-readable `KEY=value` lines at
the end for `install_z88dk.py` to parse. Because the package is prebuilt, there
is no compile step — just fetch, unzip, locate, report.

```bash
#!/usr/bin/env bash
# build_z88dk.sh — download & stage the z88dk win32 nightly (prebuilt).
# Usage: build_z88dk.sh <stage_dir> [url]
# Prints, on success:  Z88DK_DIR=<dir>   ZCCCFG=<dir>   Z88DK_BIN=<dir>
set -euo pipefail

STAGE="${1:?usage: build_z88dk.sh <stage_dir> [url]}"
URL="${2:-http://nightly.z88dk.org/z88dk-win32-latest.zip}"

mkdir -p "$STAGE"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
echo ">> downloading $URL"
curl -fL --retry 3 -o "$TMP/z88dk.zip" "$URL"

echo ">> unzipping into $STAGE"
# unzip (Git Bash has it; MSYS2: pacman -S unzip). The zip contains a top-level
# z88dk/ folder, so extract then locate the real root below.
unzip -q -o "$TMP/z88dk.zip" -d "$STAGE"

# Find the dir that actually contains lib/config and a zcc launcher.
ROOT=""
for d in "$STAGE" "$STAGE"/* ; do
  if [ -d "$d/lib/config" ] && { [ -e "$d/bin/zcc.exe" ] || [ -e "$d/bin/zcc" ]; }; then
    ROOT="$d"; break
  fi
done
[ -n "$ROOT" ] || { echo "!! could not locate z88dk root (lib/config + bin/zcc) under $STAGE" >&2; exit 1; }

# Emit Windows-style paths if cygpath is available, else POSIX (wrapper handles both).
to_win() { command -v cygpath >/dev/null 2>&1 && cygpath -w "$1" || printf '%s' "$1"; }
echo "Z88DK_DIR=$(to_win "$ROOT")"
echo "ZCCCFG=$(to_win "$ROOT/lib/config")"
echo "Z88DK_BIN=$(to_win "$ROOT/bin")"
echo ">> z88dk staged OK"
```

Notes for the implementer:
- Mirror however `install_cpmtools.py` locates a Bash to run its `.sh` (Git Bash
  is present; MSYS2 is also available). The prebuilt path needs only `curl` +
  `unzip`, so Git Bash suffices — no MSYS2 toolchain required.
- If the nightly URL ever 404s, the official release zip on the z88dk GitHub
  releases page is the fallback; keep the URL in `config.Z88DK_URL` and accept
  `--url`.
- **Avoid spaces in the stage path.** z88dk is historically fragile with spaces
  in its own install path — stage into the project dir (e.g. `z88dk\`) and keep
  the project path space-free, or document the risk.

### `install_z88dk.py` responsibilities

1. Resolve stage dir (default `<project>\z88dk`). Find Bash (reuse
   `install_cpmtools.py`'s finder). Run `build_z88dk.sh <stage> [url]`.
2. Parse the `Z88DK_DIR=`, `ZCCCFG=`, `Z88DK_BIN=` lines from stdout.
3. Persist `Z88DK_DIR` and `ZCCCFG` via `setx` (like `CPMTOOLS_DIR`). Do **not**
   mutate the global `PATH` — `ccom.py` injects `bin` into the subprocess env at
   runtime, which avoids the `setx PATH` truncation trap.
4. **Verify**: write a temp `hello.c`, run the §6 `zcc` line, assert `PROG.COM`
   exists and is non-empty and ≤ `COM_TPA_BYTES`. Print OK / the captured
   `zcc` stderr on failure.
5. `--check` re-verifies an existing install (no download). `--url` overrides.

## 6. `ccom.py` — compile wrapper

```
compile_c(src, out_com, *, target=config.ZCC_TARGET, subtype=config.ZCC_SUBTYPE,
          compiler=config.ZCC_COMPILER, flags=config.ZCC_FLAGS, defines=None) -> path
```

Builds, e.g.:
```
zcc +cpm -subtype=pcw80 -compiler=sccz80 -create-app -o <out_com> <src>
```
- Run with `env` = current env + `ZCCCFG=config.ZCCCFG` and
  `PATH = {Z88DK_DIR}\bin;` + PATH. Build in a temp/`build/` dir; z88dk also
  drops `.map`/`.lis`/intermediate files — keep them out of the project root and
  only return the `.COM`.
- On non-zero exit, raise with the captured stderr (z88dk errors are the useful
  signal). On success, assert size ≤ `COM_TPA_BYTES` and warn if it approaches
  `diskimg.free_space()` of the working disk.
- `defines` → `-DNAME=VALUE` (used for the optional seed, §9).
- Later: `compile_asm(src, out_com)` via `z88dk-z80asm` + appmake, or `pasmo
  --bin`. Phase 2 — C first.

## 7. Integration into the loop (`pcwdev.py`)

Refactor the existing `run` so the tail is shared:

```
_deploy_and_capture(work_dsk, run_cmd, settle):
    device.upload(work_dsk -> WORK_REL on SD)
    device.cold_boot(); device.wait_until_running()
    feedback.shot()
```

- `run  <prog>.bas` (unchanged behaviour): make_working_copy → `put_text`
  (LF→CRLF) `PROG.BAS` → `ensure_profile("BASIC A:PROG")` → `_deploy_and_capture`.
- `runc <prog>.c` (NEW): `ccom.compile_c` → `PROG.COM` → make_working_copy →
  **`put_file`** (BINARY) `PROG.COM` → `ensure_profile("A:PROG")` →
  `_deploy_and_capture`. Add `--compiler`, `--settle`, `--define`.
- `cc <prog>.c` (NEW): compile only; print `.COM` path + size; no device. Fast
  feedback while iterating on C before spending a ~40s boot.

## 8. Phases

0. **Install + verify compiler.** Write `build_z88dk.sh` + `install_z88dk.py`.
   Run it; confirm the test compile yields a runnable-size `PROG.COM`. Add
   `cc`/preflight compiler check. *Gate: do not proceed until a local `hello.c`
   compiles.*
1. **`ccom.py`** with `compile_c` + size checks; unit-test against `hello.c`.
2. **Disk + profile**: confirm `put_file` round-trips a binary unchanged
   (inject, `read_file`, compare bytes); confirm `ensure_profile` takes the run
   command.
3. **`runc` end-to-end** on hardware: `hello.c` → screenshot shows its output.
   Tune nothing else — boot/settle are already solved.
4. **`z88dk-pcw` skill** + a second example (`feature.c`) exercising console
   positioning and a compute loop (to show the speed win over BASIC).
5. **Polish**: `cc` quick-compile, `--compiler sdcc` path, optional asm, update
   `CLAUDE.md`/`README.md`.

## 9. `.COM`-specific gotchas (carry/adapt from CLAUDE.md)

- **Inject BINARY, never text.** A `.COM` MUST go in via `diskimg.put_file`.
  Routing it through `put_text` (the LF→CRLF path used for `.bas`) corrupts the
  machine code. This is the exact inverse of the "never `put_file` a `.bas`"
  rule.
- **Run drive-qualified `A:PROG`.** `PROFILE.SUB`'s `setdef m:,*` makes M: the
  default drive (same reason `BASIC A:PROG` is used for `.bas`). Inject as a
  fixed `PROG.COM` so the run line stays `A:PROG`.
- **8.3 uppercase name**, run without the extension (`PROG`, not `PROG.COM`).
- **Size ceilings:** runtime cap is the **61K TPA** (more generous than Mallard's
  ~31K), but the working disk's ~84K free still applies. `ccom` checks both.
- **Slim the binary** for text programs with the z88dk pragmas (smaller `.COM`,
  strips unused runtime): `#pragma output nostreams`, `nofileio`,
  `noprotectmsdos`, `noredir`, `nogfxglobals`. Put these in the skill's template.
- **Console:** prefer the native `pcw80` subtype (real PCW is 90×32). The
  portable `--generic-console` path is a fallback and is capped at 80×25, so it
  can't use the full width — and `gotoxy`/cursor positioning has known quirks;
  verify positioning on hardware before relying on it.
- **Compiled = fast.** The "interpreted BASIC is slow / capture lands mid-run"
  caveat mostly disappears — native Z80 finishes quickly. Boot (~40s) still
  dominates, so `config.SETTLE` is unchanged; compute-heavy work that needed a
  huge `--settle` in BASIC won't here. This is the main reason to use `.COM`.
- **Screenshots are still 266×200.** Keep output short/high-contrast (same as
  `.bas`).
- **Deterministic cold boot = no entropy.** If the C program needs randomness,
  seed it explicitly. Optional: mirror the `.bas` `{{SEED}}` trick — `runc`
  passes `-DPCW_SEED=<rand int>` and the program does `srand(PCW_SEED)`.
- **`ZCCCFG`/`Z88DK_DIR` need a new shell** to be visible after install (same as
  `CPMTOOLS_DIR`). `ccom` reads them from `config` and sets them per-subprocess,
  so a long-running session works without a restart.
- **Don't reintroduce the `device.BASE` double-`/api`** or write the master disk
  — all the existing invariants in `CLAUDE.md` still hold.

## 10. Open questions to verify on first run

1. Exact `zcc` flags that emit a `.COM` on this z88dk build —
   `-create-app` vs raw-binary-then-appmake. Known-good from the z88dk PCW
   forum: `zcc +cpm -subtype=pcw80 -compiler=sdcc -create-app -lm -o x.com x.c`.
2. `sccz80` vs `sdcc` default — start with `sccz80` (robust); switch to `sdcc`
   if size matters.
3. Whether `A:PROG` runs cleanly given `setdef m:,*` (it should; confirm once,
   same way `BASIC A:PROG` was confirmed).
4. `pcw80` console behaviour for cursor positioning if a program uses `conio.h`.

## 11. Docs to update when done

Append a "`.COM` cross-compilation" section to `README.md` (install step,
`cc`/`runc` usage) and a working-notes block to `CLAUDE.md` (the §9 gotchas, the
verified `zcc` line, `cf2dd`-style pinned facts for z88dk).

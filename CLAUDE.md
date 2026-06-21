# CLAUDE.md — working notes for this project

Guidance for an AI agent continuing work here. Read this and
`mister-pcw-basic-plan.md` before changing code.

## What this project does

Automates a dev loop that runs **Mallard BASIC** on a **MiSTer Amstrad PCW core**
(`192.168.2.56`) from the user's Windows PC: inject a `.bas` into a copy of the
CP/M boot disk, push it to the SD card, cold-boot the core via the Remote HTTP
API, auto-run it, and read the result back as a screenshot.

## Environment (this machine)

- **Windows 11**, PowerShell primary; a Bash (Git Bash) tool is also available.
- **Python 3.10.11**, `requests` 2.31.0 installed.
- **PuTTY present** (`plink`, `pscp` at `C:\Program Files\PuTTY`). Used for all
  SSH/SCP — **OpenSSH password auth fails on this host** ("too many auth
  failures"), so do NOT use `ssh`/`scp`. MiSTer host key is already cached, so
  `-batch` works.
- **cpmtools: INSTALLED** (was the one blocker). Built from source WITH libdsk by
  `install_cpmtools.py` (MSYS subsystem) into `cpmtools\bin` (self-contained:
  exes + `msys-2.0.dll` + `diskdefs`). `CPMTOOLS_DIR` is persisted via `setx`.
  Detected disk format = **`cf2dd`** (720K PCW), pinned in `config.CPM_FORMAT`.
  Re-verify anytime with `python install_cpmtools.py --check`.
- **tesseract: NOT installed.** OCR is optional; `feedback.read_screen()` returns
  `None` if absent.

## Credentials / target

- SSH: `root` / password `1` (in `config.SSH_PASS`).
- Remote API: `http://192.168.2.56:8182` — note `config.BASE` is the **root URL
  without `/api`**; helpers/callers add `/api/...` themselves. (A double-`/api` bug
  was already fixed once — don't reintroduce it.)
- PCW launch identifiers: system `AmstradPCW`, RBF `_Computer/Amstrad-PCW`
  (hyphen), disk mount type `s`, index 0 = A: / 1 = B:.
- Boot disk (master, read-only): `/media/fat/games/Amstrad PCW/cpm 2,11 boot
  PCW9512+ eng.dsk` — path has spaces, a comma, and `+`.

## Module map

- `config.py` — all constants. Change settings here, not in code.
- `diskimg.py` — cpmtools wrappers (local). `detect_format()` implements the
  plan's Phase 0 #7 format probe. `ensure_profile()` appends the run line to
  `PROFILE.SUB`, returns `False` if no `SUBMIT.COM` (→ keystroke fallback).
- `device.py` — PuTTY transport (`ssh`, `upload`, `download`, `_remote_spec`),
  `write_mgl`, `backup_master`, API helpers (`_get`/`_post`), `cold_boot`,
  `wait_until_running`.
- `feedback.py` — `shot()` (take + fetch newest PNG for the PCW core),
  `read_screen()` (tesseract OCR, optional).
- `keyboard.py` — ASCII→uinput keystroke fallback. Letters/digits/space are safe;
  PCW punctuation mapping is UNVERIFIED (verify `:` before trusting `BASIC B:PROG`).
- `pcwdev.py` — CLI: `preflight`, `run`, `launch`, `shot`.
- `rerun_mister_test.py` — standalone smoke test (writes `DEV.mgl`, launches the
  master disk). Good for confirming transport+launch in isolation.
- `install_cpmtools.py` + `build_cpmtools.sh` — one-shot installer for the
  cpmtools blocker. Finds/winget-installs MSYS2, compiles libdsk + cpmtools
  `--with-libdsk` from source, stages a self-contained `cpmtools\bin` (exes +
  DLLs + `diskdefs`), persists `CPMTOOLS_DIR` via `setx`, then auto-detects the
  master's format. `python install_cpmtools.py` to install; `--check` to
  re-verify. Built as MSYS *subsystem* (not ucrt64 native) so the relocated exe
  resolves its compiled-in `diskdefs` path via the bundled `msys-2.0.dll` root.

## Verified working (against the live device)

- `/api/sysinfo` → `0.4`; SSH listing; SCP backup (`master_backup.dsk`, 778,496 B);
  `DEV.mgl` written+verified; screenshot capture (CP/M Plus banner confirmed).
- `diskimg.*` against the local master copy: `make_working_copy`, `detect_format`
  (→ `cf2dd`), `list_dir`, `put_text`/`put_file` (incl. overwrite), `read_file`,
  `has_file`, `ensure_profile` (→ `True`; `SUBMIT.COM`/`PROFILE.SUB` present).

## diskimg.py fixes made during the cpmtools bring-up (cpmtools 2.23 behavior)

- `_run` now pins `cwd=CPMTOOLS_DIR` so the relative `diskdefs` lookup works
  (the relocated MSYS exe's compiled-in path doesn't resolve from Windows).
- `put_file` `cpmrm`s the target first — this cpmcp refuses to overwrite.
- `read_file` copies to a temp file — this cpmcp has no stdout (`-`) mode.

- **FULL `pcwdev.py run` PIPELINE, end to end** (2026-06-21): `python pcwdev.py
  run hello.bas` injected the program, auto-ran it via PROFILE.SUB, and a
  screenshot showed the program's output (`MALLARD-OK-1234 / SUM= 4 / LINE 1..3
  / DONE`). The loop works.

## Live-device gotchas learned during first end-to-end run (2026-06-21)

- **.mgl `path` is a bare filename** relative to the .mgl's own folder
  (`DEV_work.dsk`), NOT `games/Amstrad PCW/...`. A full path = disk doesn't
  mount = white screen. Use `delay="5"` (delay=1 was unreliable).
- **BASIC source must be CRLF.** Injecting LF-only source makes the screen
  "staircase" and Mallard can't run it. `pcwdev` now injects via `put_text`
  (LF->CRLF); never `put_file` a `.bas`.
- **Mallard BASIC has no `CLS`** (it's Locomotive business BASIC) -> "...error
  in <line>". Clear the screen with `PRINT CHR$(27);"E";`. Before writing ANY
  `.bas`, consult the **`mallard-basic` skill** (`.claude/skills/mallard-basic/
  SKILL.md`) for the real dialect/keywords (distilled from the manual .txt).
- **Run verb is `BASIC A:PROG`** (drive-qualified) because PROFILE.SUB's
  `setdef m:,*` makes M: the default drive, where PROG.BAS isn't.
- **Boot is slow (~35-40s)** before output appears (verbose PROFILE.SUB + pip
  copies to M:). `config.SETTLE` is 40. Screenshots taken earlier catch the
  boot/PROFILE text, not the result.
- **Interpreted BASIC is slow too.** Compute-heavy programs (nested loops, e.g.
  life.bas's per-cell neighbour counting over several generations) can run 30s+
  *after* boot, so `run`'s single auto-capture lands mid-run. For these, pass a
  bigger `--settle` or just take a follow-up `python pcwdev.py shot` once done.
- **Grids/tables need wide, high-contrast glyphs** to survive the 266x200 shot:
  double-width cells (`[]` live / `  ` dead) with `|` borders read far better
  than single `*`/`.`; size output to fit one 32-line screen so it doesn't
  scroll. (See life.bas / feature.bas as worked examples.)
- **MiSTer SAM is installed**: it auto-launches random games if left idle (at
  the menu or in a core) too long. Don't dawdle; capture and move on.
- **Screenshots are low-res (266x200)** from the Remote API -- 90-col PCW text
  is rough to read; no resolution knob found. Keep test output short/distinct.
- **Disk free space is tight (~84-86K on A:).** The 720K boot disk is mostly
  full of system files; `fsck.cpm` reports 43/357 free blocks (~86K) and CP/M
  `SHOW A:` ~84K. `config.MAX_PROG_BYTES` (80K) caps injected `.bas`, and
  `pcwdev run` also checks the live `diskimg.free_space()` of the working copy.
  Mallard's own workspace (~31K "free bytes") is the tighter cap on a *runnable*
  program -- a `.bas` can fit on disk yet be too big for BASIC to load.

## Not yet exercised

- Keystroke fallback (`keyboard.py`) against the real core (autorun path works,
  so this is only needed if SUBMIT.COM is ever absent).

## Conventions / gotchas

- **Never write the master disk.** Only ever copy it; all writes go to
  `DEV_work.dsk`. `master_backup.dsk` is the off-device safety copy.
- **Always launch via the `.mgl`**, never a bare `.dsk` (auto-detect boots the CPC
  core by mistake).
- **Quote remote paths** — they contain spaces/`+`. Use `device._remote_spec()`
  for pscp; `device.ssh()` commands quote paths inline.
- Cold-boot for every disk change; don't hot-swap under a running CP/M session.
- cpmtools needs `CPMTOOLS_DIR` set (persisted by the installer). A *new* shell
  picks it up; an already-open shell won't until restarted or set in-process.
- Verify Edits by trusting the tool result; the code has been import- and
  compile-checked and the live paths smoke-tested.

## Next steps

1. ~~Install cpmtools~~ DONE (`cf2dd` pinned). To rebuild: `python
   install_cpmtools.py`; to re-verify: `--check`.
2. `pcwdev.py run <prog>.bas` → validate the full loop; tune `config.SETTLE`.
   Watch the PROFILE.SUB EOF caveat above on first real run.
3. (Optional) install tesseract for OCR read-back.

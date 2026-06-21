# Claude → Amstrad PCW (MiSTer) dev loop

Drive **Mallard BASIC** on a **MiSTer Amstrad PCW core** (at `192.168.2.56`) from
your PC: generate a BASIC program, inject it into a copy of the CP/M boot disk,
launch the core, run the program, and read the result back as a screenshot — in
an automated loop.

See `mister-pcw-basic-plan.md` for the full design and rationale.

## How it works

```
generate PROG.BAS
  -> inject into a COPY of the boot disk        (cpmtools, local)
  -> scp the copy to the MiSTer SD card         (pscp)
  -> write/verify DEV.mgl launcher              (plink)
  -> cold-boot the PCW core via the Remote API  (HTTP :8182)
  -> PROFILE.SUB auto-runs `BASIC PROG`
  -> take + fetch a screenshot                  (HTTP, + optional OCR)
  -> loop
```

The master boot disk is **never written to** — it's backed up off-device and only
ever copied. All writes go to `DEV_work.dsk`.

## Files

| File | Purpose |
|------|---------|
| `config.py` | All settings: host, paths, CP/M format, timing. Edit here. |
| `diskimg.py` | cpmtools wrappers — build working disk, inject/read files, `PROFILE.SUB`, format auto-detect. |
| `device.py` | SSH/SCP transport (PuTTY) + Remote HTTP API: backup, `.mgl`, launch, status. |
| `feedback.py` | Take/fetch screenshots; optional tesseract OCR. |
| `keyboard.py` | Keystroke fallback (send a run command if auto-run isn't possible). |
| `pcwdev.py` | CLI front end: `preflight`, `run`, `launch`, `shot`. |
| `rerun_mister_test.py` | Standalone smoke test (writes `DEV.mgl` + launches the master). |
| `master_backup.dsk` | Off-device backup of the read-only boot disk. |
| `screenshots/` | Captured PNGs. |

## Requirements

- **Python 3.10+** with `requests` (installed).
- **PuTTY** (`plink`, `pscp`) — used for SSH/SCP password auth. Found on PATH or
  at `C:\Program Files\PuTTY`. (OpenSSH password auth did not work on this host.)
- **cpmtools built WITH libdsk** — *not yet installed*. Needed for the disk
  injection step. The boot image is a CPCEMU `.DSK` container, so libdsk
  (`-T dsk`) is required. Put `cpmcp`/`cpmls` on PATH or set `CPMTOOLS_DIR`.
- **tesseract** (optional) — for OCR of screenshots. If absent, the PNG is still
  saved; OCR is just skipped.

## Usage

```bash
# Phase 0 checks: API, SSH, master backup, format detection, .mgl
python pcwdev.py preflight

# Full loop: inject a local .bas, boot, run, screenshot
python pcwdev.py run hello.bas
python pcwdev.py run hello.bas --no-autorun --settle 12   # keystroke run + longer wait

# Re-boot the existing DEV.mgl without rebuilding the disk
python pcwdev.py launch

# Just grab a screenshot of the current screen
python pcwdev.py shot
```

## Status

Verified working against the live device:

- Remote API reachable (`/sysinfo` → `0.4`)
- SSH command + SCP file transfer (master backed up: 778,496 bytes)
- `DEV.mgl` written and verified on the SD card
- Screenshot capture/fetch (confirmed CP/M Plus prompt)

**Blocked on one prerequisite:** `cpmtools` (with libdsk) is not installed, so the
disk-injection path can't run yet. Once installed:

1. `python pcwdev.py preflight` auto-detects the CP/M disk format. Pin the printed
   value into `config.CPM_FORMAT` to skip re-detection.
2. `python pcwdev.py run yourprog.bas` exercises the whole loop.

## Notes / gotchas

- Always launch via the explicit `.mgl` (names `_Computer/Amstrad-PCW`). Launching
  a bare `.dsk` boots the wrong (CPC) core.
- The boot-disk path contains spaces, a comma, and `+` — remote paths are quoted
  for the remote shell in `device._remote_spec()`.
- Don't hot-swap a disk under a running CP/M session; always cold-boot.
- The PCW floppy controller can't format disks — never create a blank disk on the
  device; build images on the PC.

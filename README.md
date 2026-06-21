# Claude → Amstrad PCW (MiSTer) dev loop

Drive **Mallard BASIC** on a **MiSTer Amstrad PCW core** from your PC: generate a
BASIC program, inject it into a copy of the CP/M boot disk, launch the core, run
the program, and read the result back as a screenshot — in an automated loop.

See `mister-pcw-basic-plan.md` for the full design and `CLAUDE.md` for working
notes and hard-won gotchas.

## How it works

```
generate PROG.BAS
  -> inject into a COPY of the boot disk        (cpmtools+libdsk, local)
  -> scp the copy to the MiSTer SD card         (pscp)
  -> write/verify DEV.mgl launcher              (plink)
  -> cold-boot the PCW core via the Remote API  (HTTP :8182)
  -> PROFILE.SUB auto-runs `BASIC A:PROG`
  -> take + fetch a screenshot                  (HTTP, + optional OCR)
  -> loop
```

The master boot disk is **never written to** — it's backed up off-device and only
ever copied. All writes go to `DEV_work.dsk`.

---

## Quick start (point it at *your* MiSTer)

### MiSTer-side setup (one-time)

On the MiSTer itself, three things need to be in place. Your MiSTer must be on
the same network as your PC and reachable at the IP you'll put in `HOST`.

1. **The Amstrad-PCW core + a boot disk.** Install the `Amstrad-PCW` core (it's
   in the standard core sets / the `update_all` updater). Put a PCW CP/M boot
   disk — a CPCEMU `.dsk`, e.g. a PcW9512 CP/M Plus boot image — into
   `/media/fat/games/Amstrad PCW/`. That file's path is your `MASTER` setting.

2. **SSH** — enabled by default on MiSTer (Dropbear); login `root` / password `1`.
   Test from your PC with `plink root@<mister-ip>` and accept the host key once.
   If it was turned off, re-enable SSH via the on-screen **Scripts** menu or your
   `MiSTer.ini`.

3. **The Remote service** (`mrext`) — the web API this project drives, on port
   `8182`. Easiest install is the community **`update_all`** script: run it, and
   in its settings enable **MiSTer Extensions** (which installs/updates
   **Remote**); or add the mrext downloader database manually. It auto-starts on
   boot. Project + docs: <https://github.com/wizzomafizzo/mrext>. Verify it's up
   with `curl http://<mister-ip>:8182/api/sysinfo` (should return a JSON blob with
   a `version`), or just run `pcwdev.py preflight` once configured.

### 1. Prerequisites (dev PC)

- **Python 3.10+** with `requests` (`pip install requests`).
- **PuTTY** (`plink` + `pscp`) on PATH or at `C:\Program Files\PuTTY`. Used for
  all SSH/SCP — on Windows, OpenSSH password auth tends to fail against MiSTer,
  PuTTY's does not. Run `plink root@<your-mister-ip>` once to cache the host key.
- **cpmtools built WITH libdsk** — installed for you by `install_cpmtools.py`
  (see step 3). The boot image is a CPCEMU `.DSK` container, so libdsk (`-T dsk`)
  is mandatory; prebuilt Windows cpmtools (without libdsk) will *not* work.
- **tesseract** (optional) — OCR of screenshots. If absent the PNG is still saved.

### 2. Configure `config.py` for your machine

Open `config.py` and edit the top section — these are the only values that are
specific to your setup:

| Setting | What to set it to |
|---------|-------------------|
| `HOST` | Your MiSTer's IP address, e.g. `"192.168.1.50"`. |
| `SSH_USER` / `SSH_PASS` | MiSTer SSH login (stock is `root` / `1`). |
| `API_PORT` | Remote API port (default `8182`). |
| `GAMES` | Core's games folder on the SD card, e.g. `"/media/fat/games/Amstrad PCW"`. |
| `MASTER` | Full path to *your* PCW CP/M boot `.dsk` inside `GAMES`. |
| `RBF` | Core file id. For the PCW it's `"_Computer/Amstrad-PCW"` (hyphen, no `.rbf`). |

Leave the rest at their defaults to start. `CPM_FORMAT` is pinned to `cf2dd`
(720K PCW); if your boot disk is a different geometry, set it to `None` and
preflight will auto-detect and tell you what to pin (step 4).

> Notes: paths with spaces / `+` / `,` are fine — they're quoted for the remote
> shell. `WORK_REL` must stay a **bare filename** (`DEV_work.dsk`) — it's relative
> to the `.mgl`'s own folder, not `/media/fat`.

### 3. Install cpmtools (`install_cpmtools.py`)

This is the one build step. On Windows it compiles **libdsk + cpmtools
`--with-libdsk`** from source inside MSYS2 and stages a self-contained copy into
`cpmtools\bin`:

```bash
python install_cpmtools.py        # installs MSYS2 via winget if needed, then builds
```

What it does, in order: finds (or `winget`-installs) MSYS2 → `pacman`-installs a
toolchain → downloads & builds libdsk and cpmtools → stages exes + DLLs +
`diskdefs` into `cpmtools\bin` → persists `CPMTOOLS_DIR` (via `setx`) → verifies
by auto-detecting your boot disk's CP/M format.

```bash
python install_cpmtools.py --check    # re-verify an existing build (no rebuild)
python install_cpmtools.py --no-winget # fail instead of auto-installing MSYS2
```

After it finishes, **open a new shell** so `CPMTOOLS_DIR` is visible (or set it
for the current session: `set CPMTOOLS_DIR=<path>\cpmtools\bin`). If cpmtools is
already on your PATH from elsewhere, this step is optional.

> Non-Windows: install a libdsk-enabled cpmtools your platform's way
> (`brew install cpmtools` on macOS/Linux pulls in libdsk) and put `cpmcp`/`cpmls`
> on PATH, or set `CPMTOOLS_DIR`.

### 4. Preflight, then run

```bash
python pcwdev.py preflight          # checks API, SSH, master backup, format, .mgl, free space
```

Preflight backs the master disk up off-device and prints the detected CP/M
format + free space. If `config.CPM_FORMAT` is `None`, pin the printed value.
Then run a program:

```bash
python pcwdev.py run hello.bas      # inject -> boot -> auto-run -> screenshot
```

The PNG lands in `screenshots/`. Compute-heavy programs run slowly under the
interpreter — if the auto-capture lands mid-run, bump `--settle` or grab a
follow-up `python pcwdev.py shot`.

---

## Files

| File | Purpose |
|------|---------|
| `config.py` | **All settings**: host, creds, paths, RBF, CP/M format, timing, size limits. Edit here. |
| `install_cpmtools.py` + `build_cpmtools.sh` | One-shot installer: builds libdsk+cpmtools and wires up `CPMTOOLS_DIR`. |
| `diskimg.py` | cpmtools wrappers — working disk, inject/read files, `PROFILE.SUB`, format + free-space detection. |
| `device.py` | SSH/SCP transport (PuTTY) + Remote HTTP API: backup, `.mgl`, launch, status. |
| `feedback.py` | Take/fetch screenshots; optional tesseract OCR. |
| `keyboard.py` | Keystroke fallback (used only if `SUBMIT.COM` is absent for auto-run). |
| `pcwdev.py` | CLI front end: `preflight`, `run`, `launch`, `shot`. |
| `rerun_mister_test.py` | Standalone smoke test (writes `DEV.mgl` + launches the master). |
| `.claude/skills/mallard-basic/` | Mallard BASIC dialect reference skill (keywords, gotchas like "no `CLS`"). |
| `hello.bas`, `feature.bas`, `life.bas` | Example programs (basic, language features, Conway's Life). |
| `master_backup.dsk` | Off-device backup of the read-only boot disk (created by preflight). |
| `screenshots/` | Captured PNGs. |

## Usage

```bash
# Phase 0 checks: API, SSH, master backup, format detection, .mgl, free space
python pcwdev.py preflight

# Full loop: inject a local .bas, boot, run, screenshot
python pcwdev.py run hello.bas
python pcwdev.py run life.bas --settle 70    # slow program: wait longer before the shot

# Re-boot the existing DEV.mgl without rebuilding the disk
python pcwdev.py launch

# Just grab a screenshot of the current screen
python pcwdev.py shot
```

## Writing Mallard BASIC

Mallard BASIC is Locomotive's CP/M business BASIC — **not** GW/QBASIC and not the
CPC's Locomotive BASIC. Several familiar keywords are missing (notably **no
`CLS`** — clear the screen with `PRINT CHR$(27);"E";`). Before writing `.bas`,
consult the **`mallard-basic` skill** (`.claude/skills/mallard-basic/SKILL.md`)
for the real keyword set and dialect rules. `feature.bas` and `life.bas` are
working examples.

## Status

Verified working end to end against a live MiSTer: cpmtools build → inject (CRLF)
→ cold-boot → `PROFILE.SUB` auto-runs `BASIC A:PROG` → screenshot. `hello.bas`,
`feature.bas`, and `life.bas` (Conway's Life) all run on hardware.

## Notes / gotchas (full list in `CLAUDE.md`)

- Always launch via the explicit `.mgl` (`_Computer/Amstrad-PCW`). A bare `.dsk`
  boots the wrong (CPC) core.
- `.mgl` `path` is a **bare filename** relative to the `.mgl`'s folder, with
  `delay="5"`. A full path → disk doesn't mount → blank white screen.
- BASIC source must use **CRLF** line endings (handled automatically on inject).
- Cold-boot for every disk change; don't hot-swap under a running CP/M session.
- The PCW floppy controller can't format disks — build images on the PC, never
  create a blank disk on the device.
- Disk free space (~84K) and Mallard's ~31K program workspace both cap program
  size; `pcwdev run` checks the disk budget.
- Screenshots are low-res (266×200) — keep on-screen output short and
  high-contrast (see `life.bas`).
```

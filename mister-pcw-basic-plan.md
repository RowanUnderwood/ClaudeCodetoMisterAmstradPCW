# Project Plan — Drive Mallard BASIC on a MiSTer Amstrad PCW core from Claude Code

## 0. One-paragraph summary

A Claude Code instance running on the user's own computer authors Mallard BASIC
programs, gets them onto a running **MiSTer Amstrad PCW core** (at `192.168.2.56`),
runs them, and reads back the result — in an automated loop. Transport is a mix of
the **mrext "Remote" HTTP API** (port `8182`, for launching the core via a `.mgl`,
sending keystrokes, and taking screenshots) and **SSH/SCP** (for moving files onto
the SD card, since Remote has no upload endpoint). Programs are injected by writing
them into a **copy** of the CP/M boot disk image with `cpmtools`; the original disk
image is a read-only master.

---

## 1. Target environment (confirmed facts)

- **MiSTer IP:** `192.168.2.56`
- **Remote (mrext) API base:** `http://192.168.2.56:8182/api`
- **Core / system:** Amstrad PCW.
  - mrext system **ID:** `AmstradPCW`
  - **RBF (for .mgl):** `_Computer/Amstrad-PCW`  ← note the **hyphen**, not the space in the folder name
  - **Disk mount:** type `s`, index `0` = drive **A:**, index `1` = drive **B:**, delay `1`
  - Games folder on SD: `/media/fat/games/Amstrad PCW/`
- **OS on the core:** CP/M **Plus** (banner `v 2.11, 61K TPA, 2 disc drives, 112K drive M:`).
  - CP/M Plus ⇒ a `PROFILE.SUB` on the boot drive auto-runs at cold boot (needs `SUBMIT.COM`, normally present).
  - `M:` is a volatile RAM drive — not usable for outside injection. Ignore it.
- **BASIC:** Locomotive **Mallard BASIC** (Jetsam 1.47), invoked from CP/M as **`BASIC PROG`** (no extension; loads & runs `PROG.BAS`). **Confirmed working.**
- **Boot disk image (the ONLY one available):**
  `/media/fat/games/Amstrad PCW/cpm 2,11 boot PCW9512+ eng.dsk`
  (verify exact path/case; note the literal comma in `2,11`).
- **Disk image format:** standard **CPCEMU `.DSK`** container (track/sector headers),
  *not* a raw CP/M filesystem dump ⇒ `cpmtools` must be built **with libdsk**.
- **SSH:** stock MiSTer is `root` / password `1` (confirm — may have been changed).

### Hard constraints / gotchas

- **`/api/launch` on a bare `.dsk` launches the WRONG core.** Both the CPC (`Amstrad`)
  and PCW (`AmstradPCW`) systems claim `.dsk`; auto-detection picked CPC. **Always
  launch via an explicit `.mgl`** that names `_Computer/Amstrad-PCW`. (Also means
  `/api/launch/new`, which auto-detects, is unusable here — hand-write the `.mgl`.)
- **No file-upload endpoint** in Remote ⇒ use SCP for disk images and the `.mgl`.
- **The PCW floppy controller cannot format disks** ⇒ never create a blank disk on the
  device; build any disk image on the dev machine (or copy an existing one).
- **Feedback is screenshots only** — no text read-back. Use the screenshot endpoint + optional OCR.
- **Don't hot-swap a disk under a running CP/M session** (directory-cache corruption). Always cold-boot.

---

## 2. Architecture / the dev loop

```
Claude Code (user's PC)
   │ ONE-TIME: write DEV.mgl  (rbf=_Computer/Amstrad-PCW, mounts DEV_work.dsk in A:)
   │
   │ 1. generate PROG.BAS (ASCII text)
   │ 2. cpmcp PROG.BAS (+ PROFILE.SUB) into a COPY of the boot disk  ->  DEV_work.dsk
   │ 3. scp DEV_work.dsk  ->  /media/fat/games/Amstrad PCW/         (SSH)
   │ 4. POST /api/launch/menu                 (exit current core)   ┐ force a
   │ 5. POST /api/launch  { path: ".../DEV.mgl" }  (cold boot PCW)  ┘ clean boot
   │      └─ PROFILE.SUB auto-runs `BASIC PROG`   (preferred)
   │         (fallback: send `BASIC PROG` + Enter via Remote keystrokes)
   │ 6. wait for boot+run, POST /api/screenshots, GET newest PNG
   │ 7. (optional) OCR the PNG -> text the model can read
   └─ loop  (only DEV_work.dsk changes each pass; DEV.mgl is static)
```

The master boot disk image is **never written to**; `DEV_work.dsk` is a regenerated copy.

### Drive layout — two options

- **Option 1 (default): single working copy in A:.** `DEV_work.dsk` = copy of the boot
  disk + injected `PROG.BAS` + `PROFILE.SUB` running `BASIC PROG`. Fully auto-run, no
  keystrokes. Master stays safe because we only ever write to the copy.
- **Option 2: master in A: (index 0), scratch in B: (index 1).** `.mgl` mounts the
  untouched master read-only in A: and a small writable scratch disk in B:. Then run
  `BASIC B:PROG` — but `PROFILE.SUB` would have to live on A:, which we won't modify, so
  this needs the keystroke fallback to issue the run command. Use only if you want the
  master literally untouched in the boot slot.

---

## 3. Prerequisites on the dev machine

- Python 3.10+ with `requests` (`pip install requests`).
- SSH client (`ssh`, `scp`) via `subprocess`, or `paramiko`.
- **`cpmtools` built with libdsk:**
  - Debian/Ubuntu: `sudo apt install cpmtools libdsk4` (confirm libdsk `-T` support; else build `--with-libdsk`).
  - macOS: `brew install cpmtools libdsk` (or build against libdsk).
  - Verify: `cpmcp -h` shows `-T` and `dsk`/`edsk` types are available.
- Optional: `tesseract-ocr` to turn screenshots into text.

---

## 4. Phase 0 — pre-flight checks (do first, report results)

1. **API reachable:** `GET /api/sysinfo` → 200 + JSON.
2. **Baseline screenshot:** `POST /api/screenshots`, then `GET /api/screenshots`, fetch newest via `GET /api/screenshots/{core}/{filename}`, save + view.
3. **Core screenshot `setname`:** from `GET /api/games/playing` (`core`) or the screenshot list `core` field. Store it.
4. **Correct launch (THE fix):** write `DEV.mgl` (see §6) pointing at the real boot disk, then `POST /api/launch {"path":".../DEV.mgl"}`. Confirm it boots the **PCW** core to the CP/M prompt (screenshot). If it lands in the menu instead, `POST /api/launch/menu` first, then launch again.
5. **SSH/SCP test:** `ssh root@192.168.2.56 'ls -la "/media/fat/games/Amstrad PCW/"'`. Capture the exact boot-disk filename; confirm the password.
6. **BACK UP THE MASTER NOW:** `scp` the boot `.dsk` to the dev machine; keep it untouched. Everything depends on this.
7. **Characterise disk geometry:** `cpmls -f <candidate> -T dsk "master.dsk"` until it cleanly lists real files (`BASIC.COM`, `J14CPM3.EMS`, `PROFILE.SUB`, …). Start with PCW 3"/720K CP/M Plus diskdefs; if none match, read the DSK header geometry and add a `diskdefs` entry. Success = a believable file listing.
8. **Inspect existing `PROFILE.SUB`:** `cpmcp` it out of the master. Confirm `SUBMIT.COM` is present (needed for auto-run). We'll **append** our run line, not clobber existing setup.
   - (Run verb already confirmed: **`BASIC PROG`**.)
9. **Free space:** sanity-check the directory isn't full (a small `.BAS` is tiny).

> Do not automate until 1–8 pass. Report failures with the exact request/response or shell output.

---

## 5. Phase 1 — disk tooling (`diskimg.py`)

- `make_working_copy(master, work)` — copy master `.dsk` → `work`.
- `put_file(work, HOST_NAME, local_text, fmt)` —
  `cpmcp -f {fmt} -T dsk "{work}" "{local_text}" 0:{HOST_NAME}` (8.3 uppercase, e.g. `PROG.BAS`). Overwrite if present.
- `read_file(work, HOST_NAME, fmt)` — `cpmcp ... 0:{NAME} -` (read back; used for PROFILE.SUB).
- `list_dir(work, fmt)` — wraps `cpmls` (post-write sanity check).
- `ensure_profile(work, fmt, run_line="BASIC PROG")` — read existing `PROFILE.SUB`, **append** the run line (preserve existing lines), write back. If no `SUBMIT.COM`, skip and use keystroke fallback.

Notes: only ever operate on `DEV_work.dsk`; use CR/LF line endings in `.SUB`/`.BAS` text.

---

## 6. Phase 2 — the `.mgl`, transfer, and launch (`device.py`)

Constants:
```
BASE   = "http://192.168.2.56:8182/api"
GAMES  = "/media/fat/games/Amstrad PCW"
MASTER = f"{GAMES}/cpm 2,11 boot PCW9512+ eng.dsk"   # confirm exact name
WORK   = f"{GAMES}/DEV_work.dsk"
MGL    = f"{GAMES}/DEV.mgl"
RBF    = "_Computer/Amstrad-PCW"
```

`DEV.mgl` (static — points at the working copy; `path` is relative to `/media/fat`):
```xml
<mistergamedescription>
    <rbf>_Computer/Amstrad-PCW</rbf>
    <file delay="1" type="s" index="0" path="games/Amstrad PCW/DEV_work.dsk"/>
</mistergamedescription>
```
(Option 2 only: add `<file delay="1" type="s" index="1" path="games/Amstrad PCW/DEV_b.dsk"/>` for drive B:.)

Functions:
- `write_mgl()` — SSH/heredoc or scp the `DEV.mgl` above (once during setup).
- `upload(local, remote)` — `scp` (quote remote paths; they contain spaces and `+`).
- `to_menu()` — `POST /api/launch/menu`.
- `boot_mgl()` — `POST /api/launch {"path": MGL}`.
- `cold_boot()` — `to_menu()`, short sleep, `boot_mgl()`.
- `wait_until_running(timeout=30)` — poll `GET /api/games/playing` until PCW shows, then a tunable settle delay (~6–10 s for boot + PROFILE.SUB + BASIC).

Quick manual launch (also the Phase-0 test):
```bash
curl --request POST --url "http://192.168.2.56:8182/api/launch" \
  --data '{"path":"/media/fat/games/Amstrad PCW/DEV.mgl"}'
```

---

## 7. Phase 3 — run trigger

**Preferred (auto-run):** `ensure_profile()` puts `BASIC PROG` in `PROFILE.SUB` on
`DEV_work.dsk`. Cold boot ⇒ it runs automatically. No keystrokes.

**Fallback (keystrokes):** after boot, send `BASIC PROG` + Enter via
`POST /api/controls/keyboard-raw/{code}` (`-` prefix = hold Shift), one key at a time,
~40–80 ms apart. No "send string" call exists; build an ASCII→uinput map (see §9).
For Option 2, send `BASIC B:PROG` instead.

---

## 8. Phase 4 — read result + Phase 5 — loop

`feedback.py`:
- `shot()` — `POST /api/screenshots`, wait, `GET /api/screenshots`, pick newest for our `setname`, `GET /api/screenshots/{core}/{filename}`, save PNG.
- `read_screen()` — optional `tesseract` OCR (PCW text is crisp; expect light cleanup).

`pcwdev.py` (CLI):
```
python pcwdev.py run path/to/myprog.bas
  -> make_working_copy -> put_file PROG.BAS -> ensure_profile
  -> upload -> cold_boot -> wait_until_running -> shot [-> read_screen]
  -> print screenshot path (+ OCR text)
```
Flags: `--no-autorun` (keystroke run), `--settle N` (tune delay), `--drive-b` (Option 2).

---

## 9. Keyboard fallback reference (only if needed)

- `POST /api/controls/keyboard-raw/{code}`; `-` prefix = hold Shift.
- Codes are Linux uinput keycodes (`KEY_ENTER=28`, `KEY_SPACE=57`, letters/digits per the uinput table). Build the ASCII→(code, shift?) map programmatically; don't hand-type it.
- Hold/combos: WebSocket `/ws` commands `kbdRawDown:{code}` / `kbdRawUp:{code}`.
- Verify the few symbols actually sent (`:` for `B:`, space) interactively — PCW-core mapping of punctuation may differ.

---

## 10. Risks / open questions

1. Does launching the `.mgl` land in CP/M directly, or need a `menu`-then-launch bounce? (Phase 0 #4)
2. Exact boot-disk path/filename incl. the comma. (Phase 0 #5)
3. SSH credentials unchanged? (Phase 0 #5)
4. Which stock cpmtools diskdef matches, or author one from the DSK header. (Phase 0 #7)
5. Existing `PROFILE.SUB` to preserve + `SUBMIT.COM` present for auto-run? (Phase 0 #8)

## 11. Safety rules

- Master boot `.dsk` is **read-only**; back it up off-device before anything else.
- All writes go to `DEV_work.dsk` (or `DEV_b.dsk`); regenerate from master if corrupted.
- Never format a disk on the device.
- Never overwrite a mounted image in a running session without a full cold boot after.

## 12. API quick reference (endpoints used)

| Purpose | Method + path |
| --- | --- |
| Reachability / sysinfo | `GET /api/sysinfo` |
| Launch (use the .mgl path!) | `POST /api/launch` `{"path": ".../DEV.mgl"}` |
| Exit to menu | `POST /api/launch/menu` |
| What's running | `GET /api/games/playing` |
| Take screenshot | `POST /api/screenshots` |
| List screenshots | `GET /api/screenshots` |
| Fetch a screenshot | `GET /api/screenshots/{core}/{filename}` |
| Key (named) | `POST /api/controls/keyboard/{name}` |
| Key (raw uinput, `-`=shift) | `POST /api/controls/keyboard-raw/{code}` |
| Low-latency / hold keys | WebSocket `/ws`: `kbdRaw:` `kbdRawDown:` `kbdRawUp:` |

File moves (no API): `scp <local> root@192.168.2.56:"/media/fat/games/Amstrad PCW/..."`.

**PCW launch identifiers (confirmed):** system ID `AmstradPCW`, RBF `_Computer/Amstrad-PCW`, disk mount type `s`, index 0 = A: / index 1 = B:.

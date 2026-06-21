---
name: z88dk-pcw
description: Reference and gotchas for writing C (z88dk) that cross-compiles to a Z80 CP/M .COM for the Amstrad PCW (CP/M Plus), driven by the pcwdev `cc`/`runc` loop. Use whenever creating or editing .c/.asm destined for the PCW .COM path -- the toolchain has sharp edges (subtype choice, 16-bit int, binary inject). Verified end-to-end 2026-06-21 with z88dk v2.4.
---

# z88dk C for the Amstrad PCW (.COM path)

Compiles C to a native Z80 `.COM` that loads at `0x0100` and runs directly under
the PCW's **CP/M Plus** — far faster than Mallard BASIC, with a ~61K TPA ceiling
instead of Mallard's ~31K. Build with `python pcwdev.py cc prog.c` (compile only)
or `runc prog.c` (compile → inject → boot → screenshot). `ccom.py` wraps `zcc`.

## Hard rules / gotchas (the "don't crash on the PCW" part)

- **Use the GENERIC CP/M subtype, not `pcw80`.** `config.ZCC_SUBTYPE = "default"`
  (`zcc +cpm` → `-Cz.com`) makes a portable `.COM` that does console I/O through
  the BDOS — which CP/M Plus serves on the PCW. The `pcw80` subtype instead builds
  a PCW-native **disk image** (`+cpmdisk`) with the heavy `-lpcw` banked runtime
  (`REGISTER_SP=61000`); a bare `.COM` carved out of that crashes when injected and
  run as `A:PROG` (hardcoded stack above the real TPA). Generic crt0 sets its
  stack from the BDOS pointer at `0x0006`, which is CP/M-Plus-safe.
- **Inject BINARY, never as text.** A `.COM` goes in via `diskimg.put_file`
  (`runc` does this). Routing it through `put_text` (the `.bas` LF→CRLF path)
  corrupts machine code. This is the exact inverse of the `.bas` rule.
- **Run drive-qualified `A:PROG`** (no extension). `PROFILE.SUB`'s `setdef m:,*`
  makes M: the default drive, so an unqualified `PROG` wouldn't be found. Inject
  as the fixed name `PROG.COM` so the run line stays `A:PROG`.
- **`int` is 16-bit.** Use `long` (and `%ld`) for any value over 32767 — e.g.
  `1+2+...+1000 = 500500` overflows an `int`. `long` is 32-bit.
- **The "This program is for a CP/M system." text at the file start is normal** —
  it's z88dk's benign MS-DOS-detection stub; on Z80 the entry `EB 04 EB C3 ..`
  decodes to `EX DE,HL / INC B / EX DE,HL / JP <crt0>` and runs the real program.

## Console (verified on hardware)

Generic console = BDOS char output. `\n` is translated to CRLF. ANSI/VT52 escape
sequences pass through to the PCW firmware (same as Mallard's `PRINT CHR$(27)`):

- **Clear + home:** `printf("\x1B" "E" "\x1B" "H");`  (ESC E clears, ESC H homes)
- **Position cursor** (0-based row,col): `ESC Y (row+32) (col+32)`
  ```c
  static void at(int row, int col){ printf("\x1B" "Y%c%c", row+32, col+32); }
  ```
- Screenshots are still 266x200, so keep output short/distinct (same as `.bas`).

## Sizes

- Runtime ceiling: **~61K TPA** (`config.COM_TPA_BYTES`) — `ccom` rejects bigger.
- Disk: the boot disk has **~84K free** on A: (`MAX_PROG_BYTES`); `runc` also
  checks the live `diskimg.free_space()`. A trivial program is ~7K.

## Compilers & options

- `sccz80` (default, robust) vs `sdcc`/`zsdcc` (smaller/faster): `--compiler sdcc`.
- Add a `-D` define with `cc/runc --define NAME=VALUE` (repeatable). For
  randomness (cold boot is deterministic — no entropy), pass `--define PCW_SEED=<n>`
  and `srand(PCW_SEED)` in the program (mirrors the `.bas` `{{SEED}}` trick).
- Slimming pragmas exist (`#pragma output noprotectmsdos` drops the DOS stub;
  `nofileio`, `noredir`) — but **`#pragma output nostreams` removes the stdio
  stream layer and breaks `printf`**; only use it with `fputc_cons`-style output.
  For ordinary text programs, plain `#include <stdio.h>` + `printf` is fine.

## Known-good template (verified end-to-end)

```c
#include <stdio.h>

static void at(int row, int col){ printf("\x1B" "Y%c%c", row+32, col+32); }

int main(void)
{
    long sum = 0; int i;
    printf("\x1B" "E" "\x1B" "H");          /* clear + home */
    printf("HELLO FROM C\n");
    for (i = 1; i <= 1000; i++) sum += i;   /* instant compiled */
    at(2, 0); printf("SUM = %ld", sum);     /* 500500 */
    return 0;
}
```

Build/run: `python pcwdev.py runc yourprog.c` (see CLAUDE.md / README). The
verified `zcc` line `ccom` produces is:
`zcc +cpm -subtype=default -compiler=sccz80 -create-app -o PROG.COM prog.c`.

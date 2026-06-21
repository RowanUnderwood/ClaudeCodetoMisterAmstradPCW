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
- **`sccz80` (the default compiler) silently MISCOMPILES some control flow — it
  does NOT crash, it computes the WRONG ANSWER.** Two confirmed on hardware AND
  reproduced under `z88dk-ticks` (Game-of-Life bring-up, 2026-06-21):
  - **`a == X || a == Y` used as an `if`/ternary condition** comes out *inverted*.
    Conway survival `(n == 2 || n == 3) ? 1 : 0` kept a live cell with 1 neighbour
    and killed one with 2 or 3 — exactly backwards — which silently starved every
    pattern. The neighbour *count* was correct; only the boolean test was wrong.
  - **`continue` inside a nested loop** jumps to the wrong loop's increment
    (garbles/undercounts; sometimes corrupts enough to crash).
  Workarounds that DO compile correctly: replace OR-of-equalities with a **small
  lookup table** indexed by the value (e.g. `survive[9]`/`born[9]` for B3/S23,
  `cell = alive ? survive[n] : born[n]`), or a range test (`n >= 2 && n <= 3`);
  and avoid `continue` (sum all cases and subtract, or use an explicit guarded
  branch). When a port is logically correct (verify the algorithm in Python/host
  C first) yet dies/freezes on the PCW, suspect sccz80 codegen of booleans/`continue`
  before anything else. `--compiler sdcc` is the other escape hatch.
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

## Test locally under z88dk-ticks BEFORE touching hardware

`z88dk-ticks` (`$Z88DK_DIR\bin\z88dk-ticks.exe`) is a Z80/CP/M instruction
emulator that runs the produced `.COM` on the PC with BDOS console output — no
device round-trip. This is the fastest way to flush out **sccz80 codegen bugs**
(see the boolean/`continue` gotcha above): build a tiny harness with the exact
suspect routine, print results, and diff against a host (Python) reference.

```
python pcwdev.py cc harness.c          # produces PROG.COM
& "$env:Z88DK_DIR\bin\z88dk-ticks.exe" PROG.COM
```

This is how the Life `||` miscompile was isolated (2026-06-21): the emulator
reproduced the hardware's exact wrong sequence (`5 4 4 6 0`), then proved the
table-lookup fix held the glider at `5`. Caveats:
- **~1e8-cycle limit:** ticks stops and prints a big counter (e.g. `100000004`)
  if the program runs too long. Keep harness loops short (a handful of
  generations); heavy `printf` use also eats the budget — a run that printed ~8
  lines then emitted the counter had hit the wall, not finished.
- It emulates BDOS **console** I/O; don't rely on it for file I/O or the PCW's
  VT52 firmware/graphics. Test pure logic here; confirm rendering on the device.
- Can't easily run the full app if it busy-waits for input (e.g. a keypress-seed
  loop blows the cycle budget) — factor the logic into a harness instead.

## Compilers & options

- `sccz80` is the default but is NOT fully trustworthy (see the boolean/`continue`
  miscompiles above); `sdcc`/`zsdcc` (also smaller/faster) is the escape hatch:
  `--compiler sdcc`.
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

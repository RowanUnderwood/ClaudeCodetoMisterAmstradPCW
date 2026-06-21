---
name: mallard-basic
description: Reference and gotchas for writing Mallard BASIC programs for the Amstrad PCW (PCW8256/8512/9512, CP/M Plus, Locomotive Mallard BASIC / Mallard-80). Use whenever generating or editing .bas source destined for the pcwdev MiSTer PCW loop, so the dialect is correct (e.g. there is NO CLS). Source: "Mallard BASIC for Amstrad PCW8256 8512 PCW9512.txt" (Locomotive Software, 2nd ed. 1987).
---

# Mallard BASIC (Amstrad PCW) — authoring reference

Mallard BASIC is Locomotive Software's **business**-oriented CP/M BASIC (the PCW
runs the **Mallard-80** Z80 build, with the **Jetsam** keyed-file extension). It
is *not* Locomotive BASIC (the CPC ROM BASIC) and *not* GW/QBASIC — several
keywords you'd reflexively reach for do not exist. Check this file before using
any keyword you're unsure of.

## Hard rules / gotchas (this is the "don't repeat the CLS mistake" part)

- **Every line needs a line number.** Classic numbered BASIC. Use 10,20,30…
- **CRLF line endings, always.** CP/M needs `\r\n`. LF-only source "staircases"
  on screen and won't run. (The pcwdev loop injects `.bas` via `put_text`, which
  converts LF→CRLF — never inject a `.bas` with a raw byte copy.)
- **There is NO `CLS`.** Clear the screen by sending ESC E (see below). Using
  `CLS` gives "Syntax error in <line>".
- **No `LOCATE` / `PRINT AT`.** Position the cursor with ESC Y (see below).
- **No colour/graphics keywords** (`INK`, `PAPER`, `COLOR`, `PLOT`, `DRAW`,
  `LINE`). The PCW screen is monochrome; bitmap graphics are via the separate
  **GSX** library, not BASIC statements.
- **No modern control flow:** no `DO…LOOP`, no `REPEAT…UNTIL`, no `ELSEIF`, no
  `SELECT CASE`, no block `IF…END IF`. `IF`'s `THEN`/`ELSE` bodies must sit on
  the **same physical line** as the `IF`. Loops are `FOR…NEXT` and `WHILE…WEND`.
- **Run verb in this project is `BASIC A:PROG`** — drive-qualified, because
  PROFILE.SUB's `setdef m:,*` makes M: (RAM disk) the default drive. Mallard
  loads *and runs* the named program.
- Comments: both `REM` and a trailing apostrophe `'` work.
- `LET` is optional (`A=1` is fine). String concat is `+`. Relational/logical
  ops: `=`,`<>`,`<`,`>`,`<=`,`>=`, and `AND OR NOT XOR EQV IMP MOD`.

## Variable types

Suffix on the name picks the type: `%` integer (−32768…32767), `!` single,
`#` double, `$` string. No suffix → default type, which you can set per first
letter with `DEFINT / DEFSNG / DEFDBL / DEFSTR` (e.g. `DEFINT I-N`).
Arrays: `DIM a(n)`; subscripts default to max 10; `OPTION BASE 0|1` sets the
lower bound (default 0, must be set before any array use).

## Screen control (the CLS / LOCATE replacements)

The PCW screen is a VT52-ish terminal; send escape sequences with `PRINT` +
`CHR$`. ESC = `CHR$(27)`. End the `PRINT` with `;` to suppress the newline.

```basic
10 ESC$=CHR$(27)
20 PRINT ESC$;"E";          ' clear screen (ESC E)
30 PRINT ESC$;"H";          ' cursor home, top-left (ESC H)
40 PRINT ESC$;"Y";CHR$(15+32);CHR$(22+32);  ' cursor to row 15, col 22 (ESC Y r+32 c+32)
50 PRINT "Hello"
```

(Note `ESC E` clears but leaves the cursor where it was — follow with `ESC H`.)

## Keyword reference (grouped — Chapter 5 of the manual)

- **Program creation/editing:** AUTO, DELETE, EDIT, LIST, LLIST, NEW, RENUM,
  SAVE  (SAVE forms: ASCII / Compressed / Protected)
- **Load & run:** CLEAR, CHAIN, CHAIN MERGE, COMMON, COMMON RESET, HIMEM,
  LOAD, MEMORY, MERGE, RUN
- **Termination:** END, SYSTEM  (END→Direct Mode; SYSTEM→exit to CP/M)
- **Misc:** OPTION RUN, OPTION STOP, VERSION
- **Control structures:** FOR…NEXT (with STEP, incl. negative), WHILE…WEND,
  IF…THEN…ELSE (single line), GOTO, GOSUB…RETURN (global vars; recursion OK),
  ON x GOTO, ON x GOSUB
- **Console I/O:** INKEY$, INPUT, INPUT$, LINE INPUT, POS, PRINT, WIDTH, WRITE,
  ZONE, TAB, SPC, plus OPTION PRINT/INPUT/TAB/NOT TAB
- **Printer:** LPRINT, LLIST, LPOS, WIDTH LPRINT, OPTION LPRINT
- **Constant data:** DATA, READ, RESTORE
- **Arithmetic fns:** ABS, ATN, COS, EXP, FIX, INT, LOG, LOG10, MAX, MIN,
  RANDOMIZE, RND, ROUND, SGN, SIN, SQR, TAN  (angles in radians)
- **String fns:** LEFT$, RIGHT$, MID$ (assignable), INSTR, LEN, LOWER$, UPPER$,
  STRIP$, STRING$, SPACE$, STR$, DEC$, HEX$, OCT$, VAL
- **Type conversion:** ASC, CHR$, CDBL, CINT, CSNG, UNT
- **Files (seq/random):** OPEN, CLOSE, RESET, EOF, LOC, LOF, GET, PUT, FIELD,
  LSET, RSET, INPUT #, LINE INPUT #, PRINT #, WRITE #, and CVI/CVS/CVD…/MKI$/
  MKS$/MKD$… record-field conversions
- **Directory:** DIR, FILES, DEL, ERA, KILL, NAME, REN, FIND$, OPTION FILES
- **File inspection:** DISPLAY, TYPE
- **Machine level:** CALL, USR, DEF USR, DEF SEG (ignored on Mallard-80),
  PEEK, POKE, INP, INPW, OUT, OUTW, WAIT, WAITW
- **Error trapping:** ON ERROR GOTO, RESUME, RESUME 0, ON ERROR GOTO 0, ERROR,
  ERL, ERR, OSERR
- **Dev/debug:** CONT, STOP, TRON, TROFF, FRE, VARPTR
- **Jetsam keyed files (DB):** ADDKEY, ADDREC, CREATE, DELKEY, FETCHKEY$,
  FETCHRANK, FETCHREC, LOCK, RANKSPEC, SEEKKEY/NEXT/PREV/RANK/REC/SET,
  CVIK/CVUK/MKIK$/MKUK$, CONSOLIDATE, BUFFERS

## Full reserved-word list (Appendix IV — cannot be variable names)

ABS, ADDKEY, ADDREC, ALL, AND, AS, ASC, ATN, AUTO, BASE, BUFFERS, CALL, CD,
CDBL, CHAIN, CHDIR, CHDIR$, CHR$, CINT, CLEAR, CLOSE, COMMON, CONSOLIDATE, CONT,
COS, CREATE, CSNG, CVD, CVI, CVIK, CVS, CVUK, DATA, DEC$, DEF, DEFDBL, DEFINT,
DEF SEG, DEFSNG, DEFSTR, DEL, DELETE, DELKEY, DIM, DIR, DISPLAY, EDIT, ELSE, END,
EOF, EQV, ERA, ERASE, ERL, ERR, ERROR, EXP, FETCHKEY$, FETCHRANK, FETCHREC,
FIELD, FILES, FIND$, FINDDIR$, FIX, FN, FOR, FRE, GET, GOSUB, GOTO, HEX$, HIMEM,
IF, IMP, INKEY$, INP, INPUT, INPUT #, INPUT$, INPW, INSTR, INT, KILL, LEFT$, LEN,
LET, LINE, LIST, LLIST, LOAD, LOC, LOCK, LOF, LOG, LOG10, LOWER$, LPOS, LPRINT,
LSET, MAX, MD, MEMORY, MERGE, MID$, MIN, MKD$, MKDIR, MKI$, MKIK$, MKS$, MKUK$,
MOD, NAME, NEXT, NEW, NOT, OCT$, ON, ON ERROR GOTO 0, OPEN, OPTION, OR, OSERR,
OUT, OUTW, PEEK, POKE, POS, PRINT, PRINT #, PUT, RANDOMIZE, RANKSPEC, RD, READ,
REM, REN, RENUM, RESET, RESTORE, RESUME, RESUME 0, RETURN, RIGHT$, RMDIR, RND,
ROUND, RSET, RUN, SAVE, SEEKKEY, SEEKNEXT, SEEKPREV, SEEKRANK, SEEKREC, SEEKSET,
SGN, SIN, SPACE$, SPC, SQR, STEP, STOP, STR$, STRING$, STRIP$, SWAP, SYSTEM, TAB,
TAN, THEN, TO, TROFF, TRON, TYPE, UNT, UPPER$, USING, USR, VAL, VARPTR, VERSION,
WAIT, WAITW, WEND, WHILE, WIDTH, WRITE, WRITE #, XOR, ZONE

(`CLS`, `LOCATE`, `COLOR`, `INK`, `PAPER`, `PLOT`, `DRAW`, `DO`, `LOOP`,
`REPEAT`, `UNTIL`, `ELSEIF`, `SELECT`/`CASE` are **absent** — by design.)

## Formatted output: PRINT USING / DEC$

`PRINT USING` applies a format template to numbers/strings (e.g.
`PRINT USING "###.##"; x`). `DEC$(n, "template")` returns the formatted string.
`WRITE` outputs comma-separated, quoting strings (handy for files re-read by
`INPUT`).

## Known-good template (verified end-to-end on the device)

```basic
10 PRINT "MALLARD-OK-1234"
20 PRINT "SUM=";2+2
30 FOR I=1 TO 3
40 PRINT "LINE ";I
50 NEXT I
60 PRINT "DONE"
70 END
```

Test it with: `python pcwdev.py run yourprog.bas` (see CLAUDE.md). Keep on-screen
output short and distinctive — the MiSTer screenshot is only 266×200, so long
90-column lines are hard to read back.

## Size limits

- **On disk:** A: has only ~84K free (`config.MAX_PROG_BYTES` = 80K; `pcwdev`
  rejects larger sources). Source `.bas` files are normally a few KB, so this
  rarely bites.
- **In BASIC:** Mallard's workspace is ~31K (the "free bytes" shown at its
  banner) — the real ceiling for a *runnable* program. A program can fit on disk
  yet be too large for BASIC to LOAD/RUN. Keep programs well under ~30K.

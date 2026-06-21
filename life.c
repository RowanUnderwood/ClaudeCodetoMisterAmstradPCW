/* life.c -- Conway's Game of Life for the Amstrad PCW (.COM path, z88dk)
 *
 * 39x14 toroidal grid, VT52 screen control, double-width [] /    cells.
 * Native Z80 .COM under CP/M Plus.
 *
 * Rendering: one buffered console write per frame (BDOS function 2 over an
 * exact byte count -- NOT '$'-terminated func 9, whose terminator collides with
 * VT52 ESC Y coordinates), and only the cells that CHANGED are redrawn.
 *
 * Speed (all measured under z88dk-ticks, 2026-06-21):
 *   - compute_next hoists per-row pointers and uses precomputed column-wrap
 *     tables, so a neighbour read is a pointer+index load -- no per-access *39
 *     multiply. ~6x faster than the naive A[rr][cc] form.
 *   - swap is a single memcpy (Z80 LDIR), ~free vs the old 2D-indexed copy.
 *   - live count is accumulated inside compute_next (free), not a separate scan.
 *   - NO per-frame delay: the demo runs flat out (compute time is the pacing).
 *   - the Conway rule is a TABLE lookup, never `(n==2||n==3)` -- sccz80
 *     miscompiles that OR-of-equalities (it inverted survival and killed every
 *     pattern). See the z88dk-pcw skill.
 *
 * Patterns cycle forever: spaceships (glider, LWSS, loafer), oscillators
 * (queen bee shuttle, pulsar, pentadecathlon) and methuselahs (acorn,
 * R-pentomino, Gosper glider gun). Per-pattern generation counts.
 */

#include <stdio.h>
#include <string.h>

#pragma output noprotectmsdos   /* drop the benign MS-DOS stub (~128 bytes) */

/* Diagnostic knobs (only used when compiled with --define LIFE_DEBUG=1).
   Override per build, e.g. --define DEBUG_PAT=1 --define DEBUG_GENS=20. */
#ifndef DEBUG_PAT
#define DEBUG_PAT   0           /* pattern index to trace (0 = GLIDER) */
#endif
#ifndef DEBUG_GENS
#define DEBUG_GENS  16          /* generations to log before exiting */
#endif

/* ----- grid constants ------------------------------------------------------- */
#define GW     39               /* grid columns */
#define GH     14               /* grid rows   */

/* ----- pattern library ------------------------------------------------------ */

struct pattern {
    const char        *name;
    int                base_row, base_col;
    int                count;           /* number of living cells */
    int                gens;            /* generations to run before cycling */
    const signed char (*cells)[2];      /* count x {row_off, col_off} pairs */
};

static const signed char glider_cells[][2] = {
    {0,1}, {1,2}, {2,0}, {2,1}, {2,2}};

static const signed char lwss_cells[][2] = {
    {0,1}, {0,4}, {1,0}, {2,0}, {2,4}, {3,0}, {3,1}, {3,2}, {3,3}};

/* Loafer -- c/7 orthogonal spaceship (Josh Ball, 2013), 9x9, 20 cells */
static const signed char loafer_cells[][2] = {
    {0,1},{0,2},{0,5},{0,7},{0,8},
    {1,0},{1,3},{1,6},{1,7},
    {2,1},{2,3},
    {3,2},
    {4,8},
    {5,6},{5,7},{5,8},
    {6,5},
    {7,6},
    {8,7},{8,8}};

/* Queen bee shuttle -- period-30 oscillator (queen bee bouncing between two
   stabilising blocks), 22x7, 20 cells */
static const signed char queenbee_cells[][2] = {
    {0,9},
    {1,7},{1,9},
    {2,6},{2,8},{2,20},{2,21},
    {3,0},{3,1},{3,5},{3,8},{3,20},{3,21},
    {4,0},{4,1},{4,6},{4,8},
    {5,7},{5,9},
    {6,9}};

/* Pulsar -- period-3 oscillator, 13x13, very showy */
static const signed char pulsar_cells[][2] = {
    {0,2},{0,3},{0,4},{0,8},{0,9},{0,10},
    {2,0},{2,5},{2,7},{2,12},
    {3,0},{3,5},{3,7},{3,12},
    {4,0},{4,5},{4,7},{4,12},
    {5,2},{5,3},{5,4},{5,8},{5,9},{5,10},
    {7,2},{7,3},{7,4},{7,8},{7,9},{7,10},
    {8,0},{8,5},{8,7},{8,12},
    {9,0},{9,5},{9,7},{9,12},
    {10,0},{10,5},{10,7},{10,12},
    {12,2},{12,3},{12,4},{12,8},{12,9},{12,10}};

/* Pentadecathlon -- period-15 oscillator, 3x10 */
static const signed char pentadeca_cells[][2] = {
    {0,2},{0,7},
    {1,0},{1,1},{1,3},{1,4},{1,5},{1,6},{1,8},{1,9},
    {2,2},{2,7}};

/* Acorn -- methuselah, 7x3, 7 cells (fills the torus with chaos) */
static const signed char acorn_cells[][2] = {
    {0,1}, {1,3}, {2,0},{2,1},{2,4},{2,5},{2,6}};

static const signed char rpento_cells[][2] = {
    {0,1}, {0,2}, {1,0}, {1,1}, {2,1}};

static const signed char gosper_cells[][2] = {
    {4,0}, {5,0}, {4,1}, {5,1},                       /* left block      */
    {4,10}, {5,10}, {6,10}, {3,11}, {7,11},            /* main body       */
    {2,12}, {8,12}, {2,13}, {8,13},
    {5,14},
    {3,15}, {7,15}, {4,16}, {5,16}, {6,16}, {5,17},
    {2,20}, {3,20}, {4,20}, {2,21}, {3,21}, {4,21},
    {1,22}, {5,22},
    {0,24}, {1,24}, {5,24}, {6,24},
    {2,34}, {3,34}, {2,35}, {3,35}                     /* distant block   */
};

static const struct pattern patterns[] = {
    /* name             row col  cnt gens  cells           */
    {"GLIDER",            1,  1,   5,  32, glider_cells},
    {"LOAFER",            3, 15,  20,  35, loafer_cells},
    {"LWSS",             5,  2,   9,  28, lwss_cells},
    {"QUEEN BEE",         3,  8,  20,  45, queenbee_cells},
    {"PULSAR",            0, 13,  48,  18, pulsar_cells},
    {"PENTADECATHLON",    6, 14,  12,  30, pentadeca_cells},
    {"ACORN",             6, 16,   7,  60, acorn_cells},
    {"R-PENTOMINO",       6, 18,   5,  40, rpento_cells},
    {"GOSPER GUN",        2,  1,  36,  34, gosper_cells},
};
#define NP (sizeof(patterns) / sizeof(patterns[0]))

/* ----- grids ---------------------------------------------------------------- */
static char A[GH][GW];   /* current (displayed) generation */
static char B[GH][GW];   /* next generation                */
static int  g_live;      /* live-cell count of the most recent compute (B)     */

/* B3/S23 as lookup tables, indexed by neighbour count (0..8).
   These REPLACE `(n==2 || n==3)`: sccz80 miscompiles that OR-of-equalities as a
   condition (it inverted survival and silently killed every pattern). */
static const char born[9]    = {0,0,0,1,0,0,0,0,0};  /* dead -> alive iff n==3      */
static const char survive[9] = {0,0,1,1,0,0,0,0,0};  /* live stays iff n==2 or n==3 */

/* Precomputed column wrap: left/right neighbour column for each c (no per-cell
   branch or modulo in the hot loop). Row wrap is cheap (done GH times/gen). */
static int lfc[GW], rtc[GW];
static void initwrap(void)
{
    int i;
    for (i = 0; i < GW; i++) {
        lfc[i] = i - 1; if (lfc[i] < 0)   lfc[i] = GW - 1;
        rtc[i] = i + 1; if (rtc[i] >= GW) rtc[i] = 0;
    }
}

/* ----- frame buffer + single-call BDOS output -------------------------------
   Worst case (every GH*GW=546 cell changes): 546*(4-byte ESC Y + 2-byte glyph)
   = 3276 + status < 4096. NOT static: the inline-asm emitter references `_fb`. */
unsigned char fb[4096];
static int    fblen;

static void buf_char(int ch) { fb[fblen++] = (unsigned char)ch; }
static void buf_str(const char *s) { while (*s) fb[fblen++] = (unsigned char)*s++; }

static void buf_int(int v)
{
    char tmp[8];
    int  i = 0;
    if (v == 0) { fb[fblen++] = '0'; return; }
    while (v > 0) { tmp[i++] = (char)('0' + (v % 10)); v /= 10; }
    while (i > 0) fb[fblen++] = (unsigned char)tmp[--i];
}

static void buf_at(int row, int col)
{
    fb[fblen++] = 0x1B;
    fb[fblen++] = 'Y';
    fb[fblen++] = (unsigned char)(row + 32);
    fb[fblen++] = (unsigned char)(col + 32);
}

/* Emit exactly `fblen` bytes via BDOS function 2 in a tight asm loop. (Func 9
   is '$'-terminated and 4+32=='$', so a cursor at row/col 4 would truncate it.)
   BDOS clobbers registers, so we push/pop our pointer (HL) and counter (BC). */
static void put_buf(void)
{
    #asm
    ld      hl,_fb
    ld      bc,(_fblen)
.pb_loop
    ld      a,b
    or      c
    jr      z,pb_done
    push    hl
    push    bc
    ld      e,(hl)
    ld      c,2
    call    0005h
    pop     bc
    pop     hl
    inc     hl
    dec     bc
    jr      pb_loop
.pb_done
    #endasm
    fblen = 0;
}

/* ----- VT52 helpers (printf path, used only off the hot path) --------------- */
static void at(int row, int col)
{
    printf("\x1B" "Y%c%c", row + 32, col + 32);
}
static void cls(void)
{
    printf("\x1B" "E" "\x1B" "H");   /* ESC E clears+homes, ESC H homes */
}

/* ----- diagnostics ---------------------------------------------------------- */
static int grid_live(char g[GH][GW])
{
    int r, c, n = 0;
    for (r = 0; r < GH; r++)
        for (c = 0; c < GW; c++)
            if (g[r][c]) n++;
    return n;
}
static long grid_chk(char g[GH][GW])   /* position-weighted, for LIFE.LOG */
{
    int  r, c;
    long s = 0;
    for (r = 0; r < GH; r++)
        for (c = 0; c < GW; c++)
            if (g[r][c]) s += (long)(r * GW + c + 1);
    return s;
}

/* ----- status line into the buffer ------------------------------------------ */
static void buf_status(int gen, const char *name, int live)
{
    buf_at(GH, 0);
    buf_str("GEN ");   buf_int(gen);
    buf_str(" PAT:");  buf_str(name);
    buf_str(" LIVE:"); buf_int(live);
    buf_str("        ");          /* pad to clear any wider previous line */
}

/* ----- seed one pattern onto the grid (toroidal) ---------------------------- */
static void seed_grid(int pat_idx)
{
    int i, r, c;
    const struct pattern *p = &patterns[pat_idx];

    for (r = 0; r < GH; r++)
        for (c = 0; c < GW; c++)
            A[r][c] = 0;

    for (i = 0; i < p->count; i++) {
        r = p->base_row + p->cells[i][0];
        c = p->base_col + p->cells[i][1];
        if (r >= GH) r -= GH;
        if (c >= GW) c -= GW;
        A[r][c] = 1;
    }
}

/* ----- draw the WHOLE grid (one buffered BDOS call) -- first frame ----------- */
static void full_render(int pat_idx)
{
    int   r, c;
    char *arow;

    fblen = 0;
    for (r = 0; r < GH; r++) {
        arow = A[r];
        buf_at(r, 0);
        for (c = 0; c < GW; c++) {
            if (arow[c]) { buf_char('['); buf_char(']'); }
            else         { buf_char(' '); buf_char(' '); }
        }
    }
    buf_status(0, patterns[pat_idx].name, grid_live(A));
    put_buf();
}

/* ----- draw ONLY the changed cells A->B (one buffered BDOS call) ------------ */
static void diff_render(int gen, int pat_idx)
{
    int   r, c;
    char *arow, *brow;

    fblen = 0;
    for (r = 0; r < GH; r++) {
        arow = A[r];
        brow = B[r];
        for (c = 0; c < GW; c++) {
            if (arow[c] != brow[c]) {
                buf_at(r, c * 2);
                if (brow[c]) { buf_char('['); buf_char(']'); }
                else         { buf_char(' '); buf_char(' '); }
            }
        }
    }
    buf_status(gen, patterns[pat_idx].name, g_live);
    put_buf();
}

/* ----- compute one generation (Conway B3/S23, toroidal) into B -------------
   Hot loop: per-row pointers (up/mid/dn) computed GH times, NOT per cell, so
   neighbour reads are pointer+index loads with no *GW multiply. Column wrap via
   the lfc[]/rtc[] tables. Rule via born[]/survive[] tables. Live count free. */
static void compute_next(void)
{
    int   r, c, ru, rd, n, l, rt, lv;
    char *up, *mid, *dn, *brow;

    lv = 0;
    for (r = 0; r < GH; r++) {
        ru = r - 1; if (ru < 0)   ru = GH - 1;
        rd = r + 1; if (rd >= GH) rd = 0;
        up = A[ru]; mid = A[r]; dn = A[rd]; brow = B[r];
        for (c = 0; c < GW; c++) {
            l = lfc[c]; rt = rtc[c];
            n = up[l] + up[c] + up[rt]
              + mid[l]        + mid[rt]
              + dn[l] + dn[c] + dn[rt];
            n = mid[c] ? survive[n] : born[n];   /* table rule (no `||`) */
            brow[c] = (char)n;
            lv += n;
        }
    }
    g_live = lv;
}

/* ----- copy B back into A (Z80 LDIR, ~free) -------------------------------- */
static void swap_grids(void)
{
    memcpy(A, B, (unsigned)(GH * GW));
}

/* ===== main ================================================================ */
int main(void)
{
    int  pat_idx, gen;
    long cycle;
    const struct pattern *p;

    initwrap();
    cls();
    printf("CONWAY'S GAME OF LIFE\n\n  %d patterns, cycling forever\n", (int)NP);

#ifdef LIFE_DEBUG
    /* DIAGNOSTIC build (--define LIFE_DEBUG=1): log one pattern's LIVE/CHK to
       LIFE.LOG, close it, exit to a prompt so you can `TYPE LIFE.LOG`. */
    {
        FILE *lf;
        int   g;
        lf = fopen("LIFE.LOG", "w");
        seed_grid(DEBUG_PAT);
        cls();
        full_render(DEBUG_PAT);
        if (lf) {
            fprintf(lf, "PAT %s\r\n", patterns[DEBUG_PAT].name);
            fprintf(lf, "G 0 LIVE %d CHK %ld\r\n", grid_live(A), grid_chk(A));
        }
        for (g = 1; g <= DEBUG_GENS; g++) {
            compute_next();
            diff_render(g, DEBUG_PAT);
            swap_grids();
            if (lf) fprintf(lf, "G %d LIVE %d CHK %ld\r\n", g, g_live, grid_chk(A));
        }
        if (lf) fclose(lf);
        at(GH + 3, 0);
        printf("DEBUG DONE -- type:  TYPE LIFE.LOG");
        return 0;
    }
#endif

    /* ----- endless pattern cycle, flat out (no artificial pauses) ----------- */
    for (cycle = 0; ; cycle++) {

        pat_idx = (int)(cycle % NP);
        p = &patterns[pat_idx];

        seed_grid(pat_idx);
        cls();
        full_render(pat_idx);

        for (gen = 1; gen <= p->gens; gen++) {
            compute_next();
            diff_render(gen, pat_idx);
            swap_grids();
        }
    }

    return 0;
}

/* life.c -- Conway's Game of Life for the Amstrad PCW (.COM path, z88dk)
 *
 * 39x14 toroidal grid, VT52 screen control, double-width [] /    cells.
 * Runs as a CP/M .COM at native Z80 speed.
 *
 * Rendering: the old version issued ~546 printf() calls per frame (one per
 * cell) through the BDOS console -- that, not the simulation, was the ~3s/frame
 * bottleneck (the program is I/O-bound, not CPU-bound; overclocking barely
 * helped).  This version:
 *   - builds each frame into a single buffer and emits it with ONE BDOS call
 *     (function 9, print-string), bypassing printf's heavy format engine, and
 *   - only redraws the cells that CHANGED between generations (differential
 *     update), so a typical frame is a few dozen bytes instead of ~1.1 KB.
 * Net effect: tiny per-frame output, smooth per-cell motion, no flicker, no
 * full-screen clear each frame.
 *
 * Features:
 *   - Press Enter to start -- the timing of your keypress seeds the RNG
 *   - Cycles through a library of patterns (still-lifes, oscillators, and
 *     spaceships incl. a Gosper glider gun), looping forever
 *   - Per-pattern generation counts: movers get more gens to read as motion;
 *     static still-lifes don't linger
 */

#include <stdio.h>
#include <stdlib.h>

#pragma output noprotectmsdos   /* drop the benign MS-DOS stub (~128 bytes) */

/* ----- CP/M BDOS console status (function 11) --------------------------------
   C_STAT: returns 0 if no key waiting, 0xFF if a character is ready.
   Consistent across CP/M 2.2 and CP/M Plus (the PCW runs CP/M Plus).
   Used to poll the keyboard without blocking for the timing seed. */

static int kbhit(void)
{
    #asm
    ld      c,11
    call    0005h
    ld      l,a
    ld      h,0
    #endasm
}

/* Busy-loop iteration at the BANNER — user presses Enter (or timeout auto-starts
   after ~10 s for unattended PROFILE.SUB runs).  Returns the counter as entropy. */

static long wait_for_start(void)
{
    long counter = 1;
    int c;

    printf("PRESS ENTER TO START (or wait ~10s)\n");
    printf("  longer wait = more random seed\n");

    for (;;) {
        counter++;
        /* Poll keyboard every ~256 iterations (~a few ms on 4 MHz Z80) */
        if ((counter & 0xff) == 0) {
            if (kbhit()) {
                /* A key is waiting — read and discard it, then break */
                c = getchar();
                /* Drain any additional buffered characters */
                while (kbhit()) { c = getchar(); }
                (void)c;
                break;
            }
        }
        /* Timeout: auto-start after ~500k iterations (~8-10 s on 4 MHz Z80)
           so unattended PROFILE.SUB runs don't hang forever. */
        if (counter > 500000L)
            break;
    }
    return counter;
}

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

static const signed char block_cells[][2] = {
    {0,0}, {0,1}, {1,0}, {1,1}};

static const signed char beehive_cells[][2] = {
    {0,1}, {0,2}, {1,0}, {1,3}, {2,1}, {2,2}};

static const signed char blinker_cells[][2] = {
    {0,0}, {0,1}, {0,2}};

static const signed char toad_cells[][2] = {
    {0,1}, {0,2}, {0,3}, {1,0}, {1,1}, {1,2}};

static const signed char glider_cells[][2] = {
    {0,1}, {1,2}, {2,0}, {2,1}, {2,2}};

static const signed char lwss_cells[][2] = {
    {0,1}, {0,4}, {1,0}, {2,0}, {2,4}, {3,0}, {3,1}, {3,2}, {3,3}};

static const signed char rpento_cells[][2] = {
    {0,1}, {0,2}, {1,0}, {1,1}, {2,1}};

/* Pulsar -- period-3 oscillator, 13x13, very showy (lots of cells flipping) */
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

/* Pentadecathlon -- period-15 oscillator, 3x10, pulses dramatically */
static const signed char pentadeca_cells[][2] = {
    {0,2},{0,7},
    {1,0},{1,1},{1,3},{1,4},{1,5},{1,6},{1,8},{1,9},
    {2,2},{2,7}};

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
    /* name           row col  cnt gens  cells           */
    {"GLIDER",          1,  1,   5,  32, glider_cells},
    {"LWSS",            5,  2,   9,  28, lwss_cells},
    {"PULSAR",          0, 13,  48,  18, pulsar_cells},
    {"PENTADECATHLON",  6, 14,  12,  30, pentadeca_cells},
    {"R-PENTOMINO",     6, 18,   5,  40, rpento_cells},
    {"GOSPER GUN",      2,  1,  36,  34, gosper_cells},
    {"TOAD",            6, 18,   6,  14, toad_cells},
    {"BLINKER",         7, 18,   3,  12, blinker_cells},
    {"BEEHIVE",         6, 18,   6,   6, beehive_cells},
    {"BLOCK",           6, 18,   4,   6, block_cells},
};
#define NP (sizeof(patterns) / sizeof(patterns[0]))

/* ----- grids ---------------------------------------------------------------- */
static char A[GH][GW];   /* current (displayed) generation */
static char B[GH][GW];   /* next generation                */

/* ----- frame buffer + single-call BDOS output -------------------------------
   Worst case (every one of GH*GW=546 cells changes): 546 * (4-byte ESC Y +
   2-byte glyph) = 3276 bytes, plus the status line -> < 4096.  NOT static:
   the inline-asm emitter references the public label `_fb`. */
unsigned char fb[4096];
static int    fblen;

static void buf_char(int ch) { fb[fblen++] = (unsigned char)ch; }

static void buf_str(const char *s) { while (*s) fb[fblen++] = (unsigned char)*s++; }

/* append a non-negative decimal integer */
static void buf_int(int v)
{
    char tmp[8];
    int  i = 0;
    if (v == 0) { fb[fblen++] = '0'; return; }
    while (v > 0) { tmp[i++] = (char)('0' + (v % 10)); v /= 10; }
    while (i > 0) fb[fblen++] = (unsigned char)tmp[--i];
}

/* VT52 cursor position into the buffer (0-based row,col) */
static void buf_at(int row, int col)
{
    fb[fblen++] = 0x1B;
    fb[fblen++] = 'Y';
    fb[fblen++] = (unsigned char)(row + 32);
    fb[fblen++] = (unsigned char)(col + 32);
}

/* '$'-terminate and hand the whole buffer to BDOS function 9 in ONE call.
   Our glyphs ("[]"/"  ") and VT52 escapes contain no '$', so func 9 is safe;
   escapes pass through to the PCW firmware exactly as printf's did. */
static void put_buf(void)
{
    fb[fblen] = '$';
    #asm
    ld      c,9
    ld      de,_fb
    call    0005h
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
    /* PCW VT52: ESC E clears screen AND homes cursor; ESC H homes (belt+braces) */
    printf("\x1B" "E" "\x1B" "H");
}

/* ----- append the status line into the buffer ------------------------------ */
static void buf_status(int gen, const char *name, long seed)
{
    buf_at(GH, 0);
    buf_str("GEN ");
    buf_int(gen);
    buf_str("  PAT: ");
    buf_str(name);
    buf_str("  SEED: ");
    buf_int((int)(seed & 0x7fff));
    buf_str("      ");          /* pad to clear any wider previous line */
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
        /* toroidal wrap (offsets are non-negative in the data, but safe) */
        if (r >= GH) r -= GH;
        if (c >= GW) c -= GW;
        A[r][c] = 1;
    }
}

/* ----- draw the WHOLE grid (one buffered BDOS call) -- first frame of a pattern */
static void full_render(int pat_idx, long seed)
{
    int r, c;

    fblen = 0;
    for (r = 0; r < GH; r++) {
        buf_at(r, 0);
        for (c = 0; c < GW; c++) {
            if (A[r][c]) { buf_char('['); buf_char(']'); }
            else         { buf_char(' '); buf_char(' '); }
        }
    }
    buf_status(0, patterns[pat_idx].name, seed);
    put_buf();
}

/* ----- draw ONLY the changed cells A->B (one buffered BDOS call) ------------ */
static void diff_render(int gen, int pat_idx, long seed)
{
    int r, c;

    fblen = 0;
    for (r = 0; r < GH; r++) {
        for (c = 0; c < GW; c++) {
            if (A[r][c] != B[r][c]) {
                buf_at(r, c * 2);
                if (B[r][c]) { buf_char('['); buf_char(']'); }
                else         { buf_char(' '); buf_char(' '); }
            }
        }
    }
    buf_status(gen, patterns[pat_idx].name, seed);
    put_buf();
}

/* ----- compute one generation (Conway B3/S23, toroidal) into B ------------- */
static void compute_next(void)
{
    int r, c, dr, dc, n, rr, cc;

    for (r = 0; r < GH; r++) {
        for (c = 0; c < GW; c++) {
            /* count live neighbours in the 3x3 Moore neighbourhood */
            n = 0;
            for (dr = -1; dr <= 1; dr++) {
                rr = r + dr;
                if      (rr <  0)  rr += GH;
                else if (rr >= GH) rr -= GH;
                for (dc = -1; dc <= 1; dc++) {
                    if (dr == 0 && dc == 0) continue;
                    cc = c + dc;
                    if      (cc <  0)  cc += GW;
                    else if (cc >= GW) cc -= GW;
                    n += A[rr][cc];
                }
            }
            /* Conway rules (B3/S23) */
            if (A[r][c])
                B[r][c] = (n == 2 || n == 3) ? 1 : 0;
            else
                B[r][c] = (n == 3) ? 1 : 0;
        }
    }
}

/* ----- copy B back into A --------------------------------------------------- */
static void swap_grids(void)
{
    int r, c;
    for (r = 0; r < GH; r++)
        for (c = 0; c < GW; c++)
            A[r][c] = B[r][c];
}

/* ----- delay loop (busy-wait) -- now the deliberate frame-rate control ------- */
static void pause(void)
{
    volatile long w;
    for (w = 0; w < 15000L; w++) { /* ~0.3 s @ 4 MHz (rough) */ }
}

/* ===== main ================================================================ */
int main(void)
{
    const struct pattern *p;
    int  pat_idx, gen;
    long counter;
    long seed;
    long cycle;

    /* ----- splash screen + timing-based seed ------------------------------- */
    cls();
    printf("CONWAY'S GAME OF LIFE\n\n");
    printf("  39x14 toroidal grid\n");
    printf("  %d patterns, cycling forever\n\n", (int)NP);

    /* Wait for Enter (or auto-timeout after ~10 s). The counter is our entropy. */
    counter = wait_for_start();

    /* Mix the counter into a 15-bit seed (srand is 16-bit). XOR-fold so both
       short and long waits vary the result. */
    seed = (counter ^ (counter >> 16)) & 0x7fff;
    if (seed == 0) seed = 1;
    srand((unsigned int)seed);

    /* ----- endless pattern cycle ------------------------------------------- */
    for (cycle = 0; ; cycle++) {

        pat_idx = (int)(cycle % NP);
        p = &patterns[pat_idx];

        /* Seed the grid and draw the first frame in full */
        seed_grid(pat_idx);
        cls();
        full_render(pat_idx, seed);
        pause();

        /* Run this pattern's generations -- differential updates only */
        for (gen = 1; gen <= p->gens; gen++) {
            compute_next();
            diff_render(gen, pat_idx, seed);
            swap_grids();
            pause();
        }

        /* Completion message + short countdown (off the hot path -> printf ok) */
        at(GH + 1, 0);
        printf("-- %d gens -- %s (%d/%d) -- next in: ",
               p->gens, p->name, pat_idx + 1, (int)NP);
        {
            int n;
            for (n = 3; n > 0; n--) {
                printf("%d ", n);
                pause();
            }
        }
    }

    return 0;
}

/* hello.c -- smoke test for the PCW .COM cross-compile path (z88dk).
 * Compiled to a generic CP/M PROG.COM (BDOS console I/O), injected binary,
 * run as A:PROG. ESC E / ESC H clear+home the PCW screen so the distinctive
 * markers are easy to read in the low-res screenshot. */
#include <stdio.h>

int main(void)
{
    printf("\x1B" "E" "\x1B" "H");   /* clear screen, cursor home (PCW/VT52) */
    printf("CCOM-OK-1234\n");
    printf("SUM=%d\n", 2 + 2);
    printf("PCW-C-WORKS\n");
    return 0;
}

/* feature.c -- exercises the PCW .COM path: BDOS console, ESC screen control,
 * 32-bit math, and a compute loop that would crawl in Mallard BASIC but is
 * instant compiled. Deterministic results so they're easy to verify:
 *   SUM 1..1000 = 500500   PRIMES<=200 = 46
 * NOTE: z88dk int is 16-bit -- use long (%ld) for values over 32767. */
#include <stdio.h>

static void at(int row, int col)        /* VT52 ESC Y r+32 c+32 (0-based) */
{
    printf("\x1B" "Y%c%c", row + 32, col + 32);
}

int main(void)
{
    long sum = 0;
    int i, n, d, primes = 0, isprime;

    printf("\x1B" "E" "\x1B" "H");       /* clear + home */
    printf("CCOM FEATURE TEST");

    for (i = 1; i <= 1000; i++)
        sum += i;

    for (n = 2; n <= 200; n++) {
        isprime = 1;
        for (d = 2; d * d <= n; d++)
            if (n % d == 0) { isprime = 0; break; }
        primes += isprime;
    }

    at(2, 0); printf("SUM 1..1000 = %ld", sum);
    at(3, 0); printf("PRIMES <=200 = %d", primes);
    at(5, 0); printf("CFEAT-DONE-99");
    return 0;
}

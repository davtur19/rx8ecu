/* test_obd_service_handler_63834.c
 *
 * Host C companion for obd_service_handler_63834 (0x63834).
 *
 * Mode-1 status read over the 21-entry DTC context table
 * (base 0xFFFF87D8, 16-byte stride, code word @+0, type byte @+6), all in
 * page 0xFFFF8000 (mapped MAP_FIXED; 0xFFFF87D8 + 21*16 == 0xFFFF8928):
 *
 *   cur = word@0xFFFF8928 & 0xFFFF
 *   for i in 0..20:
 *       p = 0xFFFF87D8 + i*16
 *       if word@p == (r4 & 0xFFFF) and i != cur: return s8(p[6])
 *   return 0
 */

#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

extern int32_t obd_service_handler_63834(uint32_t r4);

#define BASE   0xFFFF87D8u
#define CUR    0xFFFF8928u
#define COUNT  21u

static void map_page(uintptr_t addr)
{
    long page = sysconf(_SC_PAGESIZE);
    uintptr_t base = addr & ~((uintptr_t)page - 1);
    void *p = mmap((void *)base, (size_t)page, PROT_READ | PROT_WRITE,
                   MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED, -1, 0);
    if (p == MAP_FAILED) { perror("mmap"); exit(1); }
}

static void seed_row(uint16_t idx, uint16_t code, uint8_t t6)
{
    uint8_t *p = (uint8_t *)(BASE + (uint32_t)idx * 16);
    *(volatile uint16_t *)p = code;
    p[6] = t6;
}

static int check(uint32_t r4, uint16_t cur,
                 const uint16_t *codes, const uint8_t *types, unsigned nrows)
{
    *(volatile uint16_t *)CUR = cur;
    for (unsigned i = 0; i < COUNT; i++)
        if (i < nrows) seed_row(i, codes[i], types[i]);
        else seed_row(i, 0xFFFF, 0);          /* non-matching filler */

    int32_t exp = 0;
    for (unsigned i = 0; i < COUNT; i++) {
        if (i < nrows && codes[i] == (uint16_t)(r4 & 0xFFFFu)
            && i != (cur & 0xFFFFu)) {
            exp = (int8_t)types[i];
            break;
        }
    }

    int32_t got = obd_service_handler_63834(r4);
    if (got != exp) {
        printf("FAIL: r4=%04X cur=%04X -> %d expected %d\n", r4, cur, got, exp);
        return 1;
    }
    return 0;
}

int main(void)
{
    unsigned failures = 0, tests = 0;
    map_page(0xFFFF8000);
    printf("=== obd_service_handler_63834 ===\n");

    /* Targeted: 1-row tables, match/skip/retype corners. */
    for (uint16_t row = 0; row < COUNT; row++) {
        static const uint8_t types[] = {0x00, 0x01, 0x7F, 0x80, 0xFF};
        for (size_t t = 0; t < sizeof(types); t++) {
            uint16_t codes[COUNT] = {0};
            uint8_t ty[COUNT] = {0};
            codes[row] = 0x1234; ty[row] = types[t];
            tests++;
            failures += check(0x1234, row, codes, ty, 1);          /* skip  */
            tests++;
            failures += check(0x1234, (row + 1) % COUNT, codes, ty, 1); /* hit */
            tests++;
            failures += check(0x9999, row, codes, ty, 1);          /* miss */
        }
    }

    /* Random. */
    srand(0x63834);
    for (int i = 0; i < 20000; i++) {
        uint16_t codes[COUNT];
        uint8_t ty[COUNT];
        unsigned nrows = rand() % 7;
        for (unsigned r = 0; r < nrows; r++) {
            codes[r] = (uint16_t)rand();
            ty[r] = (uint8_t)rand();
        }
        tests++;
        failures += check((uint32_t)rand(), (uint16_t)rand(), codes, ty, nrows);
    }

    printf("Results: %u tests, %u failures\n", tests, failures);
    return failures ? 1 : 0;
}

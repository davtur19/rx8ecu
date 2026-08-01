/* test_obd_service_handler_63B46.c
 *
 * Host C companion for obd_service_handler_63B46 (0x63B46).
 *
 * Debounce-state writer: row = word@0xFFFF8928 & 0xFFFF; p = 0xFFFF87D8 +
 * row*16; p[0x0E] = (s8(p[0x0E]) + s8(p[0x0D]) - r4) & 0xFF; p[0x0D] = r4&0xFF.
 * All cells in page 0xFFFF8000 (mapped MAP_FIXED).  Rows tested are 0..0x14
 * so p stays inside the page (0xFFFF87D8 + 0x14*16 + 0x0E == 0xFFFF8926).
 */

#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

extern uint32_t obd_service_handler_63B46(uint32_t r4);

#define BASE 0xFFFF87D8u
#define CUR  0xFFFF8928u

static void map_page(uintptr_t addr)
{
    long page = sysconf(_SC_PAGESIZE);
    uintptr_t base = addr & ~((uintptr_t)page - 1);
    void *p = mmap((void *)base, (size_t)page, PROT_READ | PROT_WRITE,
                   MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED, -1, 0);
    if (p == MAP_FAILED) { perror("mmap"); exit(1); }
}

static int check(uint32_t r4, uint16_t idx, uint8_t b0d, uint8_t b0e)
{
    uint8_t *p = (uint8_t *)(BASE + (uint32_t)(idx & 0xFFFF) * 16);
    *(volatile uint16_t *)CUR = idx;
    p[0x0D] = b0d;
    p[0x0E] = b0e;

    uint8_t e0e = (uint8_t)((int32_t)(int8_t)b0e + (int32_t)(int8_t)b0d
                            - (int32_t)r4);
    uint8_t e0d = (uint8_t)r4;

    uint32_t got_r = obd_service_handler_63B46(r4);

    if (got_r != (r4 & 0xFFFFFFFFu) || p[0x0D] != e0d || p[0x0E] != e0e) {
        printf("FAIL: r4=%08X idx=%u (b0d,b0e)=(%02X,%02X) -> ret=%08X "
               "(%02X,%02X) expected ret=%08X (%02X,%02X)\n",
               r4, idx, b0d, b0e, got_r, p[0x0D], p[0x0E],
               r4 & 0xFFFFFFFFu, e0d, e0e);
        return 1;
    }
    return 0;
}

int main(void)
{
    unsigned failures = 0, tests = 0;
    map_page(0xFFFF8000);
    printf("=== obd_service_handler_63B46 ===\n");

    static const uint8_t vals[] = {0x00, 0x01, 0x7F, 0x80, 0xFE, 0xFF};
    for (uint16_t idx = 0; idx < 0x15; idx++)
        for (size_t a = 0; a < sizeof(vals); a++)
            for (size_t b = 0; b < sizeof(vals); b++)
                for (size_t c = 0; c < sizeof(vals); c++) {
                    tests++;
                    failures += check(vals[a], idx, vals[b], vals[c]);
                }

    srand(0x63B46);
    for (int i = 0; i < 20000; i++) {
        tests++;
        failures += check((uint32_t)rand(), (uint16_t)(rand() & 0x14),
                          (uint8_t)rand(), (uint8_t)rand());
    }

    printf("Results: %u tests, %u failures\n", tests, failures);
    return failures ? 1 : 0;
}

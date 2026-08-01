/* test_obd_dtc_row_update_0x64490.c
 *
 * Host C companion for obd_dtc_row_update_0x64490 (0x64490).
 *
 * Row index word at 0xFFFF8D74 and table base 0xFFFF8930 both live in page
 * 0xFFFF8000 (mapped MAP_FIXED).  Rows tested are 0..4 so p stays inside
 * the page.
 *
 * Reference: delta = (s16(w) + (w>>8)) - (r4 + (r4>>8));
 *            b32 = (s8(b32) + delta) & 0xFF; w = r4 & 0xFFFF.
 */

#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

extern void obd_dtc_row_update_0x64490(uint32_t r4);

#define ROW_ADDR 0xFFFF8D74u
#define BASE     0xFFFF8930u
#define STRIDE   0x34u

static void map_page(uintptr_t addr)
{
    long page = sysconf(_SC_PAGESIZE);
    uintptr_t base = addr & ~((uintptr_t)page - 1);
    void *p = mmap((void *)base, (size_t)page, PROT_READ | PROT_WRITE,
                   MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED, -1, 0);
    if (p == MAP_FAILED) {
        perror("mmap");
        exit(1);
    }
}

static int check(uint32_t r4, uint16_t row, uint8_t b32, uint16_t w)
{
    uint8_t *p = (uint8_t *)(BASE + (uint32_t)row * STRIDE);
    *(volatile uint16_t *)ROW_ADDR = row;
    p[0x32] = b32;
    *(volatile uint16_t *)(p + 0x02) = w;

    int32_t delta = (int32_t)(int16_t)w + (int32_t)((w >> 8) & 0xFF)
                    - (int32_t)r4 - (int32_t)((r4 & 0xFFFF) >> 8);
    uint8_t e32 = (uint8_t)((int32_t)(int8_t)b32 + delta);
    uint16_t ew = (uint16_t)r4;

    obd_dtc_row_update_0x64490(r4);

    if (p[0x32] != e32 || *(volatile uint16_t *)(p + 0x02) != ew) {
        printf("FAIL: r4=%04X row=%u (b32,w)=(%02X,%04X) -> (%02X,%04X) "
               "expected (%02X,%04X)\n",
               r4, row, b32, w, p[0x32], *(volatile uint16_t *)(p + 0x02), e32, ew);
        return 1;
    }
    return 0;
}

int main(void)
{
    unsigned failures = 0, tests = 0;

    map_page(0xFFFF8000);

    printf("=== obd_dtc_row_update_0x64490 ===\n");

    static const uint8_t v8[] = {0x00, 0x01, 0x7E, 0x7F, 0x80, 0x81, 0xFE, 0xFF};
    static const uint16_t v16[] = {0x0000, 0x0001, 0x00FF, 0x0100,
                                   0x7FFF, 0x8000, 0x8001, 0xFFFF};
    for (uint16_t row = 0; row < 5; row++)
        for (size_t a = 0; a < sizeof(v16) / sizeof(v16[0]); a++)
            for (size_t b = 0; b < sizeof(v8) / sizeof(v8[0]); b++)
                for (size_t c = 0; c < sizeof(v16) / sizeof(v16[0]); c++) {
                    tests++;
                    failures += check(v16[a], row, v8[b], v16[c]);
                }

    srand(42);
    for (int i = 0; i < 20000; i++) {
        tests++;
        failures += check((uint32_t)(rand() & 0xFFFF), (uint16_t)(rand() & 0x4),
                          (uint8_t)rand(), (uint16_t)(rand() & 0xFFFF));
    }

    printf("Results: %u tests, %u failures\n", tests, failures);
    return failures ? 1 : 0;
}

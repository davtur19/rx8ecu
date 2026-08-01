/* test_obd_dtc_row_update_0x64418.c
 *
 * Host C companion for obd_dtc_row_update_0x64418 (0x64418).
 *
 * Row index word at 0xFFFF8D74 and table base 0xFFFF8930 both live in page
 * 0xFFFF8000 (mapped MAP_FIXED).  Rows tested are 0..4 so p stays inside
 * the page.
 *
 * Reference: b32 = (s8(b32) + s8(b08) - r4) & 0xFF; b08 = r4 & 0xFF.
 */

#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

extern void obd_dtc_row_update_0x64418(uint32_t r4);

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

static int check(uint32_t r4, uint16_t row, uint8_t b32, uint8_t b08)
{
    uint8_t *p = (uint8_t *)(BASE + (uint32_t)row * STRIDE);
    *(volatile uint16_t *)ROW_ADDR = row;
    p[0x32] = b32; p[0x08] = b08;

    uint8_t e32 = (uint8_t)((int32_t)(int8_t)b32 + (int32_t)(int8_t)b08 - (int32_t)r4);
    uint8_t e08 = (uint8_t)r4;

    obd_dtc_row_update_0x64418(r4);

    if (p[0x32] != e32 || p[0x08] != e08) {
        printf("FAIL: r4=%02X row=%u (b32,b08)=(%02X,%02X) -> (%02X,%02X) "
               "expected (%02X,%02X)\n",
               r4, row, b32, b08, p[0x32], p[0x08], e32, e08);
        return 1;
    }
    return 0;
}

int main(void)
{
    unsigned failures = 0, tests = 0;

    map_page(0xFFFF8000);

    printf("=== obd_dtc_row_update_0x64418 ===\n");

    static const uint8_t vals[] = {0x00, 0x01, 0x7E, 0x7F, 0x80, 0x81, 0xFE, 0xFF};
    for (uint16_t row = 0; row < 5; row++)
        for (size_t a = 0; a < sizeof(vals); a++)
            for (size_t b = 0; b < sizeof(vals); b++)
                for (size_t c = 0; c < sizeof(vals); c++) {
                    tests++;
                    failures += check(vals[a], row, vals[b], vals[c]);
                }

    srand(42);
    for (int i = 0; i < 20000; i++) {
        tests++;
        failures += check((uint32_t)(rand() & 0xFF), (uint16_t)(rand() & 0x4),
                          (uint8_t)rand(), (uint8_t)rand());
    }

    printf("Results: %u tests, %u failures\n", tests, failures);
    return failures ? 1 : 0;
}

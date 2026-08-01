/* test_obd_dtc_row_update_0x64258.c
 *
 * Host C companion for obd_dtc_row_update_0x64258 (0x64258).
 *
 * The lift updates the active DTC-table row: row index word at 0xFFFF8D74,
 * table base 0xFFFF8930, stride 0x34.  Both SFRs live in page 0xFFFF8000,
 * mapped MAP_FIXED.  Rows tested are 0..3 so p stays inside the page.
 *
 * Reference: byte32 = (byte32 + byte07 + 0xFF) & 0xFF; byte07 = 1;
 *            byte32 = (byte32 + byte08 + 0xF9) & 0xFF; byte08 = 7.
 */

#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

extern void obd_dtc_row_update_0x64258(void);

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

static void set_row(uint16_t row)
{
    *(volatile uint16_t *)ROW_ADDR = row;
}

static int check(uint16_t row, uint8_t b32, uint8_t b07, uint8_t b08)
{
    uint8_t *p = (uint8_t *)(BASE + (uint32_t)row * STRIDE);
    set_row(row);
    p[0x32] = b32; p[0x07] = b07; p[0x08] = b08;

    uint8_t e32 = (uint8_t)((b32 + b07 + 0xFF) & 0xFF);
    e32 = (uint8_t)((e32 + b08 + 0xF9) & 0xFF);

    obd_dtc_row_update_0x64258();

    if (p[0x32] != e32 || p[0x07] != 1 || p[0x08] != 7) {
        printf("FAIL: row=%u (b32,b07,b08)=(%02X,%02X,%02X) -> (%02X,%02X,%02X) "
               "expected (%02X,01,07)\n",
               row, b32, b07, b08, p[0x32], p[0x07], p[0x08], e32);
        return 1;
    }
    return 0;
}

int main(void)
{
    unsigned failures = 0, tests = 0;

    map_page(0xFFFF8000);

    printf("=== obd_dtc_row_update_0x64258 ===\n");

    static const uint8_t vals[] = {0x00, 0x01, 0x06, 0x07, 0x08, 0x7F, 0x80, 0xFF};
    for (uint16_t row = 0; row < 4; row++)
        for (size_t a = 0; a < sizeof(vals); a++)
            for (size_t b = 0; b < sizeof(vals); b++)
                for (size_t c = 0; c < sizeof(vals); c++) {
                    tests++;
                    failures += check(row, vals[a], vals[b], vals[c]);
                }

    srand(42);
    for (int i = 0; i < 20000; i++) {
        uint16_t row = (uint16_t)(rand() & 0x4);   /* keep p in the mapped page */
        tests++;
        failures += check(row, (uint8_t)rand(), (uint8_t)rand(), (uint8_t)rand());
    }

    printf("Results: %u tests, %u failures\n", tests, failures);
    return failures ? 1 : 0;
}

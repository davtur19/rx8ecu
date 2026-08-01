/* test_idx_table_helpers_68780.c
 *
 * Host C companion for the idx_table helper family (0x68780 family).
 *
 * Table base 0xFFFFD998 spans pages 0xFFFFD000..0xFFFFF000 for indices
 * 0..8 (the non-wrapping range; 9+ wrap to low 32-bit addresses that are
 * below mmap_min_addr on this host and are pinned in the emulator test).
 *
 * Reference (model in idx_table_helpers_68780.c):
 *   clear: w0=w2=w4=0
 *   step:  w0 = (w4 >= 0x0464) ? 0 : w4+1
 *   dec:   w4 = (w0 == 0) ? 0x0464 : w0-1
 */

#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

extern void idx_table_clear_68780(uint32_t r4);
extern void idx_table_step_6879C(uint32_t r4);
extern void idx_table_step2_687C8(uint32_t r4);
extern void idx_table_dec_687F4(uint32_t r4);

#define BASE   0xFFFFD998u
#define STRIDE 0x46Cu
#define THRESH 0x0464u

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

static uint8_t *paddr(uint32_t r4)
{
    return (uint8_t *)(BASE + (uint32_t)(r4 & 0xFF) * STRIDE);
}

static uint16_t rd16(uint8_t *p) { return *(volatile uint16_t *)p; }

static int check(uint32_t idx, uint16_t w0, uint16_t w2, uint16_t w4)
{
    uint8_t *p = paddr(idx);
    uint16_t gw[3];
    int bad = 0;

    *(volatile uint16_t *)p = w0;
    *(volatile uint16_t *)(p + 2) = w2;
    *(volatile uint16_t *)(p + 4) = w4;
    idx_table_clear_68780(idx);
    gw[0] = rd16(p); gw[1] = rd16(p + 2); gw[2] = rd16(p + 4);
    if (gw[0] || gw[1] || gw[2]) {
        printf("FAIL clear idx=%u -> %04X,%04X,%04X\n", idx, gw[0], gw[1], gw[2]);
        bad = 1;
    }

    *(volatile uint16_t *)(p + 4) = w4;
    idx_table_step_6879C(idx);
    gw[0] = rd16(p);
    if (gw[0] != ((w4 >= THRESH) ? 0 : (uint16_t)(w4 + 1))) {
        printf("FAIL step idx=%u w4=%04X -> %04X\n", idx, w4, gw[0]);
        bad = 1;
    }

    *(volatile uint16_t *)(p + 4) = w4;
    idx_table_step2_687C8(idx);
    gw[0] = rd16(p);
    if (gw[0] != ((w4 >= THRESH) ? 0 : (uint16_t)(w4 + 1))) {
        printf("FAIL step2 idx=%u w4=%04X -> %04X\n", idx, w4, gw[0]);
        bad = 1;
    }

    *(volatile uint16_t *)p = w0;
    idx_table_dec_687F4(idx);
    gw[2] = rd16(p + 4);
    if (gw[2] != ((w0 == 0) ? THRESH : (uint16_t)(w0 - 1))) {
        printf("FAIL dec idx=%u w0=%04X -> %04X\n", idx, w0, gw[2]);
        bad = 1;
    }

    return bad;
}

int main(void)
{
    unsigned failures = 0, tests = 0;

    map_page(0xFFFFD000);
    map_page(0xFFFFE000);
    map_page(0xFFFFF000);

    printf("=== idx_table_helpers_68780 ===\n");

    static const uint16_t edges[] = {0x0000, 0x0001, 0x0463, 0x0464, 0x0465,
                                     0x0466, 0x7FFF, 0x8000, 0xFFFE, 0xFFFF};
    for (uint32_t idx = 0; idx <= 8; idx++)
        for (size_t i = 0; i < sizeof(edges) / sizeof(edges[0]); i++) {
            tests++;
            failures += check(idx, edges[i], 0x5555, edges[(i + 3) % 10]);
        }

    srand(42);
    for (int i = 0; i < 20000; i++) {
        tests++;
        failures += check((uint32_t)(rand() % 9), (uint16_t)rand(),
                          (uint16_t)rand(), (uint16_t)rand());
    }

    printf("Results: %u tests, %u failures\n", tests, failures);
    return failures ? 1 : 0;
}

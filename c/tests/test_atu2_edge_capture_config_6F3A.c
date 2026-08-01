/* test_atu2_edge_capture_config_6F3A.c
 *
 * Host C companion for atu2_edge_capture_config_6F3A (0x6F3A).
 *
 * The lift does byte RMWs on 7 SFRs (0xFFFFF818, 0xFFFFF838, 0xFFFFF819,
 * 0xFFFFF76E, 0xFFFFF839, 0xFFFFF72E, 0xFFFF9F27).  All live in two pages
 * (0xFFFFC000..0xFFFFCFFF and 0xFFFFF000..0xFFFFFFFF), mapped MAP_FIXED.
 *
 * Reference: see lift header — r4==0 → [F818]=0x0B [F838]=0x4B, else
 * 0x0A/0x4A; RMW masks (init & 0xDF & 0xAF) | 0x80 for F819/F839,
 * (init & 0x7F) | 0x80 for F76E/F72E, [FFFF9F27] = 0x01.
 */

#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

extern void atu2_edge_capture_config_6F3A(uint32_t r4);

static uint8_t *p818, *p838, *p819, *p76E, *p839, *p72E, *p9F27;

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

static void set_all(uint8_t v)
{
    *p818 = v; *p838 = v; *p819 = v; *p76E = v; *p839 = v; *p72E = v; *p9F27 = v;
}

static int check(uint32_t r4, uint8_t init)
{
    uint8_t e818 = (r4 == 0) ? 0x0B : 0x0A;
    uint8_t e838 = (r4 == 0) ? 0x4B : 0x4A;
    uint8_t e919 = (init & 0xDF & 0xAF) | 0x80;
    uint8_t e76E = (init & 0x7F) | 0x80;
    uint8_t e839 = (init & 0xDF & 0xAF) | 0x80;
    uint8_t e72E = (init & 0x7F) | 0x80;

    set_all(init);
    atu2_edge_capture_config_6F3A(r4);

    if (*p818 != e818 || *p838 != e838 || *p819 != e919 || *p76E != e76E ||
        *p839 != e839 || *p72E != e72E || *p9F27 != 0x01) {
        printf("FAIL: r4=0x%X init=0x%02X -> 818=%02X(exp %02X) 838=%02X(exp %02X) "
               "919=%02X(exp %02X) 76E=%02X(exp %02X) 839=%02X(exp %02X) "
               "72E=%02X(exp %02X) 9F27=%02X(exp 01)\n",
               r4, init, *p818, e818, *p838, e838, *p819, e919, *p76E, e76E,
               *p839, e839, *p72E, e72E, *p9F27);
        return 1;
    }
    return 0;
}

int main(void)
{
    unsigned failures = 0, tests = 0;

    map_page(0xFFFFF000);  /* covers F818/F838/F819/F76E/F839/F72E */
    map_page(0xFFFF9000);  /* covers 0xFFFF9F27 */

    p818 = (uint8_t *)0xFFFFF818;
    p838 = (uint8_t *)0xFFFFF838;
    p819 = (uint8_t *)0xFFFFF819;
    p76E = (uint8_t *)0xFFFFF76E;
    p839 = (uint8_t *)0xFFFFF839;
    p72E = (uint8_t *)0xFFFFF72E;
    p9F27 = (uint8_t *)0xFFFF9F27;

    printf("=== atu2_edge_capture_config_6F3A ===\n");

    /* Exhaustive over r4 in {0,1} x all 256 initial byte values. */
    for (uint32_t r4 = 0; r4 <= 1; r4++) {
        for (unsigned init = 0; init < 256; init++) {
            tests++;
            failures += check(r4, (uint8_t)init);
        }
    }

    printf("Results: %u tests, %u failures\n", tests, failures);
    return failures ? 1 : 0;
}

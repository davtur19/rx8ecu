/* test_flag_setter_49ED0.c
 *
 * Host C companion for flag_setter_49ED0 (0x49ED0).
 *
 * The lift reads a 16-bit word at 0xFFFFF76C, tests bit 0x100 and writes
 * a 0/1 flag byte to both 0xFFFFCD48 and 0xFFFFCD49, returning the flag.
 * On the host those addresses are not mapped, so map their pages with
 * mmap(MAP_FIXED) and back them with plain bytes (same trick as
 * test_calc_manifold_pressure_error_clamp_10A5C.c).
 *
 * Reference: v = (word & 0x0100) ? 1 : 0; [0xFFFFCD48] = v; [0xFFFFCD49] = v.
 *
 * The word is stored big-endian-style ({hi,lo} bytes) so the numeric value
 * matches the emulator's mov.w read.
 */

#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

extern uint32_t flag_setter_49ED0(void);

#define IN_WORD 0xFFFFF76Cu   /* input word address  */
#define OUT_A   0xFFFFCD48u   /* output byte A       */
#define OUT_B   0xFFFFCD49u   /* output byte B       */

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

static void set_word(uint16_t w)
{
    /* native store: the lift reads back exactly `w` on the LE host.
     * (The emulator test seeds {w>>8, w&0xFF} big-endian bytes and its
     * mov.w read yields the same numeric value — semantics match.) */
    *(volatile uint16_t *)IN_WORD = w;
}

int main(void)
{
    unsigned failures = 0, tests = 0;

    map_page(IN_WORD);
    map_page(OUT_A);   /* OUT_A and OUT_B share one page */

    printf("=== flag_setter_49ED0 ===\n");

    const uint16_t edge[] = {0x0000, 0x0001, 0x00FF, 0x0100, 0x0101, 0x01FF,
                             0x02FF, 0x8000, 0x80FF, 0xFFFF, 0x7F00, 0xFEFF,
                             0xFF00, 0xFF01};
    for (size_t i = 0; i < sizeof(edge) / sizeof(edge[0]); i++) {
        set_word(edge[i]);
        uint32_t got = flag_setter_49ED0();
        uint8_t exp = (edge[i] & 0x0100) ? 1 : 0;
        tests++;
        if (got != exp ||
            *(volatile uint8_t *)OUT_A != exp ||
            *(volatile uint8_t *)OUT_B != exp) {
            printf("FAIL: word=0x%04X got r=0x%X outA=0x%02X outB=0x%02X exp=0x%02X\n",
                   edge[i], got, *(volatile uint8_t *)OUT_A,
                   *(volatile uint8_t *)OUT_B, exp);
            failures++;
        }
    }

    srand(42);
    for (int i = 0; i < 20000; i++) {
        uint16_t w = (uint16_t)(rand() & 0xFFFF);
        set_word(w);
        uint32_t got = flag_setter_49ED0();
        uint8_t exp = (w & 0x0100) ? 1 : 0;
        tests++;
        if (got != exp ||
            *(volatile uint8_t *)OUT_A != exp ||
            *(volatile uint8_t *)OUT_B != exp) {
            printf("FAIL: word=0x%04X got r=0x%X outA=0x%02X outB=0x%02X exp=0x%02X\n",
                   w, got, *(volatile uint8_t *)OUT_A,
                   *(volatile uint8_t *)OUT_B, exp);
            failures++;
            break;
        }
    }

    printf("Results: %u tests, %u failures\n", tests, failures);
    return failures ? 1 : 0;
}

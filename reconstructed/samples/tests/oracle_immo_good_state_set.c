/* ============================================================================
 * oracle_immo_good_state_set.c  —  host test rig for
 *                                       rx8_immo_good_state_set @0x36544
 * ============================================================================
 * Compile together with samples/src/rx8_immo_good_state_set.c and pipe test
 * vectors on stdin; one vector per line, whitespace-separated hex tokens:
 *
 *     immo <c240> <c2f2> <c29f> <c282> <c284> <c28c> <c28d> <c29a> <f754>
 *                                       -> <c240> <c2f2> <c29f> <c282>
 *                                          <c284> <c28c> <c28d> <c29a> <f754>
 *
 * The nine tokens are the INITIAL values of the nine side-effected on-chip RAM
 * locations (the function is a void leaf whose writes are fixed constants, so
 * each vector is a fresh initial RAM state; the lamp register 0xFFFFF754 is a
 * read-modify-write and therefore must start from the given value).  The oracle
 * seeds the mmap()ed pages, runs the reconstructed C and prints the nine FINAL
 * values.  It contains NO copy of the function logic — that lives solely in
 * the reconstructed source under test.
 *
 * Mapping: all nine addresses live in the 0xFFFFC000 and 0xFFFFF000 pages,
 * both above this host's mmap_min_addr (0x10000), so MAP_FIXED works exactly
 * as in tests/host_oracle.c.
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

/* 0x36544 — immobilizer good-state latch (see rx8_immo_good_state_set.c).
 * Declared here rather than in rx8_samples.h (off-limits for this task). */
void rx8_immo_good_state_set(void);

#define A_C240   0xFFFFC240u   /* u8  CAN TX flag            (mov.w sign-ext) */
#define A_C2F2   0xFFFFC2F2u   /* u8  E2[0x1E] working copy                 */
#define A_C29F   0xFFFFC29Fu   /* u8  seed machine active                   */
#define A_C282   0xFFFFC282u   /* u16 good-state timer                      */
#define A_C284   0xFFFFC284u   /* u16 good-state timeout counter            */
#define A_C28C   0xFFFFC28Cu   /* u8  reserved result slot                  */
#define A_C28D   0xFFFFC28Du   /* u8  result code 3 (good)                  */
#define A_C29A   0xFFFFC29Au   /* u8  good-state flag                       */
#define A_F754   0xFFFFF754u   /* u16 immo lamp register (setImmoLight(1))  */

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

int main(void)
{
    char line[256];

    map_page(0xFFFFC000u);   /* covers 0xFFFFC240..0xFFFFC2F2 */
    map_page(0xFFFFF000u);   /* covers 0xFFFFF754               */

    while (fgets(line, sizeof line, stdin)) {
        unsigned long c240, c2f2, c29f, c282, c284, c28c, c28d, c29a, f754;

        if (sscanf(line, "immo %lx %lx %lx %lx %lx %lx %lx %lx %lx",
                   &c240, &c2f2, &c29f, &c282, &c284,
                   &c28c, &c28d, &c29a, &f754) == 9) {
            *(volatile uint8_t  *)(uintptr_t)A_C240 = (uint8_t)c240;
            *(volatile uint8_t  *)(uintptr_t)A_C2F2 = (uint8_t)c2f2;
            *(volatile uint8_t  *)(uintptr_t)A_C29F = (uint8_t)c29f;
            *(volatile uint16_t *)(uintptr_t)A_C282 = (uint16_t)c282;
            *(volatile uint16_t *)(uintptr_t)A_C284 = (uint16_t)c284;
            *(volatile uint8_t  *)(uintptr_t)A_C28C = (uint8_t)c28c;
            *(volatile uint8_t  *)(uintptr_t)A_C28D = (uint8_t)c28d;
            *(volatile uint8_t  *)(uintptr_t)A_C29A = (uint8_t)c29a;
            *(volatile uint16_t *)(uintptr_t)A_F754 = (uint16_t)f754;

            rx8_immo_good_state_set();

            printf("%02X %02X %02X %04X %04X %02X %02X %02X %04X\n",
                   *(volatile uint8_t  *)(uintptr_t)A_C240,
                   *(volatile uint8_t  *)(uintptr_t)A_C2F2,
                   *(volatile uint8_t  *)(uintptr_t)A_C29F,
                   *(volatile uint16_t *)(uintptr_t)A_C282,
                   *(volatile uint16_t *)(uintptr_t)A_C284,
                   *(volatile uint8_t  *)(uintptr_t)A_C28C,
                   *(volatile uint8_t  *)(uintptr_t)A_C28D,
                   *(volatile uint8_t  *)(uintptr_t)A_C29A,
                   *(volatile uint16_t *)(uintptr_t)A_F754);
        } else {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
    }
    return 0;
}

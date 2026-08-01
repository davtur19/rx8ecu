/* ============================================================================
 * oracle_rev_limit_fuel_cut_init.c  —  host test rig for
 *                                      rx8_rev_limit_fuel_cut_init @0xF0FC
 * ============================================================================
 * Compile together with src/rx8_rev_limit_fuel_cut_init.c (see
 * harness_rev_limit_fuel_cut_init.py) and pipe test vectors on stdin; one
 * vector per line, eight space-separated hex bytes:
 *
 *     rlim <flag> <a4a3> <a4a4> <a4a5> <a4a6> <a4a7> <a4a8> <a4a9>
 *          -> <a4a3'> <a4a4'> <a4a5'> <a4a6'> <a4a7'> <a4a8'> <a4a9'>
 *
 * <flag> is the pre-state of the rev-limit enable byte at 0xFFFF9F8C;
 * <a4a4>/<a4a5>/<a4a8>/<a4a9> are the pre-states of the counter cells
 * (cell C is a 16-bit word at 0xFFFFA4A8..0xFFFFA4A9); <a4a3>, <a4a6>,
 * <a4a7> are sentinel bytes that must survive the call untouched — they pin
 * the store count, while <a4a9> proves the third store is a WORD (a non-zero
 * a4a9 must be cleared when the flag is set: the ROM's `mov.w r4,@r3`).
 *
 * The oracle re-implements the caller-side setup only: it mmap()s the pages
 * backing the flag byte and the counter cells (same trick as host_oracle.c)
 * and prints the bytes after the call.  It contains NO copy of the function
 * logic — that lives solely in the reconstructed source under test.
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

#include "rx8_samples.h"

/* Prototype is NOT in rx8_samples.h (sample project convention: only the
 * verified "public" leaves are listed there); declared here for the rig. */
void rx8_rev_limit_fuel_cut_init(void);

#define FLAG_ADDR  0xFFFF9F8Cu   /* rev-limit enable flag (u8)    */
#define A4A3_ADDR  0xFFFFA4A3u   /* sentinel: left of cell A      */
#define CNT_A_ADDR 0xFFFFA4A4u   /* counter cell A (u8)           */
#define CNT_B_ADDR 0xFFFFA4A5u   /* counter cell B (u8)           */
#define A4A6_ADDR  0xFFFFA4A6u   /* sentinel: between cell B and C*/
#define A4A7_ADDR  0xFFFFA4A7u   /* sentinel: between cell B and C*/
#define ACC_ADDR   0xFFFFA4A8u   /* counter cell C (u16, low byte) */
#define A4A9_ADDR  0xFFFFA4A9u   /* counter cell C (u16, hi byte)  */

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
    /* Page 0xFFFF9000..0xFFFF9FFF backs the flag; page 0xFFFFA000..
     * 0xFFFFAFFF backs the counter cells + sentinels. */
    map_page(FLAG_ADDR);
    map_page(CNT_A_ADDR);

    char line[256];
    while (fgets(line, sizeof line, stdin)) {
        unsigned long f, a, b, c, d, e, g, h;
        if (sscanf(line, "rlim %lx %lx %lx %lx %lx %lx %lx %lx",
                   &f, &a, &b, &c, &d, &e, &g, &h) == 8) {
            *(volatile uint8_t *)(uintptr_t)FLAG_ADDR  = (uint8_t)f;
            *(volatile uint8_t *)(uintptr_t)A4A3_ADDR  = (uint8_t)a;
            *(volatile uint8_t *)(uintptr_t)CNT_A_ADDR = (uint8_t)b;
            *(volatile uint8_t *)(uintptr_t)CNT_B_ADDR = (uint8_t)c;
            *(volatile uint8_t *)(uintptr_t)A4A6_ADDR  = (uint8_t)d;
            *(volatile uint8_t *)(uintptr_t)A4A7_ADDR  = (uint8_t)e;
            *(volatile uint8_t *)(uintptr_t)ACC_ADDR   = (uint8_t)g;
            *(volatile uint8_t *)(uintptr_t)A4A9_ADDR  = (uint8_t)h;

            rx8_rev_limit_fuel_cut_init();

            printf("%02X %02X %02X %02X %02X %02X %02X\n",
                   *(volatile uint8_t *)(uintptr_t)A4A3_ADDR,
                   *(volatile uint8_t *)(uintptr_t)CNT_A_ADDR,
                   *(volatile uint8_t *)(uintptr_t)CNT_B_ADDR,
                   *(volatile uint8_t *)(uintptr_t)A4A6_ADDR,
                   *(volatile uint8_t *)(uintptr_t)A4A7_ADDR,
                   *(volatile uint8_t *)(uintptr_t)ACC_ADDR,
                   *(volatile uint8_t *)(uintptr_t)A4A9_ADDR);
        } else {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
    }
    return 0;
}

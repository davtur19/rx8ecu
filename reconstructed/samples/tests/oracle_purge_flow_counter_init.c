/* ============================================================================
 * oracle_purge_flow_counter_init.c  —  host test rig for
 *                                      rx8_purge_flow_counter_init @0xF534
 * ============================================================================
 * Compile together with src/rx8_purge_flow_counter_init.c (see
 * harness_purge_flow_counter_init.py) and pipe test vectors on stdin; one
 * vector per line, five space-separated hex bytes:
 *
 *     purge <a4af> <a4b0> <a4b1> <a4b2> <a4b3>
 *          -> <a4af'> <a4b0'> <a4b1'> <a4b2'> <a4b3'>
 *
 * The oracle re-implements the caller-side setup only: it mmap()s the page
 * backing the 3-byte purge-flow cell (same trick as host_oracle.c) and prints
 * the bytes after the call.  It contains NO copy of the function logic —
 * that lives solely in the reconstructed source under test.  The two sentinel
 * bytes (0xFFFFA4AF / 0xFFFFA4B3) must survive the call untouched; they catch
 * any over/under-run of the three byte stores.
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

#include "rx8_samples.h"

/* Prototype is NOT in rx8_samples.h (sample project convention: only the
 * verified "public" leaves are listed there); declared here for the rig. */
void rx8_purge_flow_counter_init(void);

#define PURGE_FLOW_ADDR   0xFFFFA4B0u  /* purge flow countdown counter (u8) */
#define PURGE_STATE_ADDR  0xFFFFA4B1u  /* purge flow state / target (u8)   */
#define PURGE_DEC_EN_ADDR 0xFFFFA4B2u  /* purge decrement enable (u8)      */

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
    /* Page 0xFFFFA000..0xFFFFAFFF backs the purge cell + both sentinels. */
    map_page(PURGE_FLOW_ADDR);

    char line[256];
    while (fgets(line, sizeof line, stdin)) {
        unsigned long s0, s1, s2, s3, s4;
        if (sscanf(line, "purge %lx %lx %lx %lx %lx",
                   &s0, &s1, &s2, &s3, &s4) == 5) {
            *(volatile uint8_t *)(uintptr_t)(PURGE_FLOW_ADDR - 1) = (uint8_t)s0;
            *(volatile uint8_t *)(uintptr_t)(PURGE_FLOW_ADDR)     = (uint8_t)s1;
            *(volatile uint8_t *)(uintptr_t)(PURGE_STATE_ADDR)    = (uint8_t)s2;
            *(volatile uint8_t *)(uintptr_t)(PURGE_DEC_EN_ADDR)   = (uint8_t)s3;
            *(volatile uint8_t *)(uintptr_t)(PURGE_FLOW_ADDR + 3) = (uint8_t)s4;

            rx8_purge_flow_counter_init();

            printf("%02X %02X %02X %02X %02X\n",
                   *(volatile uint8_t *)(uintptr_t)(PURGE_FLOW_ADDR - 1),
                   *(volatile uint8_t *)(uintptr_t)(PURGE_FLOW_ADDR),
                   *(volatile uint8_t *)(uintptr_t)(PURGE_STATE_ADDR),
                   *(volatile uint8_t *)(uintptr_t)(PURGE_DEC_EN_ADDR),
                   *(volatile uint8_t *)(uintptr_t)(PURGE_FLOW_ADDR + 3));
        } else {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
    }
    return 0;
}

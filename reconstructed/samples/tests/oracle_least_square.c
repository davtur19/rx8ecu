/* ============================================================================
 * oracle_least_square.c  —  host oracle for rx8_least_square
 * ============================================================================
 * Compile together with the reconstructed source (see
 * harness_least_square.py) and pipe test vectors on stdin; one vector per
 * line, whitespace-separated hex tokens:
 *
 *     ls <val> <ref>              -> <r>     (32-bit pack, hex)
 *
 * `val` is truncated to 8 bits exactly like the ROM's leading `extu.b`
 * (zero-extension of the low byte), so vectors with upper bits set still
 * verify the truncation path.  `ref` is written to the SECURITY_STATE_1
 * location (0xFFFFD20B) before the call — the leaf reads that byte through a
 * volatile pointer, so the oracle mmap()s the backing page (same trick as
 * tests/host_oracle.c for the idx-table pages) and stores each vector's
 * reference byte there.  The oracle contains NO copy of the function logic —
 * that lives solely in rx8_least_square.c under test.
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

#include "rx8_samples.h"

/* rx8_samples.h (shared, untouched by this sample) does not declare the
 * function under test; declare its prototype here instead. */
uint32_t rx8_least_square(uint8_t val);

/* SECURITY_STATE_1 — must match rx8_least_square.c. */
#define REF_ADDR 0xFFFFD20Bu

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

    /* Back the page holding the reference byte at 0xFFFFD20B. */
    map_page(REF_ADDR);

    while (fgets(line, sizeof line, stdin)) {
        unsigned long a, b;

        if (sscanf(line, "ls %lx %lx", &a, &b) == 2) {
            *(volatile uint8_t *)REF_ADDR = (uint8_t)b;
            printf("%08lX\n",
                   (unsigned long)rx8_least_square((uint8_t)(uint32_t)a));
        } else {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
    }
    return 0;
}

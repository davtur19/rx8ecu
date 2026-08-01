/* ============================================================================
 * oracle_immo_key_expander_365d6.c  —  host rig for rx8_immo_key_expander_365d6
 * ============================================================================
 * Compile together with samples/src/rx8_immo_key_expander_365d6.c and pipe
 * test vectors on stdin; one vector per line, whitespace-separated hex tokens:
 *
 *     immo <key> <w2E0> <w2DC>
 *         -> <slot0> <slot1> <slot2> <slot3> <exp1> <exp2> <exp3> <exp4>
 *
 * The oracle re-implements only the *caller-side* set-up: it mmap()s the page
 * backing the immobilizer RAM words (same MAP_FIXED trick as tests/host_oracle.c
 * and tests/oracle_purge_flow_decrement.c), seeds the three 32-bit inputs
 * (rolling code @0xFFFFC278, EEPROM key words @0xFFFFC2E0/@0xFFFFC2DC), runs
 * the reconstructed function, and prints the eight 32-bit words it wrote
 * (slots @0xFFFFC24C..0xFFFFC258, expected @0xFFFFC260..0xFFFFC26C).  It
 * contains NO copy of the function logic — that lives solely in the
 * reconstructed source under test.
 *
 * All of the addresses fall inside the 0xFFFFC000..0xFFFFCFFF page of the
 * 32 KB on-chip RAM window (0xFFFF6000..0xFFFFDFFF), well above
 * mmap_min_addr on this host, so the single fixed mapping succeeds.
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

#include "rx8_samples.h"

/* rx8_immo_key_expander_365d6 is not (yet) declared in rx8_samples.h — the
 * reconstructed sources are dropped in without touching the shared header. */
void rx8_immo_key_expander_365d6(void);

#define IMMO_KEY_ADDR    0xFFFFC278u   /* rolling code / keygen output    */
#define IMMO_W2E0_ADDR   0xFFFFC2E0u   /* EEPROM key word B (16.16)       */
#define IMMO_W2DC_ADDR   0xFFFFC2DCu   /* EEPROM key word A (16.16)       */
#define IMMO_SLOT0_ADDR  0xFFFFC24Cu
#define IMMO_SLOT1_ADDR  0xFFFFC250u
#define IMMO_SLOT2_ADDR  0xFFFFC254u
#define IMMO_SLOT3_ADDR  0xFFFFC258u
#define IMMO_EXP1_ADDR   0xFFFFC260u
#define IMMO_EXP2_ADDR   0xFFFFC264u
#define IMMO_EXP3_ADDR   0xFFFFC268u
#define IMMO_EXP4_ADDR   0xFFFFC26Cu

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

    /* Back the on-chip-RAM page 0xFFFFC000 — covers all words below. */
    map_page(IMMO_SLOT0_ADDR);

    while (fgets(line, sizeof line, stdin)) {
        unsigned long key, w2E0, w2DC;

        if (sscanf(line, "immo %lx %lx %lx", &key, &w2E0, &w2DC) == 3) {
            *(volatile uint32_t *)(uintptr_t)IMMO_KEY_ADDR  = (uint32_t)key;
            *(volatile uint32_t *)(uintptr_t)IMMO_W2E0_ADDR = (uint32_t)w2E0;
            *(volatile uint32_t *)(uintptr_t)IMMO_W2DC_ADDR = (uint32_t)w2DC;

            rx8_immo_key_expander_365d6();

            printf("%08lX %08lX %08lX %08lX %08lX %08lX %08lX %08lX\n",
                   (unsigned long)*(volatile uint32_t *)(uintptr_t)IMMO_SLOT0_ADDR,
                   (unsigned long)*(volatile uint32_t *)(uintptr_t)IMMO_SLOT1_ADDR,
                   (unsigned long)*(volatile uint32_t *)(uintptr_t)IMMO_SLOT2_ADDR,
                   (unsigned long)*(volatile uint32_t *)(uintptr_t)IMMO_SLOT3_ADDR,
                   (unsigned long)*(volatile uint32_t *)(uintptr_t)IMMO_EXP1_ADDR,
                   (unsigned long)*(volatile uint32_t *)(uintptr_t)IMMO_EXP2_ADDR,
                   (unsigned long)*(volatile uint32_t *)(uintptr_t)IMMO_EXP3_ADDR,
                   (unsigned long)*(volatile uint32_t *)(uintptr_t)IMMO_EXP4_ADDR);
        } else {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
    }
    return 0;
}

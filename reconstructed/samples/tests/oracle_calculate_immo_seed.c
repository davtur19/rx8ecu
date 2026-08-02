/* ============================================================================
 * oracle_calculate_immo_seed.c — host test rig for rx8_calculate_immo_seed
 * ============================================================================
 * Compile together with samples/src/rx8_calculate_immo_seed.c and pipe test
 * vectors on stdin; one vector per line, whitespace-separated hex tokens:
 *
 *     seed <keyA> <keyB> <rolling>        -> <seed>
 *
 *   keyA    : EEPROM key word A (RAM[0xFFFFC2DC], big-endian u32) -> r4
 *   keyB    : EEPROM key word B (RAM[0xFFFFC2E0])                 -> r5
 *   rolling : rolling code / key  (RAM[0xFFFFC278])               -> r6
 *   seed    : the computed 32-bit seed returned in r0
 *
 * The oracle contains NO copy of the seed logic — that lives solely in
 * src/rx8_calculate_immo_seed.c.  It mirrors the *caller-side* set-up of
 * ImmoGetSeed_3664E (c/ImmoGetSeed.c): the 0xFFFFC2xx RAM words are backed
 * with mmap(MAP_FIXED) pages (same trick as tests/host_oracle.c and
 * c/tests/test_*_49ED0.c) and the three inputs are seeded at the addresses
 * the real caller would read them from, then passed to the reconstructed
 * function as r4/r5/r6.  The routine itself is a pure leaf — it reads no
 * RAM and writes no RAM; the only observable effect is the returned seed.
 *
 * There are no ROM calibration pages and no internal bsr/jsr callees for
 * this function, so nothing else needs to be pinned on the host side.
 *
 * The 32-bit words are transferred as their numeric value; endianness does
 * not affect the comparison (the emulator side uses the same big-endian
 * numeric words).
 * ==========================================================================*/
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

#include "rx8_samples.h"

/* rx8_samples.h (shared, untouched by this sample) does not declare the
 * function under test; declare its prototype here instead. */
uint32_t rx8_calculate_immo_seed(uint32_t r4, uint32_t r5, uint32_t r6);

/* Immobilizer RAM words (c/eeprom_immo.h) read by the caller ImmoGetSeed_3664E
 * to build the r4/r5/r6 argument triple.  All live in the 0xFFFFC000 page. */
#define IMMO_KEY_A_ADDR  0xFFFFC2DCu   /* EEPROM[0x02..05] working copy   */
#define IMMO_KEY_B_ADDR  0xFFFFC2E0u   /* EEPROM[0x06..09] working copy   */
#define IMMO_ROLL_ADDR   0xFFFFC278u   /* rolling code out                */

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

    /* Back the page holding the immobilizer words (0xFFFFC000..0xFFFFCFFF). */
    map_page(0xFFFFC000u);

    while (fgets(line, sizeof line, stdin)) {
        unsigned long a, b, c;

        if (sscanf(line, "seed %lx %lx %lx", &a, &b, &c) == 3) {
            /* Seed the three caller-side RAM words, then run the pure seed
             * calculator with the same argument triple the ROM would build. */
            *(volatile uint32_t *)(uintptr_t)IMMO_KEY_A_ADDR = (uint32_t)a;
            *(volatile uint32_t *)(uintptr_t)IMMO_KEY_B_ADDR = (uint32_t)b;
            *(volatile uint32_t *)(uintptr_t)IMMO_ROLL_ADDR  = (uint32_t)c;

            printf("%08lX\n",
                   (unsigned long)rx8_calculate_immo_seed((uint32_t)a,
                                                          (uint32_t)b,
                                                          (uint32_t)c));
        } else {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
    }
    return 0;
}

/* ============================================================================
 * oracle_immo_get_seed_3664e.c — host test rig for rx8_immo_get_seed @0x3664E
 * ============================================================================
 * Reads one vector per line on stdin, whitespace-separated hex tokens:
 *
 *     imm <keyA> <keyB> <rolling>        -> <seed>
 *
 *   keyA    : EEPROM key word A, placed at RAM[0xFFFFC2DC] (big-endian u32)
 *   keyB    : EEPROM key word B, placed at RAM[0xFFFFC2E0]
 *   rolling : rolling code / key, placed at RAM[0xFFFFC278]
 *   seed    : the computed seed left at RAM[0xFFFFC270] (IMMO_SEED_OUT)
 *
 * The oracle contains NO copy of the seed logic — that lives solely in
 * src/rx8_immo_get_seed_3664e.c.  It only mirrors the *caller-side* set-up:
 * the 0xFFFFC2xx RAM words are backed with mmap(MAP_FIXED) pages (same trick
 * as tests/host_oracle.c and c/tests/test_*_49ED0.c), so the volatile
 * fixed-address pointers in the sample compile and fault-free on the host.
 * On the SH-2E those addresses are plain on-chip RAM; the ROM reads the three
 * input words and writes the result word — exactly what this rig does.
 *
 * The 32-bit words are transferred as their numeric value; on the little-
 * endian host they are stored via RX8_IO32() and read back the same way, so
 * endianness does not affect the comparison (the emulator side uses the same
 * big-endian numeric words).
 * ==========================================================================*/
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

#include "rx8_hw.h"

/* rx8_samples.h (shared, untouched by this sample) does not declare the
 * function under test; declare its prototype here instead. */
void rx8_immo_get_seed(void);

/* Immobilizer RAM words (c/eeprom_immo.h): key words + rolling code input,
 * seed output.  All four live in the 0xFFFFC000 page. */
#define IMMO_KEY_A_ADDR  0xFFFFC2DCu   /* EEPROM[0x02..05] working copy   */
#define IMMO_KEY_B_ADDR  0xFFFFC2E0u   /* EEPROM[0x06..09] working copy   */
#define IMMO_ROLL_ADDR   0xFFFFC278u   /* rolling code out                */
#define IMMO_SEED_ADDR   0xFFFFC270u   /* calculated seed (result)        */

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

        if (sscanf(line, "imm %lx %lx %lx", &a, &b, &c) == 3) {
            /* Seed the three input words, run the function, report the
             * seed word it wrote at 0xFFFFC270. */
            *(volatile uint32_t *)(uintptr_t)IMMO_KEY_A_ADDR = (uint32_t)a;
            *(volatile uint32_t *)(uintptr_t)IMMO_KEY_B_ADDR = (uint32_t)b;
            *(volatile uint32_t *)(uintptr_t)IMMO_ROLL_ADDR  = (uint32_t)c;
            rx8_immo_get_seed();
            printf("%08lX\n",
                   (unsigned long)*(volatile uint32_t *)(uintptr_t)IMMO_SEED_ADDR);
        } else {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
    }
    return 0;
}

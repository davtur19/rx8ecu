/* ============================================================================
 * oracle_math_min_max_49ed0.c — host test rig for rx8_math_min_max_49ed0
 * ============================================================================
 * Compile together with src/rx8_math_min_max_49ed0.c and pipe test vectors
 * on stdin; one vector per line, whitespace-separated hex tokens:
 *
 *     flg <word> <outA_init> <outB_init>    -> <result> <outA> <outB>
 *
 *   word      : 16-bit input word, stored at RAM 0xFFFFF76C (bit 0x100 is
 *               the only one the ROM ever tests)
 *   outA_init : sentinel byte written to RAM 0xFFFFCD48 before the call
 *   outB_init : sentinel byte written to RAM 0xFFFFCD49 before the call
 *
 * The oracle re-implements the *caller-side* set-up only: it mmap()s the two
 * pages backing the fixed RAM addresses (0xFFFFC000 for the output bytes,
 * 0xFFFFF000 for the input word — same MAP_FIXED trick as tests/host_oracle.c)
 * and prints the returned flag plus the two flag bytes after the call, so the
 * harness can verify the RAM side effects byte-exactly.  It contains NO copy
 * of the function logic — that lives solely in src/rx8_math_min_max_49ed0.c.
 * ==========================================================================*/
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

#include "rx8_samples.h"

/* Declared here rather than in rx8_samples.h (off-limits for this task) — the
 * reconstructed name maps to the ROM flag-setter leaf at 0x49ED0 (see
 * src/rx8_math_min_max_49ed0.c). */
uint32_t rx8_math_min_max_49ed0(void);

#define IN_WORD 0xFFFFF76Cu   /* input  word (RAM)  */
#define OUT_A   0xFFFFCD48u   /* output byte A (RAM) */
#define OUT_B   0xFFFFCD49u   /* output byte B (RAM) */

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

    /* Back the pages holding the function's RAM footprint: output bytes
     * (0xFFFFCD48/49, page 0xFFFFC000) and input word (0xFFFFF76C, page
     * 0xFFFFF000).  Native 16-bit store on the LE host gives the C lift the
     * same numeric word value the emulator's big-endian mov.w read sees. */
    map_page(0xFFFFC000u);
    map_page(0xFFFFF000u);

    while (fgets(line, sizeof line, stdin)) {
        unsigned long word, a, b;

        if (sscanf(line, "flg %lx %lx %lx", &word, &a, &b) == 3) {
            *(volatile uint16_t *)IN_WORD = (uint16_t)word;
            *(volatile uint8_t *)OUT_A = (uint8_t)a;
            *(volatile uint8_t *)OUT_B = (uint8_t)b;

            uint32_t r = rx8_math_min_max_49ed0();

            printf("%X %02X %02X\n",
                   r,
                   *(volatile uint8_t *)OUT_A,
                   *(volatile uint8_t *)OUT_B);
        } else {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
    }
    return 0;
}

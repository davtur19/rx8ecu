/* ============================================================================
 * oracle_set_register_reg_bit_val.c  —  host test rig for
 * rx8_set_register_reg_bit_val @0x4BBC
 * ============================================================================
 * Piped on stdin, one vector per line:
 *
 *     reg <addr> <init> <mask> <enable>       -> <result 4 hex digits>
 *
 *   addr   : hex RAM address of the 16-bit register (r4)
 *   init   : initial 16-bit register value (seeded into RAM)
 *   mask   : 16-bit bit mask (r5)
 *   enable : 32-bit enable flag (r6; the ROM zero-extends it to 16 bits)
 *
 * Output: the 16-bit value left in the register after the call.
 *
 * The oracle re-implements the caller-side set-up only: it mmap()s the page
 * that backs `addr` (MAP_FIXED, so the emulator and the host C run against
 * the same numeric pointer), seeds the initial register word, then calls the
 * reconstructed function under test.  It contains NO copy of the function
 * logic — that lives solely in samples/src/rx8_set_register_reg_bit_val.c.
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

#include "rx8_samples.h"

/* The reconstructed function under test.  rx8_samples.h (shared, untouched
 * by this sample) does not declare it; declare the prototype here instead. */
void rx8_set_register_reg_bit_val(uint16_t *reg, uint16_t mask, int enable);

/* MAP_FIXED bookkeeping: several vectors may reuse the same page base, so
 * never remap (and thereby wipe) a base that is already mapped. */
static uintptr_t g_mapped[8];
static int g_nmapped = 0;

static void map_once(uintptr_t addr)
{
    long page = sysconf(_SC_PAGESIZE);
    uintptr_t base = addr & ~((uintptr_t)page - 1);

    for (int i = 0; i < g_nmapped; i++) {
        if (g_mapped[i] == base) {
            return;              /* already backed, keep its contents */
        }
    }
    void *p = mmap((void *)base, (size_t)page, PROT_READ | PROT_WRITE,
                   MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED, -1, 0);
    if (p == MAP_FAILED) {
        perror("mmap");
        exit(1);
    }
    if (g_nmapped < (int)(sizeof g_mapped / sizeof g_mapped[0])) {
        g_mapped[g_nmapped++] = base;
    }
}

int main(void)
{
    char line[256];

    while (fgets(line, sizeof line, stdin)) {
        unsigned long addr, init, mask, enable;

        if (sscanf(line, "reg %lx %lx %lx %lx", &addr, &init, &mask, &enable)
            != 4) {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
        if ((addr & 1) != 0) {          /* mov.w needs a halfword boundary */
            fprintf(stderr, "unaligned register address: %s", line);
            return 2;
        }

        map_once(addr);

        uint16_t *reg = (uint16_t *)(uintptr_t)addr;
        *(volatile uint16_t *)reg = (uint16_t)init;

        /* enable ships as a full 32-bit word (may have bits >= 16 set, which
         * the ROM's extu.w strips) — pass it through as signed int32 like
         * the ABI register r6. */
        rx8_set_register_reg_bit_val(reg, (uint16_t)mask,
                                     (int)(uint32_t)enable);

        printf("%04X\n", (unsigned)*(volatile uint16_t *)reg);
    }
    return 0;
}

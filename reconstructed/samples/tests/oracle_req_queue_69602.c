/* ============================================================================
 * oracle_req_queue_69602.c  —  host test rig for rx8_req_queue_69602
 *                             (store @0x69602 / clear @0x69694)
 * ============================================================================
 * Compile together with src/rx8_req_queue_69602.c and pipe test vectors on
 * stdin; one vector per line, whitespace-separated hex tokens:
 *
 *     vec <b> <base> <r5> <preflag>      -> <v1> <f1> <f2>
 *
 *   b        : request-queue index (masked to 8 bits)
 *   base     : u32 base value written to RAM @0xFFFFF430 before the store
 *   r5       : u32 value passed to the store leaf
 *   preflag  : initial byte value of the flag @0xFFFFDE38+b
 *
 * Per vector the rig:
 *   1. writes `base` to 0xFFFFF430 and `preflag` to the flag byte,
 *   2. calls rx8_req_queue_store_69602(b, r5), then prints the resulting
 *      u32 slot @0xFFFFDE40+b*4 (`v1`) and the flag byte (`f1`, always 1),
 *   3. calls rx8_req_queue_clear_69694(b), then prints the flag byte again
 *      (`f2`, always 0).
 *
 * The pages backing the on-chip-RAM window (0xFFFFD000, 0xFFFFE000 for the
 * value array spilling past b >= 0x70, and 0xFFFFF000 for the base) are
 * mmap()ed MAP_FIXED so the reconstructed source's volatile dereferences of
 * the raw SH-2 addresses work unmodified (same trick as tests/host_oracle.c
 * and c/tests/test_req_queue_69602.c).  The oracle contains NO copy of the
 * queue logic — that lives solely in src/rx8_req_queue_69602.c.
 * ==========================================================================*/
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

#include "rx8_samples.h"

/* The reconstructed names map to the ROM leaves at 0x69602 / 0x69694 (see
 * rx8_req_queue_69602.c); rx8_samples.h is off-limits for this task so the
 * prototypes are declared here, like oracle_div32_signed.c does. */
void rx8_req_queue_store_69602(uint32_t r4, uint32_t r5);
void rx8_req_queue_clear_69694(uint32_t r4);

#define FLAGS  0xFFFFDE38u
#define VALUES 0xFFFFDE40u
#define BASE   0xFFFFF430u

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

    /* On-chip RAM window: flag array + value array (0xFFFFDE38..0xFFFFE23C
     * spans pages 0xFFFFD000/0xFFFFE000), plus the base long @0xFFFFF430. */
    map_page(0xFFFFD000u);
    map_page(0xFFFFE000u);
    map_page(0xFFFFF000u);

    while (fgets(line, sizeof line, stdin)) {
        unsigned long b, base, r5, preflag;

        if (sscanf(line, "vec %lx %lx %lx %lx", &b, &base, &r5, &preflag) == 4) {
            uint8_t idx = (uint8_t)b;
            uint32_t v1;
            uint8_t f1, f2;

            *(volatile uint32_t *)BASE = (uint32_t)base;
            *(volatile uint8_t *)(FLAGS + idx) = (uint8_t)preflag;

            rx8_req_queue_store_69602(idx, (uint32_t)r5);
            v1 = *(volatile uint32_t *)(VALUES + idx * 4);
            f1 = *(volatile uint8_t *)(FLAGS + idx);

            rx8_req_queue_clear_69694(idx);
            f2 = *(volatile uint8_t *)(FLAGS + idx);

            printf("%08X %02X %02X\n", v1, f1, f2);
        } else {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
    }
    return 0;
}

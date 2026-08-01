/* ============================================================================
 * oracle_set_memory_not_valid2.c  —  host test rig for
 *                                     rx8_set_memory_not_valid2 @0x3E5A8
 * ============================================================================
 * Reads one vector per line on stdin, whitespace-separated hex tokens:
 *
 *     cp <src_addr> <dst_addr> <src_byte> <dst_seed>   -> <dst_byte>
 *
 *   src_addr/dst_addr : 32-bit RAM addresses the copy reads from / writes to
 *   src_byte          : byte placed at RAM[src_addr] before the call
 *   dst_seed          : byte placed at RAM[dst_addr] before the call (unless
 *                       dst_addr == src_addr), proving the copy overwrites
 *   dst_byte          : the byte left at RAM[dst_addr], printed as %02X
 *
 * The oracle contains NO copy of the copy logic — that lives solely in
 * src/rx8_set_memory_not_valid2.c.  It only mirrors the *caller-side* set-up:
 * the two 0xFFFFxxxx RAM bytes are backed with mmap(MAP_FIXED) pages (same
 * trick as tests/host_oracle.c and tests/oracle_radiator_fan_relay_write.c),
 * so the volatile fixed-address pointers compile and fault-free on the host.
 * This is exactly what the ROM does on the SH-2E, where both addresses are
 * plain on-chip RAM.
 *
 * NOTE: this sample's function is a non-ABI leaf (ROM r2 = src, r5 = dst; see
 * the .c header — the lift c/SetMemoryNotValid2.c belongs to the 60E0FC00
 * image and does NOT match 60E1D400.bin at 0x3E5A8).  The oracle therefore
 * hands the two pointers straight to the reconstructed function; the emulator
 * harness seeds r2/r5 the same way.
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

#include "rx8_samples.h"

/* rx8_samples.h (shared, untouched by this sample) does not declare the
 * function under test; declare its prototype here instead. */
void rx8_set_memory_not_valid2(uint8_t *src, uint8_t *dst);

/* RAM window the vectors may touch: on-chip RAM pages 0xFFFFA000 (byte at
 * 0xFFFFA4xx) and 0xFFFFB000 (byte at 0xFFFFB5xx).  The harness only ever
 * emits addresses from these two pages. */
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

    /* Back the two on-chip-RAM pages the vectors address. */
    map_page(0xFFFFA000u);
    map_page(0xFFFFB000u);

    while (fgets(line, sizeof line, stdin)) {
        unsigned long src_a, dst_a, src_b, dst_s;

        if (sscanf(line, "cp %lx %lx %lx %lx", &src_a, &dst_a, &src_b, &dst_s)
            == 4) {
            /* Seed source byte, seed destination garbage (unless self-copy),
             * run the function, report the destination byte. */
            *(volatile uint8_t *)(uintptr_t)src_a = (uint8_t)src_b;
            if (dst_a != src_a)
                *(volatile uint8_t *)(uintptr_t)dst_a = (uint8_t)dst_s;
            rx8_set_memory_not_valid2((uint8_t *)(uintptr_t)src_a,
                                      (uint8_t *)(uintptr_t)dst_a);
            printf("%02X\n",
                   (unsigned)*(volatile uint8_t *)(uintptr_t)dst_a);
        } else {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
    }
    return 0;
}

/* ============================================================================
 * oracle_knock_function_init.c  —  host test rig for
 *                                   rx8_knock_function_init @0xC31C
 * ============================================================================
 * Compile together with src/rx8_knock_function_init.c (see
 * harness_knock_function_init.py) and pipe test vectors on stdin; one vector
 * per line, twelve space-separated hex bytes (the pre-state of every cell the
 * function may touch, plus its store-width sentinels):
 *
 *     knk <a325> <a373> <a374> <a375> <a376> <a377>
 *         <a378> <a379> <a37a> <a37b> <a38c> <a38d>
 *         -> <f374 bits> <w378> <w37a> <a325'> <a38c'> <a373'> <a38d'>
 *
 *   <a374>..<a377>  pre-state of the 4-byte knock-scale float at 0xFFFFA374
 *   <a378>/<a379>   pre-state of the 16-bit threshold word at 0xFFFFA378
 *   <a37a>/<a37b>   pre-state of the 16-bit threshold word at 0xFFFFA37A
 *   <a325>/<a38c>   pre-state of the two knock-flag bytes (overwritten)
 *   <a373>/<a38d>   sentinel bytes that must survive the call untouched —
 *                   they pin the store count and the write boundaries.
 *
 * The oracle re-implements the caller-side setup only: it mmap()s the page
 * backing the cells (same trick as host_oracle.c), seeds the pre-state, and
 * prints the state after the call.  It contains NO copy of the function logic
 * — that lives solely in the reconstructed source under test.  The two
 * sub-calls (atu2_tior2c_waveform_init @0xC346 and knockRelatedInit @0xC3C8)
 * are stubbed as no-ops: the function under test neither reads nor depends on
 * anything they write, so the stubs are behaviourally equivalent within the
 * verified scope (see rx8_knock_function_init.c header).
 *
 * NOTE on endianness: the 16-bit words and the 32-bit float are printed as
 * NUMERIC values (not raw bytes) so the little-endian host and the
 * big-endian SH-2E emulator agree bit-for-bit.  The two flag bytes and the
 * two sentinels are single bytes and are printed as-is.
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

#include "rx8_samples.h"

/* Prototype is NOT in rx8_samples.h (sample project convention: only the
 * verified "public" leaves are listed there); declared here for the rig. */
void rx8_knock_function_init(void);

/* Stubs of the ROM sub-functions @0xC346 / @0xC3C8 (see header comment: the
 * function under test ignores everything they do, so no-op is equivalent
 * within the verified scope). */
void atu2_tior2c_waveform_init(void) {}
void knockRelatedInit(void) {}

#define A325_ADDR  0xFFFFA325u  /* knock flag B (u8, overwritten)   */
#define A373_ADDR  0xFFFFA373u  /* sentinel: left of the scale float*/
#define FLT_ADDR   0xFFFFA374u  /* knock scale float (4 bytes)      */
#define W378_ADDR  0xFFFFA378u  /* threshold word A (u16)           */
#define W37A_ADDR  0xFFFFA37Au  /* threshold word B (u16)           */
#define A38C_ADDR  0xFFFFA38Cu  /* knock flag A (u8, overwritten)   */
#define A38D_ADDR  0xFFFFA38Du  /* sentinel: right of flag A        */

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
    /* All cells live in the 0xFFFFA000..0xFFFFAFFF page; one mmap. */
    map_page(A325_ADDR);

    char line[256];
    while (fgets(line, sizeof line, stdin)) {
        unsigned long a, b, c, d, e, f, g, h, i, j, k, l;
        if (sscanf(line, "knk %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx",
                   &a, &b, &c, &d, &e, &f, &g, &h, &i, &j, &k, &l) == 12) {
            *(volatile uint8_t *)(uintptr_t)(A325_ADDR + 0) = (uint8_t)a;
            *(volatile uint8_t *)(uintptr_t)(A373_ADDR + 0) = (uint8_t)b;
            *(volatile uint8_t *)(uintptr_t)(FLT_ADDR + 0)  = (uint8_t)c;
            *(volatile uint8_t *)(uintptr_t)(FLT_ADDR + 1)  = (uint8_t)d;
            *(volatile uint8_t *)(uintptr_t)(FLT_ADDR + 2)  = (uint8_t)e;
            *(volatile uint8_t *)(uintptr_t)(FLT_ADDR + 3)  = (uint8_t)f;
            *(volatile uint8_t *)(uintptr_t)(W378_ADDR + 0) = (uint8_t)g;
            *(volatile uint8_t *)(uintptr_t)(W378_ADDR + 1) = (uint8_t)h;
            *(volatile uint8_t *)(uintptr_t)(W37A_ADDR + 0) = (uint8_t)i;
            *(volatile uint8_t *)(uintptr_t)(W37A_ADDR + 1) = (uint8_t)j;
            *(volatile uint8_t *)(uintptr_t)(A38C_ADDR + 0) = (uint8_t)k;
            *(volatile uint8_t *)(uintptr_t)(A38D_ADDR + 0) = (uint8_t)l;

            rx8_knock_function_init();

            uint32_t fbits;
            memcpy(&fbits, (const void *)(uintptr_t)FLT_ADDR, 4);
            printf("%08X %04X %04X %02X %02X %02X %02X\n",
                   fbits,
                   (unsigned)*(volatile uint16_t *)(uintptr_t)W378_ADDR,
                   (unsigned)*(volatile uint16_t *)(uintptr_t)W37A_ADDR,
                   (unsigned)*(volatile uint8_t *)(uintptr_t)A325_ADDR,
                   (unsigned)*(volatile uint8_t *)(uintptr_t)A38C_ADDR,
                   (unsigned)*(volatile uint8_t *)(uintptr_t)A373_ADDR,
                   (unsigned)*(volatile uint8_t *)(uintptr_t)A38D_ADDR);
        } else {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
    }
    return 0;
}

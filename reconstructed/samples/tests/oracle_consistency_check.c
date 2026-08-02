/* ============================================================================
 * oracle_consistency_check.c  —  host rig for rx8_consistency_check @0x3A28
 * ============================================================================
 * Compile together with samples/src/rx8_consistency_check.c (see
 * harness_consistency_check.py) and pipe test vectors on stdin; one vector
 * per line:
 *
 *   cc <task> <ctx0> <sr> <cur> <exp> <save> <shadow>
 *      <w0> <w1> <w2> <w3> <d0> <d1> ... <d15>
 *          -> <ret> <cnt> <exp> <ctx0> <ctx6> <bmp0> <bmp1> <snt>
 *
 * Fields (all hex):
 *   task   u8   task id passed in r5 (sign-extended by the ROM)
 *   ctx0   u8   ctx+0 current-task byte (pre-state)
 *   sr     u32  ctx+0x10 SR shadow (used only inside the HUDI callee)
 *   cur    u16  *counter (counter buffer word 0)
 *   exp    u16  *(counter+2) expected word
 *   save   u16  entry[task]+0 shadow save value
 *   shadow u16  entry[task]+2 shadow expected value
 *   w0..w3 u32  the 16-byte exception/pending block @0xFFFF72E0
 *   d0..d15 u16 the 16-entry diagnostic table @0xFFFF7234
 *
 * Output (post-state, hex, all numeric = endianness-independent so the
 * little-endian host and the big-endian SH-2E agree bit-for-bit):
 *   ret   int32  ABI return value (r0)
 *   cnt   u16    *counter after the call
 *   exp   u16    *(counter+2) after the call (must be untouched)
 *   ctx0  u8     ctx+0 after the call (written by the HUDI callee)
 *   ctx6  u16    ctx+6 diagnostic field after the call
 *   bmp0  u8     pending-flags byte @0xFFFF72E0
 *   bmp1  u8     pending-flags byte @0xFFFF72E1 (bitmap boundary)
 *   snt   u8     @0xFFFF72E2 (sentinel; must be untouched)
 *
 * Fixed addresses backing the model (all on the single page 0xFFFF7000):
 *   ctx      0xFFFF72B0   kernel context block
 *   diag     0xFFFF7234   16 x u16 diagnostic table
 *   bitmap   0xFFFF72E0   16-byte exception/pending block
 *   entries  0xFFFF7300   0x80 x 8-byte task table
 *   scratch  0xFFFF7800   single 4-byte counter buffer every entry points at
 *
 * All 0x80 entries' counter-pointer is pre-filled with `scratch` (matching
 * the harness' emulator-side fill), so the HUDI callee's entry[code] read
 * and the parent's entry[task] read both land on the seeded buffer.  The
 * diagnostic table is deliberately 16 entries wide: the parent's mismatch
 * diag index is bounded by construction (cur/save <= 0x0F) and the HUDI
 * callee is only driven in its "no exception pending" state (w0..w3 all
 * zero), so the 0xFFFF counter value it would otherwise index is never
 * reached.  $RX8_ROM_PATH is not needed (no ROM calibration reads).
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
#include <sys/mman.h>
#include <unistd.h>

#include "rx8_samples.h"

/* Prototype is NOT in rx8_samples.h (sample project convention: only the
 * verified "public" leaves are listed there); declared here for the rig. */
int32_t rx8_consistency_check(uint8_t *ctx, int8_t task_id);

#define CTX_BASE   0xFFFF72B0u
#define DIAG_BASE  0xFFFF7234u
#define BITMAP_BASE 0xFFFF72E0u
#define ENTRY_TABLE 0xFFFF7300u
#define SCRATCH    0xFFFF7800u

#define NENTRY     0x80u            /* entry table rows (matches harness)   */

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

static void put16(uintptr_t a, uint16_t v)
{
    *(volatile uint16_t *)(uintptr_t)a = v;
}

static void put32(uintptr_t a, uint32_t v)
{
    *(volatile uint32_t *)(uintptr_t)a = v;
}

static uint16_t get16(uintptr_t a)
{
    return *(volatile uint16_t *)(uintptr_t)a;
}

static uint8_t get8(uintptr_t a)
{
    return *(volatile uint8_t *)(uintptr_t)a;
}

int main(void)
{
    char line[2048];
    unsigned long v[27];

    map_page(CTX_BASE);

    while (fgets(line, sizeof line, stdin)) {
        if (sscanf(line,
                   "cc %lx %lx %lx %lx %lx %lx %lx "
                   "%lx %lx %lx %lx "
                   "%lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx "
                   "%lx %lx %lx",
                   &v[0], &v[1], &v[2], &v[3], &v[4], &v[5], &v[6],
                   &v[7], &v[8], &v[9], &v[10],
                   &v[11], &v[12], &v[13], &v[14], &v[15], &v[16], &v[17],
                   &v[18], &v[19], &v[20], &v[21], &v[22], &v[23], &v[24],
                   &v[25], &v[26]) != 27) {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }

        uint8_t  task   = (uint8_t)v[0];
        uint8_t  ctx0   = (uint8_t)v[1];
        uint32_t sr     = (uint32_t)v[2];
        uint16_t cur    = (uint16_t)v[3];
        uint16_t exp    = (uint16_t)v[4];
        uint16_t save   = (uint16_t)v[5];
        uint16_t shadow = (uint16_t)v[6];

        /* context block */
        *(volatile uint8_t *)(uintptr_t)(CTX_BASE + 0x00) = ctx0;
        put16(CTX_BASE + 0x06, 0x1234u);            /* diag pre-state       */
        put32(CTX_BASE + 0x10, sr);
        put32(CTX_BASE + 0x20, ENTRY_TABLE);
        put32(CTX_BASE + 0x24, DIAG_BASE);

        /* every entry's counter pointer -> the single scratch buffer */
        for (unsigned e = 0; e < NENTRY; e++) {
            put32(ENTRY_TABLE + e * 8u + 0x04u, SCRATCH);
        }
        put16(ENTRY_TABLE + (uintptr_t)task * 8u + 0x00u, save);
        put16(ENTRY_TABLE + (uintptr_t)task * 8u + 0x02u, shadow);

        /* counter buffer */
        put16(SCRATCH, cur);
        put16(SCRATCH + 2u, exp);

        /* exception/pending block @0xFFFF72E0 (16 bytes from w0..w3) */
        for (unsigned i = 0; i < 4; i++) {
            put32(BITMAP_BASE + i * 4u, (uint32_t)v[7 + i]);
        }

        /* diagnostic table @0xFFFF7234 */
        for (unsigned i = 0; i < 16; i++) {
            put16(DIAG_BASE + i * 2u, (uint16_t)v[11 + i]);
        }

        int32_t ret = rx8_consistency_check((uint8_t *)(uintptr_t)CTX_BASE,
                                            (int8_t)task);

        printf("%08X %04X %04X %02X %04X %02X %02X %02X\n",
               (unsigned)ret,
               (unsigned)get16(SCRATCH),
               (unsigned)get16(SCRATCH + 2u),
               (unsigned)get8(CTX_BASE + 0x00),
               (unsigned)get16(CTX_BASE + 0x06),
               (unsigned)get8(BITMAP_BASE),
               (unsigned)get8(BITMAP_BASE + 1u),
               (unsigned)get8(BITMAP_BASE + 2u));
    }
    return 0;
}

/* ============================================================================
 * oracle_complement_shift_u32.c  —  host test rig for rx8_complement_shift_u32
 * ============================================================================
 * Compile together with samples/src/rx8_complement_shift_u32.c and pipe test
 * vectors on stdin; one vector per line:
 *
 *     f32 <threshold> <value> <adjustment>        -> <r>
 *
 * Each argument is an 8-digit hex IEEE-754 single-precision bit pattern
 * (big-endian order, exactly how the SH-2E FPU registers hold them).  The
 * oracle bit-casts the patterns to `float` with memcpy so the host C sees the
 * same values the emulator puts into FR4 / FR5 / FR6.  The result is printed
 * as an 8-digit hex uint32_t (always 0 or 1).
 *
 * No RAM or MMIO is involved: the function is pure FPU arithmetic, so no
 * mmap(MAP_FIXED) rig is needed (unlike the idx-table host_oracle.c).
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>
#include <string.h>

#include "rx8_samples.h"

/* 0x2440 — declared here because rx8_samples.h carries only the samples that
 * predate this reconstruction; the prototype must match the definition in
 * samples/src/rx8_complement_shift_u32.c. */
uint32_t rx8_complement_shift_u32(float threshold, float value, float adjustment);

/* Bit-cast an IEEE-754 single bit pattern to `float` (endianness-safe). */
static float bits_to_float(uint32_t bits)
{
    float f;
    memcpy(&f, &bits, sizeof f);
    return f;
}

int main(void)
{
    char line[256];

    while (fgets(line, sizeof line, stdin)) {
        unsigned long t, v, a;

        if (sscanf(line, "f32 %lx %lx %lx", &t, &v, &a) == 3) {
            printf("%08X\n", (unsigned int)rx8_complement_shift_u32(
                       bits_to_float((uint32_t)t),
                       bits_to_float((uint32_t)v),
                       bits_to_float((uint32_t)a)));
        } else {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
    }
    return 0;
}

/* ============================================================================
 * oracle_bitfield_extract_merge.c — host test rig for rx8_bitfield_extract_merge
 * ============================================================================
 * Standalone oracle compiled together with src/rx8_bitfield_extract_merge.c
 * (NOT host_oracle.c — this rig is private to harness_bitfield_extract_merge.py).
 *
 * Input:  one vector per line on stdin,
 *             bfe <hex32>          IEEE-754 bit pattern of the float argument
 * Output: one line per vector,
 *             <out0> <out1>        exponent word, significand word (hex32)
 *
 * The float bit pattern is reconstructed with memcpy() so the numeric value
 * handed to the C function is the exact IEEE-754 pattern on both the BE target
 * and the LE host (same trick as the harness's struct round-trip).
 * ==========================================================================*/
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* Not in rx8_samples.h (that header is frozen for all samples), so the
 * prototype is spelled out here; the definition lives in
 * src/rx8_bitfield_extract_merge.c, compiled into this same binary. */
void rx8_bitfield_extract_merge(float value, uint32_t *out);

int main(void)
{
    char line[256];

    while (fgets(line, sizeof line, stdin)) {
        unsigned long bits;

        if (sscanf(line, "bfe %lx", &bits) != 1) {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
        uint32_t word = (uint32_t)bits;
        float value;
        memcpy(&value, &word, sizeof value);

        uint32_t out[2];
        rx8_bitfield_extract_merge(value, out);
        printf("%08X %08X\n", out[0], out[1]);
    }
    return 0;
}

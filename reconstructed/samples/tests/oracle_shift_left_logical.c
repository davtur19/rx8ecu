/* ============================================================================
 * oracle_shift_left_logical.c  —  host oracle for rx8_shift_left_logical
 * ============================================================================
 * Compile together with the reconstructed source (see
 * harness_shift_left_logical.py) and pipe test vectors on stdin; one vector
 * per line, whitespace-separated hex tokens:
 *
 *     shl <val> <cnt>                -> <r>     (32-bit result, hex)
 *
 * `val` is the 32-bit value to shift (hex), `cnt` is the 32-bit raw register
 * image of the count (hex).  The count is interpreted as SIGNED int32_t on
 * both sides — the emulator places the raw 32 bits into r1 and the ROM's
 * `cmp/pz` reads the sign bit, exactly as the cast below does.  The oracle
 * contains NO copy of the function logic — that lives solely in
 * rx8_shift_left_logical.c under test.
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>

#include "rx8_samples.h"

/* 0x4308 — logical (zero-fill) left shift; value in r0, signed count in r1,
 * result in r0.  Declared here rather than in rx8_samples.h so this sample
 * stays self-contained and leaves the shared header untouched. */
uint32_t rx8_shift_left_logical(uint32_t val, int32_t cnt);

int main(void)
{
    char line[256];

    while (fgets(line, sizeof line, stdin)) {
        char op[16];
        unsigned long a, b;

        if (sscanf(line, "%15s %lx %lx", op, &a, &b) == 3) {
            uint32_t val = (uint32_t)a;
            int32_t  cnt = (int32_t)(uint32_t)b;
            printf("%08lX\n", (unsigned long)rx8_shift_left_logical(val, cnt));
        } else {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
    }
    return 0;
}

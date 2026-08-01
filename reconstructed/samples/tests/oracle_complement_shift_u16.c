/* ============================================================================
 * oracle_complement_shift_u16.c  —  host oracle for rx8_complement_shift_u16
 * ============================================================================
 * Compile together with the reconstructed source (see
 * harness_complement_shift_u16.py) and pipe test vectors on stdin; one vector
 * per line, whitespace-separated hex tokens:
 *
 *     u16 <val>                    -> <r>     (32-bit pack, hex)
 *
 * `val` is truncated to 16 bits exactly like the ROM's leading `extu.w`
 * (zero-extension of the low half), so vectors with upper bits set still
 * verify the truncation path.  The oracle contains NO copy of the function
 * logic — that lives solely in rx8_complement_shift_u16.c under test.
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>

#include "rx8_samples.h"

/* rx8_samples.h (shared, untouched by this sample) does not declare the
 * function under test; declare its prototype here instead. */
uint32_t rx8_complement_shift_u16(uint16_t val);

int main(void)
{
    char line[256];

    while (fgets(line, sizeof line, stdin)) {
        unsigned long a;

        if (sscanf(line, "u16 %lx", &a) == 1) {
            printf("%08lX\n",
                   (unsigned long)rx8_complement_shift_u16((uint16_t)(uint32_t)a));
        } else {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
    }
    return 0;
}

/* ============================================================================
 * oracle_get_hcan_register_address.c — host test rig for
 *                                         rx8_get_hcan_register_address @0xD198
 * ============================================================================
 * Reads one vector per line on stdin, whitespace-separated hex tokens:
 *
 *     hcan <idx> <base>       -> <result>
 *
 *   idx  : channel index as a full 32-bit word (r4 in the ROM; the ROM's very
 *          first `extu.b r4,r4` masks it to 8 bits, which the reconstructed
 *          function's uint8_t parameter does identically)
 *   base : register-block base address (r5 in the ROM)
 *
 * and prints the 32-bit result as %08X.  The oracle contains NO copy of the
 * address logic — that lives solely in src/rx8_get_hcan_register_address.c.
 * The op token mirrors the caller-side set-up used by the emulator harness
 * (idx in r4, base in r5), but both operands are simply forwarded to the C
 * function.
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>

#include "rx8_samples.h"

/* rx8_samples.h (shared, untouched by this sample) does not declare the
 * function under test; declare its prototype here instead. */
uint32_t rx8_get_hcan_register_address(uint8_t idx, uint32_t base);

int main(void)
{
    char line[256];

    while (fgets(line, sizeof line, stdin)) {
        unsigned long idx, base;

        if (sscanf(line, "hcan %lx %lx", &idx, &base) == 2) {
            printf("%08lX\n",
                   (unsigned long)(uint32_t)rx8_get_hcan_register_address(
                       (uint8_t)(uint32_t)idx, (uint32_t)base));
        } else {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
    }
    return 0;
}

/* ============================================================================
 * oracle_get_sr.c  —  host test rig for rx8_get_sr @0x3920
 * ============================================================================
 * Compile together with src/rx8_get_sr.c and pipe test vectors on stdin;
 * one vector per line, whitespace-separated hex tokens:
 *
 *     sr <cur_sr> <requested>            -> <ret> <new_sr>
 *
 * where <cur_sr> is the SR value that must be active before the call (the
 * harness seeds it, mirroring the emulator's `sr=` argument), <requested> is
 * r4 (the value getSR conditionally writes to SR), <ret> is the returned old
 * (SR & 0xF0) mask and <new_sr> is the SR state after the call.
 *
 * The oracle contains NO copy of the function logic — it only seeds SR state
 * and calls the reconstructed function under test.
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>

/* Declared here (not in rx8_samples.h): the SR-state seeding is a test hook,
 * and the function itself is verified standalone. */
extern uint32_t rx8_get_sr(uint32_t requested_sr);
extern void     rx8_sr_set_state(uint32_t sr);
extern uint32_t rx8_sr_get_state(void);

int main(void)
{
    char line[256];

    while (fgets(line, sizeof line, stdin)) {
        unsigned long cur_sr, requested;

        if (sscanf(line, "sr %lx %lx", &cur_sr, &requested) != 2) {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }

        rx8_sr_set_state((uint32_t)cur_sr);
        uint32_t ret = rx8_get_sr((uint32_t)requested);
        uint32_t new_sr = rx8_sr_get_state();

        printf("%08lX %08lX\n",
               (unsigned long)ret, (unsigned long)new_sr);
    }
    return 0;
}

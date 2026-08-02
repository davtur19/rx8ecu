/* ============================================================================
 * oracle_message_queue_state_dispatcher_369b8.c  —  host rig for
 *                                             rx8_message_queue_state_dispatcher_369b8
 * ============================================================================
 * Compile together with samples/src/rx8_message_queue_state_dispatcher_369b8.c
 * and pipe test vectors on stdin; one vector per line, whitespace-separated
 * hex tokens:
 *
 *     imsg <cmd> <b0> <b1> ... <b20> <w0> <w1> <w2> <w3> <w4>
 *         -> <b0'> <b1'> ... <b20'> <w0'> <w1'> <w2'> <w3'> <w4'>
 *
 *   <cmd>        the CAN message id argument (arrives in r4 on the target)
 *   <b0>..<b20>  the 21 compared byte cells (order matches the harness
 *                CELLS list): the 8-byte CAN TX frame @0xFFFFC238 with its
 *                left/right sentinels, the TX-request flag 0xFFFFC241, the
 *                CAN-TX state/status/pending flags with sentinels, and the
 *                immo WAIT_STATE (0xFFFFC290) / RESP_BYTE (0xFFFFC294)
 *                inputs.
 *   <w0>..<w4>  the five 32-bit words read by the frame layouts: the rolling
 *                key @0xFFFFC278 (id 0x07) and the four key slots
 *                @0xFFFFC24C / 0x250 / 0x254 / 0x258 (id 0x09, sel 1..4).
 *
 * The oracle re-implements only the *caller-side* set-up: it mmap()s the page
 * backing the immobilizer RAM (same MAP_FIXED trick as tests/host_oracle.c and
 * the immo sibling oracles), seeds every compared cell with the vector values,
 * runs the reconstructed function, and prints the final state of every cell.
 * It contains NO copy of the function logic — that lives solely in the
 * reconstructed source under test.
 *
 * The 32-bit words are seeded/read through native uint32_t: on the little-
 * endian host the volatile access stores/loads the same NUMBER the big-endian
 * emulator stores/loads (cf. the word cells in the immo oracles).  The
 * function's byte extraction is written with shifts (v>>24 / v>>16 / v>>8 /
 * v), which produce the ROM's big-endian bytes on both endiannesses (the
 * rx8_get_maf_sensor_value.c pattern).
 *
 * All addresses fall inside the single 0xFFFFC000..0xFFFFCFFF page of the
 * 32 KB on-chip RAM window (0xFFFF6000..0xFFFFDFFF), well above
 * mmap_min_addr on this host.
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

#include "rx8_samples.h"

/* rx8_message_queue_state_dispatcher_369b8 is not declared in rx8_samples.h —
 * the reconstructed sources are dropped in without touching the shared
 * header. */
void rx8_message_queue_state_dispatcher_369b8(uint8_t cmd);

/* ---- The 21 compared byte cells (order matches the harness). ----------- */
static const uintptr_t CELL[21] = {
    0xFFFFC237u,                                 /* sentinel left of frame  */
    0xFFFFC238u, 0xFFFFC239u, 0xFFFFC23Au,       /* CAN TX frame buf[0..2]  */
    0xFFFFC23Bu, 0xFFFFC23Cu, 0xFFFFC23Du,       /* frame buf[3..5]         */
    0xFFFFC23Eu, 0xFFFFC23Fu,                    /* frame buf[6..7]         */
    0xFFFFC240u,                                 /* sentinel (CAN TX flag)  */
    0xFFFFC241u,                                 /* CAN TX request (=1)     */
    0xFFFFC28Eu,                                 /* sentinel (state byte)   */
    0xFFFFC28Fu,                                 /* CAN TX state (=0)       */
    0xFFFFC290u,                                 /* WAIT_STATE / slot sel   */
    0xFFFFC294u,                                 /* RESP_BYTE               */
    0xFFFFC295u,                                 /* sentinel                */
    0xFFFFC296u,                                 /* CAN TX status (=0)      */
    0xFFFFC297u,                                 /* sentinel                */
    0xFFFFC298u,                                 /* sentinel                */
    0xFFFFC299u,                                 /* CAN TX pending (=1)     */
    0xFFFFC29Au,                                 /* sentinel                */
};
/* ---- The five compared 32-bit words (order matches the harness). ------- */
static const uintptr_t WORD[5] = {
    0xFFFFC278u,                                 /* rolling key (id 0x07)   */
    0xFFFFC24Cu, 0xFFFFC250u,                    /* key slots 0..1          */
    0xFFFFC254u, 0xFFFFC258u,                    /* key slots 2..3          */
};

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
    char line[512];

    /* Back the on-chip-RAM page 0xFFFFC000 — covers every cell/word below. */
    map_page(0xFFFFC000u);

    while (fgets(line, sizeof line, stdin)) {
        unsigned long cmd, b[21], w[5];
        int i;

        if (sscanf(line,
                   "imsg %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx "
                   "%lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx "
                   "%lx",
                   &cmd, &b[0],  &b[1],  &b[2],  &b[3],  &b[4],  &b[5],
                   &b[6],  &b[7],  &b[8],  &b[9],  &b[10], &b[11], &b[12],
                   &b[13], &b[14], &b[15], &b[16], &b[17], &b[18], &b[19],
                   &b[20], &w[0],  &w[1],  &w[2],  &w[3],  &w[4]) == 27) {
            for (i = 0; i < 21; i++)
                *(volatile uint8_t *)(uintptr_t)CELL[i] = (uint8_t)b[i];
            for (i = 0; i < 5; i++)
                *(volatile uint32_t *)(uintptr_t)WORD[i] = (uint32_t)w[i];

            rx8_message_queue_state_dispatcher_369b8((uint8_t)cmd);

            for (i = 0; i < 21; i++)
                printf("%02X ", (unsigned)*(volatile uint8_t *)(uintptr_t)CELL[i]);
            for (i = 0; i < 5; i++)
                printf("%08lX%c",
                       (unsigned long)*(volatile uint32_t *)(uintptr_t)WORD[i],
                       i == 4 ? '\n' : ' ');
        } else {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
    }
    return 0;
}

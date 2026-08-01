/* ============================================================================
 * oracle_alternating_sensor_sm.c  —  host rig for
 *                                       rx8_alternating_sensor_sm @0x5D34C
 * ============================================================================
 * Compile together with samples/src/rx8_alternating_sensor_sm.c and pipe test
 * vectors on stdin; one vector per line, whitespace-separated hex tokens:
 *
 *     sm <mask> <st> <magic> <src> <cnt> <inp> <latch> <ptrcell> <cmd>
 *                                       -> <ret> <st> <latch> <ptrcell>
 *
 * The oracle re-implements only the *caller-side* set-up: it mmap()s the pages
 * backing the SM descriptor (mask @0x6020C, output-pointer @0x60210) and the
 * on-chip RAM cells (0xFFFFD350..0xFFFFD400 window) — same MAP_FIXED trick as
 * tests/host_oracle.c and c/tests/test_alt_sensor_sm_5D34C.py — seeds the
 * pre-state bytes, runs the reconstructed C and prints the return value plus
 * the three side-effected cells.  It contains NO copy of the function logic —
 * that lives solely in the reconstructed source under test.
 *
 * The stored output pointer is fixed to 0xFFFFD400 (PTR_CELL), matching the
 * verified lift test; the harness seeds the same 32-bit pointer on the
 * emulator side, so the *ptr side effect lands in a comparable cell.
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

#include "rx8_samples.h"

/* rx8_alternating_sensor_sm is not (yet) declared in rx8_samples.h — the
 * reconstructed sources are dropped in without touching the shared header. */
uint8_t rx8_alternating_sensor_sm(uint8_t cmd);

#define SM_MASK_ADDR  0x6020Cu          /* u8 sensor mask (SM_BASE + 8)    */
#define SM_PTR_ADDR   0x60210u          /* u32 stored output pointer       */
#define ST_ADDR       0xFFFFD355u       /* u8 state byte                   */
#define MAGIC_ADDR    0xFFFFD350u       /* u16 magic word (0x172D)         */
#define INP_ADDR      0xFFFFD3A8u       /* u8 sensor input byte            */
#define CNT_ADDR      0xFFFFD354u       /* u8 count byte                   */
#define SRC_ADDR      0xFFFFD352u       /* u16 source word                 */
#define LATCH_ADDR    0xFFFFD385u       /* u8 output latch                 */
#define PTR_CELL      0xFFFFD400u       /* u8 output byte behind SM_PTR    */

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

    /* 0x60204 lives in the flash-shadow region of the SH-2E address map and
     * is above mmap_min_addr on this host; 0xFFFFD000 backs all the RAM
     * cells 0xFFFFD350..0xFFFFD400. */
    map_page(SM_MASK_ADDR);
    map_page(ST_ADDR);

    while (fgets(line, sizeof line, stdin)) {
        unsigned long mask, st, magic, src, cnt, inp, latch, ptrcell, cmd;

        if (sscanf(line, "sm %lx %lx %lx %lx %lx %lx %lx %lx %lx",
                   &mask, &st, &magic, &src, &cnt, &inp, &latch, &ptrcell,
                   &cmd) == 9) {
            *(volatile uint8_t  *)(uintptr_t)SM_MASK_ADDR = (uint8_t)mask;
            *(volatile uint32_t *)(uintptr_t)SM_PTR_ADDR  = (uint32_t)PTR_CELL;
            *(volatile uint8_t  *)(uintptr_t)ST_ADDR      = (uint8_t)st;
            *(volatile uint16_t *)(uintptr_t)MAGIC_ADDR   = (uint16_t)magic;
            *(volatile uint16_t *)(uintptr_t)SRC_ADDR     = (uint16_t)src;
            *(volatile uint8_t  *)(uintptr_t)CNT_ADDR     = (uint8_t)cnt;
            *(volatile uint8_t  *)(uintptr_t)INP_ADDR     = (uint8_t)inp;
            *(volatile uint8_t  *)(uintptr_t)LATCH_ADDR   = (uint8_t)latch;
            *(volatile uint8_t  *)(uintptr_t)PTR_CELL     = (uint8_t)ptrcell;

            uint8_t ret = rx8_alternating_sensor_sm((uint8_t)cmd);
            printf("%02X %02X %02X %02X\n", ret,
                   *(volatile uint8_t *)(uintptr_t)ST_ADDR,
                   *(volatile uint8_t *)(uintptr_t)LATCH_ADDR,
                   *(volatile uint8_t *)(uintptr_t)PTR_CELL);
        } else {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
    }
    return 0;
}

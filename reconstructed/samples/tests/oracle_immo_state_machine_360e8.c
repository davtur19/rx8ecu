/* ============================================================================
 * oracle_immo_state_machine_360e8.c  —  host test rig for
 *                                       rx8_immo_state_machine @0x360E8
 * ============================================================================
 * Compile together with src/rx8_immo_state_machine_360e8.c (see
 * harness_immo_state_machine_360e8.py) and pipe test vectors on stdin; one
 * vector per line, whitespace-separated hex tokens:
 *
 *     imsm <b0> <b1> ... <b25> <w>  ->  <b0'> ... <b25'> <w'> <m0>...<m4>
 *
 *   26 byte cells (ordered; see the harness for the address list) covering
 *   every on-chip RAM byte the dispatcher can touch plus sentinels pinning
 *   store count/width: the CAN TX byte 0xFFFFC240 (sub==2 path), the immo
 *   state block 0xFFFFC28C..0xFFFFC29B (state byte, substate, resp byte,
 *   goodstate ctr/flag, seed-active byte) and the E2[0x1E] working copy
 *   0xFFFFC2F2; then <w>, the 16-bit seed-refresh timer at 0xFFFFC286
 *   (written with 0x02EE in the sub==2 path).  All are backed by one
 *   mmap(MAP_FIXED) page (page 0xFFFFC000 — the same trick as
 *   tests/host_oracle.c), so the volatile fixed-address pointers in the
 *   sample compile and fault-free on the host.
 *
 *   The word cell is seeded/read through a native uint16_t (the ROM's
 *   big-endian `mov.w` and the host's native store produce the same NUMBER;
 *   the harness compares the numeric value, exactly like
 *   oracle_immo_bad_state_set.c compares its 16-bit timeout).
 *
 * Trailing marker tokens, written by the stubbed handlers (sentinel 0x5A if
 * the handler never ran):
 *   <m0> rx8_immo_bad_state_set ran   (= 1)
 *   <m1> rx8_immo_msg_queue cmd       (= 0x01 or 0x07)
 *   <m2> rx8_immo_set_light on        (= 0x01 or 0x00)
 *   <m3> rx8_immo_get_seed ran        (= 4)
 *   <m4> rx8_immo_wait_for_key ran    (= 5)
 *
 * The oracle contains NO copy of the function logic — that lives solely in
 * the reconstructed source under test.  It only mirrors the caller-side
 * set-up: seed the cells, run the function, report cells + dispatch markers.
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

#include "rx8_samples.h"

/* Prototype is NOT in rx8_samples.h (sample project convention: only the
 * verified "public" leaves are listed there); declared here for the rig. */
void rx8_immo_state_machine_360e8(void);

/* ---- Stubs of the ROM's handlers, called at the dispatch boundary. ----
 * On the target these are the real ROM functions (0x365B8 / 0x369B8 /
 * 0x263C8 / 0x3664E / 0x35F92); here they only record the dispatch so the
 * harness can compare the call boundary bit-exactly. */
static volatile uint8_t m_bad   = 0x5A;   /* rx8_immo_bad_state_set ran */
static volatile uint8_t m_msg   = 0x5A;   /* rx8_immo_msg_queue cmd     */
static volatile uint8_t m_light = 0x5A;   /* rx8_immo_set_light on      */
static volatile uint8_t m_seed  = 0x5A;   /* rx8_immo_get_seed ran      */
static volatile uint8_t m_wait  = 0x5A;   /* rx8_immo_wait_for_key ran  */

void rx8_immo_bad_state_set(void)          { m_bad = 1; }
void rx8_immo_msg_queue(uint8_t cmd)       { m_msg = cmd; }
void rx8_immo_set_light(uint8_t on)        { m_light = on; }
void rx8_immo_get_seed(void)               { m_seed = 4; }
void rx8_immo_wait_for_key(void)           { m_wait = 5; }

/* ---- The 26 compared byte cells (order matches the harness). ---------- */
static const uintptr_t CELL[26] = {
    0xFFFFC23Fu, 0xFFFFC240u, 0xFFFFC241u,          /* CAN TX data + sentinels */
    0xFFFFC285u,                                    /* sentinel left of timer  */
    0xFFFFC28Cu, 0xFFFFC28Du, 0xFFFFC28Eu, 0xFFFFC28Fu,
    0xFFFFC290u, 0xFFFFC291u, 0xFFFFC292u, 0xFFFFC293u, 0xFFFFC294u,
    0xFFFFC295u, 0xFFFFC296u, 0xFFFFC297u, 0xFFFFC298u, 0xFFFFC299u,
    0xFFFFC29Au, 0xFFFFC29Bu,
    0xFFFFC29Eu, 0xFFFFC29Fu, 0xFFFFC2A0u,          /* seed active + sentinels */
    0xFFFFC2F1u, 0xFFFFC2F2u, 0xFFFFC2F3u,          /* E2[0x1E] copy + sents   */
};
#define WORD_SEED_ADDR 0xFFFFC286u                  /* 16-bit seed timer      */

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

    /* Every compared cell lives in the single 0xFFFFC000..0xFFFFCFFF page. */
    map_page(0xFFFFC000u);

    while (fgets(line, sizeof line, stdin)) {
        unsigned long v[26], w;
        if (sscanf(line,
                   "imsm %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx "
                   "%lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx",
                   &v[0],  &v[1],  &v[2],  &v[3],  &v[4],  &v[5],  &v[6],
                   &v[7],  &v[8],  &v[9],  &v[10], &v[11], &v[12], &v[13],
                   &v[14], &v[15], &v[16], &v[17], &v[18], &v[19], &v[20],
                   &v[21], &v[22], &v[23], &v[24], &v[25], &w) == 27) {
            int i;
            for (i = 0; i < 26; i++)
                *(volatile uint8_t *)(uintptr_t)CELL[i] = (uint8_t)v[i];
            *(volatile uint16_t *)(uintptr_t)WORD_SEED_ADDR = (uint16_t)w;

            m_bad = m_msg = m_light = m_seed = m_wait = 0x5A;
            rx8_immo_state_machine_360e8();

            for (i = 0; i < 26; i++)
                printf("%02X ", (unsigned)*(volatile uint8_t *)(uintptr_t)CELL[i]);
            printf("%04X %02X %02X %02X %02X %02X\n",
                   (unsigned)*(volatile uint16_t *)(uintptr_t)WORD_SEED_ADDR,
                   (unsigned)m_bad, (unsigned)m_msg,
                   (unsigned)m_light, (unsigned)m_seed, (unsigned)m_wait);
        } else {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
    }
    return 0;
}

/*
 * link_m6_crank.c — Link pilot m6 (13th pilot): compile-link-run against the
 * REAL crank path in firmware/c/engine.c — crank_timing_update,
 * crank_position_state_machine, crank_sync_acquire, crank_gap_detect and
 * rotor_position_synchronization — not a model replica.
 *
 * Mechanism proof: links the real engine.c TU (with -DFW_HOST_TEST so the
 * host-only crank fixture accessors are compiled in), so a firmware revert
 * of any covered fix fails this binary at run time, and a signature change
 * fails at compile time (extern decls via engine.h).
 *
 * Scenarios (all mutation-proven, see the re-proof in the commit message):
 *   S1 crank_timing_update x28 — saturating ISR tooth counter + FULL_SYNC
 *      arms: tooth_pos holds 0x5A after 9 calls, ==2 at count 0x0A
 *      (call 10) and at count 0x1C (call 28); prev_ratio captures ratio_r.
 *      Kills: wrap-20 revert of `crank_tooth_count++` (the 0x1C arm goes
 *      unreachable), prev_ratio store drop.
 *   S2 crank_sync_acquire(6), engine not running — gap arm: gap_detect_r
 *      0->1, teeth_since==rotor_offset(6), and gap_ctr primed 1 STAYS 1.
 *      The gap_ctr-stays-1 check is the MANDATORY :412 discriminator:
 *      teeth_since==6 alone does NOT kill the `gap_r == 0xFF` revert
 *      (the gap_ctr==0 -> teeth_since=rotor_offset tail fallback masks
 *      it). No-gap arm: gap_detect_r 1->0, gap_ctr 0x01->0, teeth_since
 *      kept.
 *   S3 engine-running path — gap_ctr toggles 0->1->0 with rotor_offset 0,
 *      stays untouched with rotor_offset 6. Kills: :429 revert,
 *      stuck-at-1, unconditional toggle.
 *   S4 FSM out-of-domain clamp — sync_counter primed 0x24 (>3; priming
 *      <=3 would make the clamp tautological, the h4 F1 lesson) is written
 *      back 0. Kills: M1 bound revert `state > 3` -> `state > 0x24`.
 *   S5 FSM transitions — IDLE+tooth -> 1; IDLE no-tooth stays 0;
 *      SEARCHING+gap -> (sync_counter 2, tooth_pos 3) with byte_store
 *      0x77->0; PARTIAL_SYNC ratio>=limit -> 1 (page 0x75000). Kills:
 *      `>=`->`<` revert, always-transition, transition removal.
 *   S6 rotor_position_synchronization at counts 9/10/15/255 ->
 *      A/3, B/0, B/5, B/5 plus global counter untouched (C3-followup
 *      purity). Kills: `local < 10` -> `<= 10`,
 *      `% TRIGGER_TOTAL_TEETH` -> `% 6`, old else-branch counter reset.
 *
 * Host execution boundary:
 *   - Zero stubs: engine.c has no undefined externs (`nm -u engine.o`
 *     clean) — exactly like h4/dwell.
 *   - MMIO is real: four mmap(MAP_FIXED) 4 KiB pages, every load/store
 *     executes for real against mapped memory:
 *       0xFFFF9000 — sync mirrors 0xFFFF9F95..0xFFFF9FCF (first user of
 *                    this page; no collision with the 12 landed pilots);
 *       0xFFFFF000 — timer capture 0xFFFFF434 (same page as m4);
 *       0x6C000    — ROM gap-ratio limit 0x6CF5C stand-in (m7's flash
 *                    sandbox is 0x70000, no clash; each pilot is its own
 *                    process anyway);
 *       0x75000    — ROM PARTIAL_SYNC limit 0x75184 stand-in.
 *   - DOCUMENTED COVERAGE GAP: page 0xD000 (ROM rotor table at 0xDA05,
 *     read by the `sync_flag_1 == 1` tails in crank_timing_update and
 *     crank_position_state_machine) is host-blocked by
 *     mmap_min_addr=65536 (MAP_FIXED below 64 KiB fails). Every scenario
 *     keeps sync_flag_1 (0xFFFF9FA1) == 0 so the tail — delta_ts_r /
 *     last_ts_r update and the tail clamp — never executes; asserts that
 *     it STAYED 0 are placed where the tail is in reach. Note 0xFFFF9FA1
 *     doubles as `search_cnt` in the SEARCHING branch (engine.c:192).
 *   - Accessors: crank_tooth_count / crank_rotor_id /
 *     crank_rotor_position are file statics with no production getter,
 *     and the ISR counter saturates at 0xFF (S1 consumes 0->0x1C before
 *     S6 needs 9/10/15/255, so the sequence cannot be driven by
 *     crank_timing_update() calls alone) — -DFW_HOST_TEST exposes
 *     setCrankToothCount_forHostTest / getCrankRotor_forHostTest
 *     (engine.c/.h, h4 precedent), compiled out of every normal build.
 *
 * Deliberately NOT covered: dwell (owned by link_h4_dwell), pipeline
 * stubs, omp_control_task, main_engine_cycle_10ms (needs page
 * 0xFFFFA000 — out of scope).
 *
 * Build (see firmware/tests/Makefile link-check):
 *   gcc -std=c11 -Wall -Wextra -Werror -O2 -I../include -DFW_HOST_TEST \
 *       link/link_m6_crank.c ../c/engine.c -o /tmp/fwtest/link_m6_crank
 */
#include <stdint.h>
#include <stdio.h>
#include <sys/mman.h>

#include "engine.h"

#ifndef FW_HOST_TEST
#error "link_m6_crank must build with -DFW_HOST_TEST (crank fixture accessors)"
#endif

/* Contract values the rotor map divides by — a header revert breaks the
 * build here, not just the run. */
_Static_assert(TRIGGER_TOTAL_TEETH == 20, "TRIGGER_TOTAL_TEETH revert");
_Static_assert(TRIGGER_TEETH_PER_ROTOR == 6, "TRIGGER_TEETH_PER_ROTOR revert");

/* MMIO byte/word addresses, pinned as literals: engine.c declares its
 * sync mirrors as file-scope pointers with BARE literals (NOT header
 * macros), so a firmware move of any of them must also move these pins or
 * the scenario checks below fail loudly. All 0xFFFF9xxx addresses share
 * the mapped 0xFFFF9000 page (offsets 0xF95..0xFCF). */
#define M6_SYNC_COUNTER  0xFFFF9F95u /* FSM state byte           */
#define M6_ENGINE_RUN    0xFFFF9F96u /* engine-running flag      */
#define M6_SYNC_FLAG_1   0xFFFF9FA1u /* 0xDA05-tail guard; also
                                      * `search_cnt` (engine.c:192) */
#define M6_LAST_TOOTH_R  0xFFFF9FA2u /* last tooth (PARTIAL prev) */
#define M6_TOOTH_POS     0xFFFF9FA3u /* tooth position state      */
#define M6_BYTE_STORE    0xFFFF9FA4u /* SEARCHING progress byte   */
#define M6_RATIO_R       0xFFFF9FB0u /* dword ratio               */
#define M6_PREV_RATIO    0xFFFF9FB4u /* dword previous ratio      */
#define M6_GAP_RATIO     0xFFFF9FBCu /* dword gap compare ratio   */
#define M6_SYNC_STATE    0xFFFF9FC0u /* sync_state (init gate)    */
#define M6_TOOTH_CTR     0xFFFF9FC3u /* tooth event counter       */
#define M6_GAP_INPUT     0xFFFF9FC7u /* counter_inc_and_copy      */
#define M6_GAP_CTR       0xFFFF9FC9u /* gap toggle latch          */
#define M6_TEETH_SINCE   0xFFFF9FCAu /* teeth_since byte          */
#define M6_GAP_DETECT_R  0xFFFF9FCBu /* stored gap result (0/1)   */
#define M6_TIMER_CAPTURE 0xFFFFF434u /* ATU timer capture (page F) */
#define M6_ROM_GAP_LIMIT 0x0006CF5Cu /* ROM limit stand-in (0x6C) */
#define M6_ROM_PARTIAL   0x00075184u /* ROM limit stand-in (0x75) */

#define M6_PAGE_LEN 0x1000u

static int failures = 0;

#define CHECK(cond, ...) do { \
    if (!(cond)) { printf("FAIL: "); printf(__VA_ARGS__); printf("\n"); failures++; } \
} while (0)

static volatile uint8_t *m6_u8(uint32_t addr)
{
    return (volatile uint8_t *)(uintptr_t)addr;
}

static volatile uint32_t *m6_u32(uint32_t addr)
{
    return (volatile uint32_t *)(uintptr_t)addr;
}

/* Map one 4 KiB page MAP_FIXED; return 0 (with a FAIL line) on error. */
static int m6_map_page(uint32_t base)
{
    void *p = mmap((void *)(uintptr_t)base, M6_PAGE_LEN,
                   PROT_READ | PROT_WRITE,
                   MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED, -1, 0);
    if (p != (void *)(uintptr_t)base) {
        printf("FAIL: mmap(0x%08X) failed\n", base);
        return 0;
    }
    return 1;
}

/* S6 helper: set the file-static tooth count, run the real map, read back
 * all three statics. Out-params are primed 0xFF (non-zero sentinel, the
 * h4 F1 pattern): a getter that fails to write leaves 0xFF, so even the
 * zero-expects below (rotor id 0, face 0) follow a non-zero prime. */
static void s6_rotor_case(uint8_t count, uint8_t want_id, uint8_t want_pos)
{
    uint8_t tc = 0xFF, rid = 0xFF, rpos = 0xFF;

    setCrankToothCount_forHostTest(count);
    rotor_position_synchronization();
    getCrankRotor_forHostTest(&tc, &rid, &rpos);
    CHECK(tc == count && rid == want_id && rpos == want_pos,
          "S6 count %u -> rotor %c face %u (got count %u, %c/%u)",
          (unsigned)count, want_id ? 'B' : 'A', (unsigned)want_pos,
          (unsigned)tc, rid ? 'B' : 'A', (unsigned)rpos);
}

int main(void)
{
    /* Four MAP_FIXED pages; any failure aborts (scoping probe precedent). */
    if (!m6_map_page(0xFFFF9000u) || !m6_map_page(0xFFFFF000u) ||
        !m6_map_page(0x0006C000u) || !m6_map_page(0x00075000u)) {
        return 1;
    }

    /* ---------- S1: ISR tooth counter + FULL_SYNC arms ------------------ */
    *m6_u32(M6_TIMER_CAPTURE) = 0x10000000u;
    *m6_u32(M6_RATIO_R) = 0xDEADBEEFu;
    *m6_u8(M6_SYNC_COUNTER) = 3;  /* FULL_SYNC: FSM arms on 0x0A / 0x1C */
    *m6_u8(M6_SYNC_FLAG_1) = 0;   /* never enter the 0xDA05 tail */
    *m6_u8(M6_TOOTH_POS) = 0x5A;  /* non-zero prime: must HOLD until an arm */
    *m6_u8(M6_TOOTH_CTR) = 0;
    *m6_u8(M6_ENGINE_RUN) = 0;
    setCrankToothCount_forHostTest(0); /* deterministic start for 0x0A/0x1C */

    for (int i = 0; i < 9; i++)
        crank_timing_update();
    CHECK(*m6_u8(M6_TOOTH_POS) == 0x5A,
          "S1 tooth_pos holds 0x5A after 9 ISR (count not yet 0x0A), got 0x%02X",
          (unsigned)*m6_u8(M6_TOOTH_POS));
    CHECK(*m6_u32(M6_PREV_RATIO) == 0xDEADBEEFu,
          "S1 prev_ratio captured ratio_r (0xDEADBEEF), got 0x%08X",
          (unsigned)*m6_u32(M6_PREV_RATIO));
    crank_timing_update(); /* count == 0x0A */
    CHECK(*m6_u8(M6_TOOTH_POS) == 2,
          "S1 tooth_pos==2 at count 0x0A arm, got 0x%02X",
          (unsigned)*m6_u8(M6_TOOTH_POS));
    *m6_u8(M6_TOOTH_POS) = 0x5A;  /* reprime non-zero before the next arm */
    for (int i = 0; i < 18; i++)
        crank_timing_update(); /* count == 0x1C */
    CHECK(*m6_u8(M6_TOOTH_POS) == 2,
          "S1 tooth_pos==2 at count 0x1C arm (kills wrap-20), got 0x%02X",
          (unsigned)*m6_u8(M6_TOOTH_POS));
    CHECK(*m6_u8(M6_SYNC_FLAG_1) == 0,
          "S1 sync_flag_1 stayed 0 (0xDA05 tail never entered)");

    /* ---------- S2: M6 gap sentinel, engine-not-running path ------------ */
    *m6_u32(M6_ROM_GAP_LIMIT) = 0x100u; /* 0x6CF5C limit stand-in */
    *m6_u32(M6_GAP_RATIO) = 0x1000u;    /* ratio > limit */
    *m6_u8(M6_SYNC_STATE) = 1;          /* skip the init arm */
    *m6_u8(M6_TOOTH_POS) = 1;           /* tooth_pos == 1 arm */
    *m6_u8(M6_ENGINE_RUN) = 0;          /* engine not running */
    *m6_u8(M6_GAP_INPUT) = 5;           /* gap input counter != 0 -> gap */
    *m6_u8(M6_GAP_DETECT_R) = 0;        /* expect 1: crank_gap_detect ran */
    *m6_u8(M6_GAP_CTR) = 1;             /* MUST stay 1: the :412 killer */
    *m6_u8(M6_TEETH_SINCE) = 0xAA;       /* non-zero prime */
    crank_sync_acquire(6);
    CHECK(*m6_u8(M6_GAP_DETECT_R) == 1,
          "S2 gap_detect_r==1 stored by real crank_gap_detect, got 0x%02X",
          (unsigned)*m6_u8(M6_GAP_DETECT_R));
    CHECK(*m6_u8(M6_TEETH_SINCE) == 6,
          "S2 teeth_since==rotor_offset(6) on gap, got 0x%02X",
          (unsigned)*m6_u8(M6_TEETH_SINCE));
    /* Discriminator for the :412 site: the gap arm stores teeth_since
     * WITHOUT touching gap_ctr; the `gap_r == 0xFF` revert takes the
     * else-clear instead, which the teeth_since tail fallback then masks.
     * gap_ctr=1 exposes it. */
    CHECK(*m6_u8(M6_GAP_CTR) == 1,
          "S2 gap_ctr untouched on gap (kills M6 :412 ==0xFF revert), got 0x%02X",
          (unsigned)*m6_u8(M6_GAP_CTR));

    /* No-gap arm: counter 0 -> gap_detect_r 1->0 (zero-expect after
     * non-zero prime), gap_ctr 0x01->0, teeth_since kept at 6. */
    *m6_u8(M6_GAP_INPUT) = 0;
    *m6_u8(M6_GAP_CTR) = 0x01; /* non-zero prime */
    crank_sync_acquire(6);
    CHECK(*m6_u8(M6_GAP_DETECT_R) == 0,
          "S2 gap_detect_r==0 when counter==0 (zero-expect after 1), got 0x%02X",
          (unsigned)*m6_u8(M6_GAP_DETECT_R));
    CHECK(*m6_u8(M6_GAP_CTR) == 0,
          "S2 gap_ctr cleared on no-gap (zero-expect after 0x01), got 0x%02X",
          (unsigned)*m6_u8(M6_GAP_CTR));
    CHECK(*m6_u8(M6_TEETH_SINCE) == 6,
          "S2 teeth_since untouched on no-gap (stays 6), got 0x%02X",
          (unsigned)*m6_u8(M6_TEETH_SINCE));

    /* ---------- S3: engine-running gap toggle + rotor-offset gate ------- */
    *m6_u8(M6_ENGINE_RUN) = 1; /* engine running */
    *m6_u8(M6_GAP_INPUT) = 5;  /* gap present */
    *m6_u8(M6_GAP_CTR) = 0;    /* start of toggle sequence */
    crank_sync_acquire(0);
    CHECK(*m6_u8(M6_GAP_CTR) == 1,
          "S3 gap_ctr 0->1 toggle on running gap (kills M6 :429 revert), got 0x%02X",
          (unsigned)*m6_u8(M6_GAP_CTR));
    crank_sync_acquire(0);
    CHECK(*m6_u8(M6_GAP_CTR) == 0,
          "S3 gap_ctr 1->0 toggle back (kills stuck-at-1), got 0x%02X",
          (unsigned)*m6_u8(M6_GAP_CTR));
    *m6_u8(M6_GAP_CTR) = 1; /* non-zero prime */
    crank_sync_acquire(6);  /* rotor_offset 6: must NOT toggle */
    CHECK(*m6_u8(M6_GAP_CTR) == 1,
          "S3 gap_ctr untouched for rotor_offset 6 (kills unconditional toggle), got 0x%02X",
          (unsigned)*m6_u8(M6_GAP_CTR));
    CHECK(*m6_u8(M6_SYNC_FLAG_1) == 0,
          "S3 sync_flag_1 stayed 0 (0xDA05 tail never entered)");

    /* ---------- S4: FSM out-of-domain clamp write-back (M1) ------------- */
    *m6_u8(M6_SYNC_COUNTER) = 0x24; /* 36 > 3: the discriminator value
                                     * (priming <=3 makes the clamp
                                     * tautological — h4 F1 lesson) */
    *m6_u8(M6_TOOTH_CTR) = 0;
    *m6_u8(M6_SYNC_FLAG_1) = 0;
    crank_position_state_machine();
    CHECK(*m6_u8(M6_SYNC_COUNTER) == 0,
          "S4 sync_counter 0x24 clamped+written back to 0 (kills M1 >0x24 bound revert), got 0x%02X",
          (unsigned)*m6_u8(M6_SYNC_COUNTER));
    CHECK(*m6_u8(M6_SYNC_FLAG_1) == 0,
          "S4 sync_flag_1 stayed 0 (0xDA05 tail never entered)");

    /* ---------- S5: FSM transitions ------------------------------------- */
    *m6_u8(M6_SYNC_COUNTER) = 0;
    *m6_u8(M6_TOOTH_CTR) = 7; /* IDLE with tooth */
    crank_position_state_machine();
    CHECK(*m6_u8(M6_SYNC_COUNTER) == 1,
          "S5 IDLE->SEARCHING on first tooth, got 0x%02X",
          (unsigned)*m6_u8(M6_SYNC_COUNTER));
    *m6_u8(M6_SYNC_COUNTER) = 0;
    *m6_u8(M6_TOOTH_CTR) = 0; /* IDLE without tooth */
    crank_position_state_machine();
    CHECK(*m6_u8(M6_SYNC_COUNTER) == 0,
          "S5 IDLE stays 0 with no tooth (kills always-transition), got 0x%02X",
          (unsigned)*m6_u8(M6_SYNC_COUNTER));
    *m6_u8(M6_SYNC_COUNTER) = 1;
    *m6_u8(M6_TOOTH_CTR) = 0;      /* SEARCHING, tooth 0 */
    *m6_u8(M6_SYNC_FLAG_1) = 0;    /* search_cnt 0 >= tooth 0: not progressing
                                    * (0xFFFF9FA1 doubles as search_cnt) */
    *m6_u8(M6_BYTE_STORE) = 0x77;  /* non-zero prime */
    *m6_u8(M6_GAP_DETECT_R) = 1;   /* gap detected */
    *m6_u8(M6_TOOTH_POS) = 0x11;   /* non-zero prime: overwritten with 3 */
    crank_position_state_machine();
    CHECK(*m6_u8(M6_BYTE_STORE) == 0,
          "S5 search non-progression resets byte_store (zero-expect after 0x77), got 0x%02X",
          (unsigned)*m6_u8(M6_BYTE_STORE));
    CHECK(*m6_u8(M6_SYNC_COUNTER) == 2 && *m6_u8(M6_TOOTH_POS) == 3,
          "S5 SEARCHING+gap -> sync_counter 2, tooth_pos 3 (got %u/0x%02X)",
          (unsigned)*m6_u8(M6_SYNC_COUNTER), (unsigned)*m6_u8(M6_TOOTH_POS));
    *m6_u32(M6_ROM_PARTIAL) = 1u;       /* 0x75184 limit stand-in */
    *m6_u32(M6_RATIO_R) = 0xFFFFFFFFu;  /* ratio >= limit */
    *m6_u8(M6_SYNC_COUNTER) = 2;        /* PARTIAL_SYNC */
    *m6_u8(M6_TOOTH_CTR) = 5;
    *m6_u8(M6_LAST_TOOTH_R) = 0;        /* prev < tooth: progression ok */
    crank_position_state_machine();
    CHECK(*m6_u8(M6_SYNC_COUNTER) == 1,
          "S5 PARTIAL_SYNC ratio>=limit -> back to SEARCHING (kills >= revert), got %u",
          (unsigned)*m6_u8(M6_SYNC_COUNTER));
    CHECK(*m6_u8(M6_SYNC_FLAG_1) == 0,
          "S5 sync_flag_1 stayed 0 (0xDA05 tail never entered)");

    /* ---------- S6: rotor_position_synchronization map -------------------
     * No MMIO: the map touches only the file statics, read back through
     * the FW_HOST_TEST accessor (0xFF-sentinel-primed inside the helper). */
    s6_rotor_case(9, 0, 3);   /* 0..9: rotor A, face count%6 */
    s6_rotor_case(10, 1, 0);  /* kills <=10 revert and %6 revert */
    s6_rotor_case(15, 1, 5);  /* (15-10)%6 = 5 */
    s6_rotor_case(255, 1, 5); /* saturate: 255%20=15 -> B face 5, and the
                               * set count must survive the read path
                               * (C3-followup purity: the old else-branch
                               * reset the global counter here) */

    if (failures == 0) {
        printf("PASS link_m6_crank (real engine.c crank path TU)\n");
    } else {
        printf("%d FAILURES link_m6_crank\n", failures);
    }
    return failures != 0;
}

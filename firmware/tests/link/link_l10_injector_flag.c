/*
 * link_l10_injector_flag.c — Link pilot l10: compile-link-run against the
 * REAL dtc_injector_fault_check in firmware/c/dtc.c (L10 fault-flag store
 * on the fuel-cut early-return path, class M), not a model replica.
 *
 * Mechanism proof: links the real dtc.c TU, so a firmware revert of the L10
 * fix (the 0xFFFFC9A2 store inside the fuel-cut early return — dropping it
 * again leaves a stale latched fault behind) or of the normal-path tail
 * store, of the fault latch (`status_a || sec_check`), or of the
 * secondary-condition ordering (cond_2 override / fuel-cut before
 * secondary) fails this binary at run time; a signature change fails at
 * compile time (extern decl via dtc.h).
 *
 * Refactor-path coverage (the whole point of l10 scoping):
 *   - fuel-cut store: the early return at dtc.c:1003-1011 zeroes
 *     result_a/result_b AND stores the current `fault` into 0xFFFFC9A2 —
 *     the pre-L10 code skipped that store, so a previously latched 1
 *     survived a fuel-cut cycle as a stale fault;
 *   - normal-path tail store: fault flag written after the secondary
 *     conditions, results written before it;
 *   - fuel-cut gates out the secondary block (status_b/cond_1/cond_2 must
 *     NOT run when fuel_cut == 1);
 *   - cond_2 overrides the status_b/cond_1 result pair (r_a=1, r_b=0).
 *
 * Host execution boundary (two MMIO pages, mmap MAP_FIXED):
 *   - Zero stubs: dtc.c has no undefined externs (`nm -u dtc.o` clean) —
 *     exactly like the m2/h2 pilots of the same TU; no FW_HOST_TEST
 *     accessor needed (dtc_injector_fault_check is a public extern).
 *   - MMIO is real: the SH-2 RAM pages do not exist on the host (bare
 *     deref segfaults), so the test maps TWO 4 KiB pages with
 *     mmap(MAP_FIXED):
 *       0xFFFFC000 — injector cluster 0xFFFFC99C..0xFFFFC9BF
 *                    (cond_2/cond_1/status_a/status_b/result_b/fault/
 *                     result_a/sec_check);
 *       0xFFFFD000 — fuel-cut inhibit flag 0xFFFFD201.
 *     Every load/store the function performs then executes for real.
 *   - No constructor/init-time MMIO: dtc.c file-scope statics are plain
 *     zero-init (dtc_slot_count, dtc_backup_count).
 *   - Same unused-static relaxation as m2/h2 (dtc_primary_to_backup_promote;
 *     firmware sources untouched).
 *   - No ROM read: every 0x0xxxxx address in the function body appears in
 *     comments only (ROM:0x43476 / ROM:0x434A0 xrefs) — verified by
 *     extracting body literals before writing this file.
 *
 * Contract pins: dtc.h carries NO injector address macros (verified by
 * grep — the addresses live as literals in the dtc.c body), so the pins
 * are local constants + page-coverage _Static_asserts, m8-style; the
 * extern signature itself is the dtc.h compile-time contract.
 *
 * Proves (every assert killable; every zero-expect is primed nonzero
 * first — F1 lesson):
 *   (a) fuel-cut + latched fault (status_a=1): return 0, results zeroed
 *       (primed 0xEE), fault flag STORED 1 (primed 0);
 *   (b) fuel-cut + stale fault flag 1, no fault condition: fault flag
 *       cleared to 0 (primed 1 — the exact L10 stale-flag scenario),
 *       results zeroed (primed 0xEE);
 *   (c) normal path + fault: return 1, fault flag 1 (primed 0xEE),
 *       result_a 1 (primed 0), result_b 0 (primed 0xEE);
 *   (d) sec_check latches the fault like status_a: return 1, flag 1
 *       (primed 0xEE), result_a 1 (primed 0);
 *   (e) status_b path: return 0, flag 0 (primed 1), result_b 1
 *       (primed 0), result_a 0 (primed 0xEE);
 *   (f) cond_1 path: same shape as (e);
 *   (g) cond_2 overrides status_b: result_a 1 (primed 0), result_b 0
 *       (primed 0xEE);
 *   (h) fuel-cut + sec_check: fault still stored on the early return
 *       (flag primed 0 -> 1), results zeroed, return 0;
 *   (i) fuel-cut gates out secondary: status_b=1 must NOT set result_b
 *       (results primed 0xEE -> 0), flag primed 1 -> 0, return 0;
 *   (j) clean run: everything primed 0xEE -> all 0, return 0.
 *
 * Build (see firmware/tests/Makefile link-check):
 *   gcc -std=c11 -Wall -Wextra -Werror -Wno-error=unused-function -O2 \
 *       -I../include link/link_l10_injector_flag.c ../c/dtc.c \
 *       -o /tmp/fwtest/link_l10_injector_flag
 */
#include <stdint.h>
#include <stdio.h>
#include <sys/mman.h>

#include "dtc.h"

/* Extern declaration comes from the real dtc.h (linking the real dtc.c
 * TU): a signature change in firmware breaks this build. */

/* The injector RAM literals live in the dtc.c body (dtc.h has no macros
 * for them), so pin the addresses the test maps — a firmware move of the
 * cluster must also move this mapping or the asserts fail loudly. Each
 * pinned byte must sit inside ONE of the two mapped pages. */
#define L10_C_PAGE_BASE 0xFFFFC000u
#define L10_C_PAGE_LEN  0x1000u
#define L10_D_PAGE_BASE 0xFFFFD000u
#define L10_D_PAGE_LEN  0x1000u

#define L10_COND_2      0xFFFFC99Cu
#define L10_COND_1      0xFFFFC99Du
#define L10_STATUS_A    0xFFFFC99Fu
#define L10_STATUS_B    0xFFFFC9A0u
#define L10_RESULT_B    0xFFFFC9A1u
#define L10_FAULT       0xFFFFC9A2u
#define L10_RESULT_A    0xFFFFC9A3u
#define L10_SEC_CHECK   0xFFFFC9BFu
#define L10_FUEL_CUT    0xFFFFD201u

#define L10_IN_C(a) ((a) >= L10_C_PAGE_BASE && (a) < L10_C_PAGE_BASE + L10_C_PAGE_LEN)
#define L10_IN_D(a) ((a) >= L10_D_PAGE_BASE && (a) < L10_D_PAGE_BASE + L10_D_PAGE_LEN)

_Static_assert(L10_IN_C(L10_COND_2) && L10_IN_C(L10_COND_1) &&
               L10_IN_C(L10_STATUS_A) && L10_IN_C(L10_STATUS_B) &&
               L10_IN_C(L10_RESULT_B) && L10_IN_C(L10_FAULT) &&
               L10_IN_C(L10_RESULT_A) && L10_IN_C(L10_SEC_CHECK),
               "injector cluster outside mapped C page");
_Static_assert(L10_IN_D(L10_FUEL_CUT), "fuel-cut flag outside mapped D page");
_Static_assert(L10_FAULT == 0xFFFFC9A2u, "L10 fault-flag address revert");
_Static_assert(L10_FUEL_CUT == 0xFFFFD201u, "fuel-cut address revert");

static int failures = 0;

#define CHECK(cond, ...) do { \
    if (!(cond)) { printf("FAIL: "); printf(__VA_ARGS__); printf("\n"); failures++; } \
} while (0)

static volatile uint8_t *l10_u8(uint32_t addr)
{
    return (volatile uint8_t *)(uintptr_t)addr;
}

/* Zero inputs + secondary outputs; callers prime the fields they assert on
 * afterward (prime-before-zero rule applies to every asserted location). */
static void l10_reset_inputs(void)
{
    *l10_u8(L10_COND_2) = 0u;
    *l10_u8(L10_COND_1) = 0u;
    *l10_u8(L10_STATUS_A) = 0u;
    *l10_u8(L10_STATUS_B) = 0u;
    *l10_u8(L10_SEC_CHECK) = 0u;
    *l10_u8(L10_FUEL_CUT) = 0u;
}

/* Prime outputs to a value distinct from every possible store (fault/flag
 * stores are only ever 0 or 1; results too) so every post-call expect is
 * killable by a dropped store. */
static void l10_prime_outputs(uint8_t fault, uint8_t result_a, uint8_t result_b)
{
    *l10_u8(L10_FAULT) = fault;
    *l10_u8(L10_RESULT_A) = result_a;
    *l10_u8(L10_RESULT_B) = result_b;
}

int main(void)
{
    void *pc = mmap((void *)(uintptr_t)L10_C_PAGE_BASE, L10_C_PAGE_LEN,
                    PROT_READ | PROT_WRITE,
                    MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED, -1, 0);
    if (pc == (void *)-1) {
        printf("FAIL: mmap(0xFFFFC000) failed\n");
        return 1;
    }
    void *pd = mmap((void *)(uintptr_t)L10_D_PAGE_BASE, L10_D_PAGE_LEN,
                    PROT_READ | PROT_WRITE,
                    MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED, -1, 0);
    if (pd == (void *)-1) {
        printf("FAIL: mmap(0xFFFFD000) failed\n");
        return 1;
    }

    uint16_t rc;

    /* (a) fuel-cut + latched fault: flag primed 0 must become 1 (the L10
     * store runs); results primed 0xEE must zero; return 0. */
    l10_reset_inputs();
    l10_prime_outputs(0u, 0xEEu, 0xEEu);
    *l10_u8(L10_STATUS_A) = 1u;
    *l10_u8(L10_FUEL_CUT) = 1u;
    rc = dtc_injector_fault_check();
    CHECK(rc == 0, "fuel-cut+fault: rc=%u want 0", rc);
    CHECK(*l10_u8(L10_RESULT_A) == 0u && *l10_u8(L10_RESULT_B) == 0u,
          "fuel-cut+fault: results %02X/%02X want 0/0",
          *l10_u8(L10_RESULT_A), *l10_u8(L10_RESULT_B));
    CHECK(*l10_u8(L10_FAULT) == 1u,
          "fuel-cut+fault: flag %02X want 1 (L10 store dropped?)",
          *l10_u8(L10_FAULT));

    /* (b) fuel-cut + STALE flag 1, no fault condition: store must clear
     * it to 0 (exact L10 bug scenario); results primed 0xEE -> 0. */
    l10_reset_inputs();
    l10_prime_outputs(1u, 0xEEu, 0xEEu);
    *l10_u8(L10_FUEL_CUT) = 1u;
    rc = dtc_injector_fault_check();
    CHECK(rc == 0, "fuel-cut stale: rc=%u want 0", rc);
    CHECK(*l10_u8(L10_FAULT) == 0u,
          "fuel-cut stale: flag %02X want 0 (stale fault survived)",
          *l10_u8(L10_FAULT));
    CHECK(*l10_u8(L10_RESULT_A) == 0u && *l10_u8(L10_RESULT_B) == 0u,
          "fuel-cut stale: results %02X/%02X want 0/0",
          *l10_u8(L10_RESULT_A), *l10_u8(L10_RESULT_B));

    /* (c) normal path + fault: return 1, flag primed 0xEE -> 1,
     * result_a primed 0 -> 1, result_b primed 0xEE -> 0. */
    l10_reset_inputs();
    l10_prime_outputs(0xEEu, 0u, 0xEEu);
    *l10_u8(L10_STATUS_A) = 1u;
    rc = dtc_injector_fault_check();
    CHECK(rc == 1, "normal fault: rc=%u want 1", rc);
    CHECK(*l10_u8(L10_FAULT) == 1u,
          "normal fault: flag %02X want 1 (primed 0xEE)",
          *l10_u8(L10_FAULT));
    CHECK(*l10_u8(L10_RESULT_A) == 1u,
          "normal fault: result_a %02X want 1 (primed 0)",
          *l10_u8(L10_RESULT_A));
    CHECK(*l10_u8(L10_RESULT_B) == 0u,
          "normal fault: result_b %02X want 0 (primed 0xEE)",
          *l10_u8(L10_RESULT_B));

    /* (d) sec_check latches the fault like status_a. */
    l10_reset_inputs();
    l10_prime_outputs(0xEEu, 0u, 0xEEu);
    *l10_u8(L10_SEC_CHECK) = 1u;
    rc = dtc_injector_fault_check();
    CHECK(rc == 1, "sec_check fault: rc=%u want 1", rc);
    CHECK(*l10_u8(L10_FAULT) == 1u,
          "sec_check fault: flag %02X want 1 (primed 0xEE)",
          *l10_u8(L10_FAULT));
    CHECK(*l10_u8(L10_RESULT_A) == 1u,
          "sec_check fault: result_a %02X want 1 (primed 0)",
          *l10_u8(L10_RESULT_A));

    /* (e) status_b path: flag primed 1 -> 0, result_b primed 0 -> 1,
     * result_a primed 0xEE -> 0, return 0. */
    l10_reset_inputs();
    l10_prime_outputs(1u, 0xEEu, 0u);
    *l10_u8(L10_STATUS_B) = 1u;
    rc = dtc_injector_fault_check();
    CHECK(rc == 0, "status_b: rc=%u want 0", rc);
    CHECK(*l10_u8(L10_FAULT) == 0u,
          "status_b: flag %02X want 0 (primed 1)",
          *l10_u8(L10_FAULT));
    CHECK(*l10_u8(L10_RESULT_B) == 1u,
          "status_b: result_b %02X want 1 (primed 0)",
          *l10_u8(L10_RESULT_B));
    CHECK(*l10_u8(L10_RESULT_A) == 0u,
          "status_b: result_a %02X want 0 (primed 0xEE)",
          *l10_u8(L10_RESULT_A));

    /* (f) cond_1 path: same shape as (e). */
    l10_reset_inputs();
    l10_prime_outputs(1u, 0xEEu, 0u);
    *l10_u8(L10_COND_1) = 1u;
    rc = dtc_injector_fault_check();
    CHECK(rc == 0, "cond_1: rc=%u want 0", rc);
    CHECK(*l10_u8(L10_FAULT) == 0u,
          "cond_1: flag %02X want 0 (primed 1)",
          *l10_u8(L10_FAULT));
    CHECK(*l10_u8(L10_RESULT_B) == 1u,
          "cond_1: result_b %02X want 1 (primed 0)",
          *l10_u8(L10_RESULT_B));
    CHECK(*l10_u8(L10_RESULT_A) == 0u,
          "cond_1: result_a %02X want 0 (primed 0xEE)",
          *l10_u8(L10_RESULT_A));

    /* (g) cond_2 overrides status_b: result_a primed 0 -> 1,
     * result_b primed 0xEE -> 0. */
    l10_reset_inputs();
    l10_prime_outputs(1u, 0u, 0xEEu);
    *l10_u8(L10_STATUS_B) = 1u;
    *l10_u8(L10_COND_2) = 1u;
    rc = dtc_injector_fault_check();
    CHECK(rc == 0, "cond_2 override: rc=%u want 0", rc);
    CHECK(*l10_u8(L10_RESULT_A) == 1u,
          "cond_2 override: result_a %02X want 1 (primed 0)",
          *l10_u8(L10_RESULT_A));
    CHECK(*l10_u8(L10_RESULT_B) == 0u,
          "cond_2 override: result_b %02X want 0 (primed 0xEE)",
          *l10_u8(L10_RESULT_B));
    CHECK(*l10_u8(L10_FAULT) == 0u,
          "cond_2 override: flag %02X want 0 (primed 1)",
          *l10_u8(L10_FAULT));

    /* (h) fuel-cut + sec_check: the early-return store must land here too
     * (flag primed 0 -> 1); results primed 0xEE -> 0; return 0. */
    l10_reset_inputs();
    l10_prime_outputs(0u, 0xEEu, 0xEEu);
    *l10_u8(L10_SEC_CHECK) = 1u;
    *l10_u8(L10_FUEL_CUT) = 1u;
    rc = dtc_injector_fault_check();
    CHECK(rc == 0, "fuel-cut+sec: rc=%u want 0", rc);
    CHECK(*l10_u8(L10_FAULT) == 1u,
          "fuel-cut+sec: flag %02X want 1 (L10 store dropped?)",
          *l10_u8(L10_FAULT));
    CHECK(*l10_u8(L10_RESULT_A) == 0u && *l10_u8(L10_RESULT_B) == 0u,
          "fuel-cut+sec: results %02X/%02X want 0/0",
          *l10_u8(L10_RESULT_A), *l10_u8(L10_RESULT_B));

    /* (i) fuel-cut gates out the secondary block: status_b=1 must NOT set
     * result_b (results primed 0xEE must stay/be 0); flag primed 1 -> 0. */
    l10_reset_inputs();
    l10_prime_outputs(1u, 0xEEu, 0xEEu);
    *l10_u8(L10_STATUS_B) = 1u;
    *l10_u8(L10_FUEL_CUT) = 1u;
    rc = dtc_injector_fault_check();
    CHECK(rc == 0, "fuel-cut gates secondary: rc=%u want 0", rc);
    CHECK(*l10_u8(L10_RESULT_B) == 0u,
          "fuel-cut gates secondary: result_b %02X want 0 (secondary ran?)",
          *l10_u8(L10_RESULT_B));
    CHECK(*l10_u8(L10_RESULT_A) == 0u,
          "fuel-cut gates secondary: result_a %02X want 0",
          *l10_u8(L10_RESULT_A));
    CHECK(*l10_u8(L10_FAULT) == 0u,
          "fuel-cut gates secondary: flag %02X want 0 (primed 1)",
          *l10_u8(L10_FAULT));

    /* (j) clean run: every output primed 0xEE -> all 0, return 0. */
    l10_reset_inputs();
    l10_prime_outputs(0xEEu, 0xEEu, 0xEEu);
    rc = dtc_injector_fault_check();
    CHECK(rc == 0, "clean run: rc=%u want 0", rc);
    CHECK(*l10_u8(L10_FAULT) == 0u,
          "clean run: flag %02X want 0 (primed 0xEE)",
          *l10_u8(L10_FAULT));
    CHECK(*l10_u8(L10_RESULT_A) == 0u && *l10_u8(L10_RESULT_B) == 0u,
          "clean run: results %02X/%02X want 0/0",
          *l10_u8(L10_RESULT_A), *l10_u8(L10_RESULT_B));

    munmap(pc, L10_C_PAGE_LEN);
    munmap(pd, L10_D_PAGE_LEN);

    if (failures == 0) {
        printf("PASS link_l10_injector_flag (real dtc.c TU)\n");
    } else {
        printf("%d FAILURES link_l10_injector_flag\n", failures);
    }
    return failures != 0;
}

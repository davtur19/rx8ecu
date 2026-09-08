/*
 * test_l10_injector_flag.c — L10 regression: dtc_injector_fault_check must
 * write the fault flag at 0xFFFFC9A2 on ALL paths, including the fuel-cut
 * early return that used to skip the store (leaving a stale 1 behind).
 *
 * Firmware site: firmware/c/dtc.c dtc_injector_fault_check (fuel-cut arm
 *   vs the normal-path tail store). Provable statically: fault=1 set at
 *   entry, early return wrote result_a/b=0 and returned 0 without touching
 *   0xFFFFC9A2.
 *
 * Host-self-contained: RAM struct + check model mirroring the firmware,
 * including the L10 store on the fuel-cut path.
 *
 * Build:
 *   gcc -std=c11 -Wall -Wextra -Werror -O2 test_l10_injector_flag.c -o /tmp/fwtest/test_l10_injector_flag
 *   gcc ... -DTEST_BUGGY ... (must FAIL)
 */
#include <stdint.h>
#include <stdio.h>

struct inj_ram {
    uint8_t status_a;  /* 0xFFFFC99F */
    uint8_t status_b;  /* 0xFFFFC9A0 */
    uint8_t result_b;  /* 0xFFFFC9A1 */
    uint8_t fault;     /* 0xFFFFC9A2 */
    uint8_t result_a;  /* 0xFFFFC9A3 */
    uint8_t sec_check; /* 0xFFFFC9BF */
    uint8_t cond_1;    /* 0xFFFFC99D */
    uint8_t cond_2;    /* 0xFFFFC99C */
    uint8_t fuel_cut;  /* 0xFFFFD201 */
};

/* Mirror of dtc_injector_fault_check. */
static uint16_t model_check(struct inj_ram *r)
{
    uint8_t r_a = 0, r_b = 0;
    uint8_t fault = 0;

    if (r->status_a == 1 || r->sec_check == 1) {
        fault = 1;
        r_a = 1;
    }

    if (r->fuel_cut == 1) {
        r->result_a = 0;
        r->result_b = 0;
#ifndef TEST_BUGGY
        r->fault = (fault != 0) ? 1 : 0; /* L10: store on every path */
#endif
        return 0;
    }

    if (r->status_b == 1 || r->cond_1 == 1) {
        r_b = 1;
        r_a = 0;
    }
    if (r->cond_2 == 1) {
        r_a = 1;
        r_b = 0;
    }

    r->result_a = r_a;
    r->result_b = r_b;
    r->fault = (fault != 0) ? 1 : 0;

    return (fault != 0) ? 1 : 0;
}

static int failures = 0;

#define CHECK(cond, ...) do { \
    if (!(cond)) { printf("FAIL: "); printf(__VA_ARGS__); printf("\n"); failures++; } \
} while (0)

int main(void)
{
    struct inj_ram r;

    /* Fuel-cut with a latched fault: flag must be (re)written to 1 and
     * results zeroed — the write must happen, not the stale value by luck.
     * Pre-seed a stale 0 to prove the store runs. */
    r = (struct inj_ram){ .status_a = 1, .fuel_cut = 1, .fault = 0 };
    CHECK(model_check(&r) == 0, "fuel-cut must return 0");
    CHECK(r.result_a == 0 && r.result_b == 0, "fuel-cut must zero results");
    CHECK(r.fault == 1, "fuel-cut path must write fault=1 (got %u)", r.fault);

    /* Fuel-cut with no fault but a STALE 1: the store must clear it. This
     * is the exact stale-flag scenario from the bug report. */
    r = (struct inj_ram){ .fault = 1, .fuel_cut = 1 };
    CHECK(model_check(&r) == 0, "fuel-cut must return 0");
    CHECK(r.fault == 0, "fuel-cut path must clear stale fault (got %u)",
          r.fault);

    /* Normal path unchanged: fault latches, results follow conditions. */
    r = (struct inj_ram){ .status_a = 1 };
    CHECK(model_check(&r) == 1, "normal fault must return 1");
    CHECK(r.fault == 1 && r.result_a == 1, "normal fault store");
    r = (struct inj_ram){ 0 };
    CHECK(model_check(&r) == 0, "clean run must return 0");
    CHECK(r.fault == 0, "clean run must store 0");

    if (failures == 0) {
        printf("PASS l10_injector_flag\n");
    } else {
        printf("%d FAILURES l10_injector_flag\n", failures);
    }
    return failures != 0;
}

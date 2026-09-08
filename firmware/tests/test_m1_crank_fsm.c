/*
 * test_m1_crank_fsm.c — M1 regression: the crank FSM clamp must use the FSM
 * domain (states 0-3), and the tooth-18 event must consult the TOOTH counter.
 *
 * Firmware sites: firmware/c/engine.c crank_position_state_machine (:140-146
 *   clamp; 0x24 belongs to the 0xDA05 rotor-table clamp at :216) and
 *   crank_timing_update (:317-324; `state==0x12` where the ISR comment :305
 *   documents a "tooth 18" event — the tooth variable was never consulted,
 *   so crank_sync_acquire(6) on the rotor-B path never ran).
 *
 * Host-self-contained model of the clamp + ISR dispatch. Assertions:
 *   1. Fault-injection sweep: init sync_counter to every state 0-40, run up
 *      to 2 ticks, assert recovery to a valid FSM state (<=3).
 *   2. Tooth-18 event: state!=0 with tooth==0x12 fires acquire(6); a
 *      non-18 tooth does not; state==0 still fires acquire(0).
 *
 * Build:
 *   gcc -std=c11 -Wall -Wextra -Werror -O2 test_m1_crank_fsm.c -o /tmp/fwtest/test_m1_crank_fsm
 *   gcc ... -DTEST_BUGGY ... (must FAIL)
 */
#include <stdint.h>
#include <stdio.h>

static int failures = 0;

#define CHECK(cond, ...) do { \
    if (!(cond)) { printf("FAIL: "); printf(__VA_ARGS__); printf("\n"); failures++; } \
} while (0)

#ifdef TEST_BUGGY
#define CLAMP_BOUND 0x24
#else
#define CLAMP_BOUND 3
#endif

/* ---- FSM clamp model (engine.c:137-146) ---- */
static uint8_t mem_sync;

static void fsm_tick(uint8_t tooth)
{
    uint8_t state = mem_sync;
    if (state > CLAMP_BOUND) {
        mem_sync = 0;
        state = 0;
    }
    if (state == 0) {
        if (tooth != 0) {
            mem_sync = 1;
        }
        return;
    }
    /* States 1-3: branch bodies irrelevant to the clamp recovery property. */
}

/* ---- ISR dispatch model (engine.c:317-324) ---- */
static uint8_t mem_tooth;
static int acquire_fired;
static uint8_t acquire_arg;

static void acquire_stub(uint8_t off)
{
    acquire_fired = 1;
    acquire_arg = off;
}

static void isr_dispatch(void)
{
    uint8_t state = mem_sync;
    acquire_fired = 0;
    if (state == 0) {
        acquire_stub(0);
#ifdef TEST_BUGGY
    } else if (state == 0x12) {
#else
    } else if (mem_tooth == 0x12) {
#endif
        acquire_stub(6);
    }
}

int main(void)
{
    /* 1. Fault-injection sweep: every state 0-40 recovers within 2 ticks. */
    for (int init = 0; init <= 40; init++) {
        mem_sync = (uint8_t)init;
        fsm_tick(1);
        fsm_tick(1);
        CHECK(mem_sync <= 3,
              "state %d did not recover in 2 ticks (now %u)", init, mem_sync);
    }

    /* 2a. Tooth-18 event fires acquire(6) on the rotor-B path. */
    mem_sync = 2;
    mem_tooth = 0x12;
    isr_dispatch();
    CHECK(acquire_fired && acquire_arg == 6,
          "tooth 0x12 with state 2 must fire acquire(6) (fired=%d arg=%u)",
          acquire_fired, acquire_arg);

    /* 2b. Non-18 tooth does not fire acquire(6). */
    mem_sync = 2;
    mem_tooth = 0x11;
    isr_dispatch();
    CHECK(!acquire_fired,
          "tooth 0x11 must not fire acquire (fired=%d arg=%u)",
          acquire_fired, acquire_arg);

    /* 2c. Unsynced state still fires acquire(0). */
    mem_sync = 0;
    mem_tooth = 0x00;
    isr_dispatch();
    CHECK(acquire_fired && acquire_arg == 0,
          "state 0 must fire acquire(0) (fired=%d arg=%u)",
          acquire_fired, acquire_arg);

#ifndef TEST_BUGGY
    /* Repro: the old bound leaves states 4-36 stranded (no branch handles
     * them, so they never recover), and the old dispatch keys rotor-B off
     * an unreachable sync_counter value. */
    {
        mem_sync = 4;
        fsm_tick(1);
        fsm_tick(1);
        CHECK(mem_sync <= 3,
              "repro: state 4 must recover (now %u)", mem_sync);
    }
#endif

    if (failures == 0) {
        printf("PASS m1_crank_fsm\n");
    } else {
        printf("%d FAILURES m1_crank_fsm\n", failures);
    }
    return failures != 0;
}

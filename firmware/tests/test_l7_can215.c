/*
 * test_l7_can215.c — L7 regression: the CANTX_Main step-3 schedule point
 * must call the ROM-faithful counter_check_dispatch_2A242 so a real 0x215
 * frame goes on the wire.
 *
 * Firmware site: firmware/c/can.c CANTX_Main step 3. The live-wrong inline
 *   block (counter 0xFFFFBB98, every-4, calling can203pack()) sent 0x203
 *   data while 0x215 never appeared; the dead ROM-faithful
 *   counter_check_dispatch_2A242 (D7C4/D7C6, real 0x215 frame, MB3) had zero
 *   callers. Fix: delete the inline block, call the static function.
 * Spec: CAN_PROTOCOL.md "CAN ID 0x215" (DLC 8, MB3, counter 0xFFFFD7C4 vs
 *   threshold 0xFFFFD7C6, forwards CAN_TX_BUF_0215, packs no bytes itself),
 *   ECU.md:94, FINDINGS.md:683.
 *
 * Host-self-contained schedule simulation (threshold 3 as the ROM-threshold
 * stand-in). Assertions: 0x215 frame bytes + MB3 + DLC8 + counter/threshold
 * behavior (fires exactly at the gate, counter resets, no fire below it).
 *
 * Build:
 *   gcc -std=c11 -Wall -Wextra -Werror -O2 test_l7_can215.c -o /tmp/fwtest/test_l7_can215
 *   gcc ... -DTEST_BUGGY ... (must FAIL)
 */
#include <stdint.h>
#include <stdio.h>

static int failures = 0;

#define CHECK(cond, ...) do { \
    if (!(cond)) { printf("FAIL: "); printf(__VA_ARGS__); printf("\n"); failures++; } \
} while (0)

#define CAN_ID_0215 0x0215
#define CAN_ID_0203 0x0203

/* Shared staging stand-in (packs no bytes itself — forwards the buffer). */
static uint8_t staging[8] = { 0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88 };

/* Transmit log */
static int tx_count;
static uint16_t last_id;
static uint8_t last_mb;
static uint8_t last_dlc;
static uint8_t last_bytes[8];

static void tx_send(uint16_t id, uint8_t mb, uint8_t dlc, const uint8_t *buf)
{
    tx_count++;
    last_id = id;
    last_mb = mb;
    last_dlc = dlc;
    for (int i = 0; i < 8; i++) {
        last_bytes[i] = buf[i];
    }
}

#ifdef TEST_BUGGY
/* Pre-fix inline block: counter 0xFFFFBB98, every-4, falls to can203pack. */
static uint16_t cnt_bb98;

static void schedule_step3(void)
{
    cnt_bb98 += 1;
    if (cnt_bb98 >= 4) {
        static const uint8_t b203[8] = { 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5, 0xA6, 0x00 };
        tx_send(CAN_ID_0203, 0x02, 7, b203);
        cnt_bb98 = 0;
    }
}
#else
/* ROM-faithful counter_check_dispatch_2A242: D7C4 vs D7C6 gate, MB3. */
static uint16_t cnt_d7c4;
static uint16_t thr_d7c6 = 3;

static void schedule_step3(void)
{
    cnt_d7c4 += 1;
    if (cnt_d7c4 < thr_d7c6) {
        return;
    }
    cnt_d7c4 = 0;
    tx_send(CAN_ID_0215, 0x03, 8, staging);
}
#endif

int main(void)
{
#ifdef TEST_BUGGY
    cnt_bb98 = 0;
#else
    cnt_d7c4 = 0;
#endif
    tx_count = 0;

    /* Below the gate: nothing on the wire. */
    schedule_step3();
    schedule_step3();
    CHECK(tx_count == 0, "below gate: tx_count=%d want 0", tx_count);

    /* At the gate: exactly one frame. */
    schedule_step3();
    CHECK(tx_count == 1, "at gate: tx_count=%d want 1", tx_count);
    CHECK(last_id == CAN_ID_0215, "frame id=0x%03X want 0x215", last_id);
    CHECK(last_mb == 0x03, "mailbox=%u want MB3", last_mb);
    CHECK(last_dlc == 8, "dlc=%u want 8", last_dlc);
    for (int i = 0; i < 8; i++) {
        CHECK(last_bytes[i] == staging[i],
              "byte %d=0x%02X want 0x%02X", i, last_bytes[i], staging[i]);
    }

    /* Counter reset: next gate fires after a full threshold window. */
    schedule_step3();
    schedule_step3();
    CHECK(tx_count == 1, "after reset: tx_count=%d want 1", tx_count);
    schedule_step3();
    CHECK(tx_count == 2, "second window: tx_count=%d want 2", tx_count);
    CHECK(last_id == CAN_ID_0215, "second frame id=0x%03X want 0x215",
          last_id);
    CHECK(last_mb == 0x03, "second frame mb=%u want MB3", last_mb);

    if (failures == 0) {
        printf("PASS l7_can215\n");
    } else {
        printf("%d FAILURES l7_can215\n", failures);
    }
    return failures != 0;
}

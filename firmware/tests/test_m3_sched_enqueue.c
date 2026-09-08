/*
 * test_m3_sched_enqueue.c — M3 regression: task_scheduler_dispatch must copy
 * the 8 validated EEPROM bytes into the write slot BEFORE advancing.
 *
 * Firmware site: firmware/c/main.c task_scheduler_dispatch (:163-172 — on
 *   eeprom_read_validate()==1 the stack temp_buf was never copied yet
 *   WRITE_IDX advanced: phantom enqueue + data loss). Sharpened:
 *   eeprom_read_validate CONSUMES the marker (writes 0xAA, eeprom.c:443),
 *   so the bytes are unrecoverable except via temp_buf.
 *
 * Host-self-contained validate->dispatch script. Assertions: consumed entry
 * bytes equal staged bytes, pending returns to 0 after get_next, and the
 * dequeued bytes match.
 *
 * Build:
 *   gcc -std=c11 -Wall -Wextra -Werror -O2 test_m3_sched_enqueue.c -o /tmp/fwtest/test_m3_sched_enqueue
 *   gcc ... -DTEST_BUGGY ... (must FAIL)
 */
#include <stdint.h>
#include <stdio.h>

static int failures = 0;

#define CHECK(cond, ...) do { \
    if (!(cond)) { printf("FAIL: "); printf(__VA_ARGS__); printf("\n"); failures++; } \
} while (0)

#define QSIZE 100
#define ENTRY 8

static uint8_t queue[QSIZE][ENTRY];
static uint16_t write_idx;
static uint16_t read_idx;

/* EEPROM RAM buffer model: 8 data bytes + marker (0x55 valid / 0xAA used). */
static uint8_t ee_buf[9];

/* eeprom_read_validate model (eeprom.c:428-446): copies, consumes, returns 1. */
static int eeprom_read_validate(uint8_t *dest)
{
    if (ee_buf[8] != 0x55) {
        return -1;
    }
    for (int i = 0; i < 8; i++) {
        dest[i] = ee_buf[i];
    }
    ee_buf[8] = 0xAA;
    return 1;
}

/* task_scheduler_dispatch busy-path model (main.c:163-172). */
static void sched_dispatch_busy(void)
{
    uint8_t temp_buf[8];
    int result = eeprom_read_validate(temp_buf);
    if (result == 1) {
#ifdef TEST_BUGGY
        write_idx = (uint16_t)((write_idx + 1) % QSIZE);
#else
        for (int i = 0; i < 8; i++) {
            queue[write_idx][i] = temp_buf[i];
        }
        write_idx = (uint16_t)((write_idx + 1) % QSIZE);
#endif
    }
}

static int pending_count(void)
{
    int d = (int)write_idx - (int)read_idx;
    if (d < 0) {
        d += QSIZE;
    }
    return d;
}

int main(void)
{
    for (int i = 0; i < QSIZE; i++) {
        for (int j = 0; j < ENTRY; j++) {
            queue[i][j] = 0xFF;
        }
    }
    write_idx = 0;
    read_idx = 0;

    /* Stage 8 distinct bytes + valid marker. */
    for (int i = 0; i < 8; i++) {
        ee_buf[i] = (uint8_t)(0x10 + i);
    }
    ee_buf[8] = 0x55;

    sched_dispatch_busy();

    /* Marker consumed (both models — validate ran). */
    CHECK(ee_buf[8] == 0xAA, "marker=0x%02X want consumed 0xAA", ee_buf[8]);
    CHECK(pending_count() == 1, "pending=%d want 1", pending_count());

    /* Consumed entry bytes equal staged bytes (fails pre-fix: slot keeps
     * stale 0xFF while pending grew). */
    for (int i = 0; i < 8; i++) {
        CHECK(queue[0][i] == (uint8_t)(0x10 + i),
              "slot[0][%d]=0x%02X want 0x%02X", i, queue[0][i], 0x10 + i);
    }

    /* Dequeue: pending returns to 0 and bytes match. */
    {
        uint16_t idx = read_idx;
        read_idx = (uint16_t)((read_idx + 1) % QSIZE);
        for (int i = 0; i < 8; i++) {
            CHECK(queue[idx][i] == (uint8_t)(0x10 + i),
                  "dequeued[%d]=0x%02X want 0x%02X", i, queue[idx][i],
                  0x10 + i);
        }
    }
    CHECK(pending_count() == 0, "pending=%d want 0", pending_count());

    /* Invalid marker: no enqueue at all. */
    ee_buf[8] = 0x00;
    sched_dispatch_busy();
    CHECK(pending_count() == 0, "invalid: pending=%d want 0",
          pending_count());

    if (failures == 0) {
        printf("PASS m3_sched_enqueue\n");
    } else {
        printf("%d FAILURES m3_sched_enqueue\n", failures);
    }
    return failures != 0;
}

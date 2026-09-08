/*
 * test_m4_serial_rx.c — M4 regression: serial RX needs owned per-channel
 * buffers (mirroring serial_tx_owned) and RX_READY gated on rx_idx>0.
 *
 * Firmware sites: firmware/c/serial.c serial_init (:115-128 set tx_buf
 *   only — rx_buf stayed NULL: ZERO assignments to rx_buf anywhere in
 *   firmware/, no setter API), serial_data_read (:176 rx_buf NULL -> -1
 *   always), RX handlers (:314-340 stores guarded by NULL, READY set via
 *   `rx_idx >= rx_len` with rx_len==0 -> 0>=0 spurious READY on empty).
 * Fix: owned serial_rx_owned[3][] + capacity rx_len + READY on rx_idx>0;
 *   serial_data_read delivers rx_idx bytes and preserves capacity.
 *
 * Host-self-contained loopback model. Assertions: byte delivery, no
 * spurious READY on empty (READY with zero bytes stored is the failure).
 *
 * Build:
 *   gcc -std=c11 -Wall -Wextra -Werror -O2 test_m4_serial_rx.c -o /tmp/fwtest/test_m4_serial_rx
 *   gcc ... -DTEST_BUGGY ... (must FAIL)
 */
#include <stdint.h>
#include <stdio.h>

static int failures = 0;

#define CHECK(cond, ...) do { \
    if (!(cond)) { printf("FAIL: "); printf(__VA_ARGS__); printf("\n"); failures++; } \
} while (0)

#define NCH 3
#define RX_CAP 255
#define ST_IDLE 0x00
#define ST_RX_READY 0x04

typedef struct {
    uint8_t *rx_buf;
    uint8_t rx_idx;
    uint8_t rx_len;
    uint8_t status;
} ch_t;

static ch_t ch[NCH];
#ifndef TEST_BUGGY
static uint8_t rx_owned[NCH][256];
#endif

static void ch_init(void)
{
    for (int i = 0; i < NCH; i++) {
        ch[i].status = ST_IDLE;
        ch[i].rx_idx = 0;
#ifdef TEST_BUGGY
        ch[i].rx_buf = 0;
        ch[i].rx_len = 0;
#else
        ch[i].rx_buf = rx_owned[i];
        ch[i].rx_len = RX_CAP;
#endif
    }
}

/* RX handler model (serial.c ch0/ch1/ch2): store-then-flag. */
static void rx_handler(uint8_t c, uint8_t data)
{
    if (ch[c].rx_buf != 0 && ch[c].rx_idx < ch[c].rx_len) {
        ch[c].rx_buf[ch[c].rx_idx++] = data;
    }
#ifdef TEST_BUGGY
    if (ch[c].rx_idx >= ch[c].rx_len) {
        ch[c].status |= ST_RX_READY;
    }
#else
    if (ch[c].rx_idx > 0) {
        ch[c].status |= ST_RX_READY;
    }
#endif
}

/* serial_data_read model: bytes delivered, or -1 on NULL buffer. */
static int data_read(uint8_t c, uint8_t *buf, uint8_t max_len)
{
    if (c >= NCH) {
        return -1;
    }
    if (ch[c].rx_buf == 0) {
        return -1;
    }
    if (ch[c].status == ST_IDLE) {
        return 0;
    }
#ifdef TEST_BUGGY
    {
        uint8_t len = ch[c].rx_len;
        if (len > max_len) {
            len = max_len;
        }
        for (uint8_t i = 0; i < len; i++) {
            buf[i] = ch[c].rx_buf[i];
        }
        ch[c].status &= (uint8_t)~ST_RX_READY;
        ch[c].rx_idx = 0;
        ch[c].rx_len = 0;
        return len;
    }
#else
    {
        uint8_t len = ch[c].rx_idx;
        if (len > max_len) {
            len = max_len;
        }
        for (uint8_t i = 0; i < len; i++) {
            buf[i] = ch[c].rx_buf[i];
        }
        ch[c].status &= (uint8_t)~ST_RX_READY;
        ch[c].rx_idx = 0;
        return len;
    }
#endif
}

int main(void)
{
    uint8_t buf[8];

    /* 1. Fresh channel: no READY before any byte. */
    ch_init();
    CHECK(!(ch[0].status & ST_RX_READY), "ch0: READY set on empty init");

    /* 2. One byte arrives: stored (idx==1), READY set — READY must imply
     * bytes present (pre-fix: READY with idx==0, nothing stored). */
    rx_handler(0, 0xA5);
    CHECK(!((ch[0].status & ST_RX_READY) && ch[0].rx_idx == 0),
          "ch0: spurious READY with zero bytes stored");
    CHECK(ch[0].rx_idx == 1, "ch0: rx_idx=%u want 1", ch[0].rx_idx);

    /* 3. Loopback on ch1: 3 bytes in, same 3 bytes out. */
    ch_init();
    rx_handler(1, 0xAA);
    rx_handler(1, 0x55);
    rx_handler(1, 0x01);
    CHECK(ch[1].status & ST_RX_READY, "ch1: READY not set after 3 bytes");
    int n = data_read(1, buf, sizeof(buf));
    CHECK(n == 3, "ch1: read %d want 3", n);
    if (n == 3) {
        CHECK(buf[0] == 0xAA && buf[1] == 0x55 && buf[2] == 0x01,
              "ch1: got %02X %02X %02X want AA 55 01",
              buf[0], buf[1], buf[2]);
    }

    /* 4. After read: READY clear, empty read returns 0 (not -1). */
    CHECK(!(ch[1].status & ST_RX_READY), "ch1: READY stuck after read");
    n = data_read(1, buf, sizeof(buf));
    CHECK(n == 0, "ch1: empty read %d want 0", n);

    /* 5. Untouched channel reads 0. */
    n = data_read(2, buf, sizeof(buf));
    CHECK(n == 0, "ch2: idle read %d want 0", n);

    if (failures == 0) {
        printf("PASS m4_serial_rx\n");
    } else {
        printf("%d FAILURES m4_serial_rx\n", failures);
    }
    return failures != 0;
}

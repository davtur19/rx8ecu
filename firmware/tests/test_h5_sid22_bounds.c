/*
 * test_h5_sid22_bounds.c — H5 regression: SID 0x22 response index must be
 * uint16_t with an output bound; pre-fix `uint8_t idx` wrapped (14x VIN DIDs
 * wrap idx to 11, overwriting the response) and no capacity was enforced.
 *
 * Firmware sites: firmware/c/uds.c obd_sid22_readDataByIdentifier (:779 loop),
 *   firmware/c/dtc.c obd_sid12_readDTCByStatus (:877, same family).
 * Contract: response buffer holds at least UDS_MAX_RESPONSE_SIZE (256) bytes;
 *   overflow returns NRC 0x14 (responseTooLong).
 *
 * Host-self-contained: model loop with stub DID lengths (VIN 19B, mid 6B,
 *   short 4B, tiny 3B); N-DID sweep 1..127 asserting monotonic idx, no wrap,
 *   clean NRC at capacity.
 *
 * Build:
 *   gcc -std=c11 -Wall -Wextra -Werror -O2 test_h5_sid22_bounds.c -o /tmp/fwtest/test_h5_sid22_bounds
 *   gcc ... -DTEST_BUGGY ... (must FAIL)
 */
#include <stdint.h>
#include <stdio.h>

#define RESP_CAP 256
#define NRC_14 0x14

/* Stub DID response lengths (total bytes incl. the 2 DID bytes). */
int did_need(uint16_t did)
{
    switch (did) {
    case 0xF190:
        return 19; /* VIN */
    case 0xF806:
    case 0xF808:
    case 0xF187:
        return 6;
    case 0xF193:
    case 0xF18A:
    case 0x010C:
        return 4;
    default:
        return 3;
    }
}

/* Pre-fix loop: uint8_t idx, no bound. Returns final idx (wrapped). */
int buggy_sid22(const uint16_t *dids, unsigned n, uint8_t *resp, unsigned *trace)
{
    uint8_t idx = 1;
    resp[0] = 0x62;
    for (unsigned k = 0; k < n; k++) {
        int need = did_need(dids[k]);
        for (int j = 0; j < need; j++) {
            resp[(uint8_t)(idx + j)] = 0xA5; /* may wrap-write */
        }
        if (trace) {
            trace[k] = idx;
        }
        idx = (uint8_t)(idx + need);
    }
    return idx;
}

/* Fixed loop: uint16_t idx + capacity bound, NRC 0x14 on overflow. */
int fixed_sid22(const uint16_t *dids, unsigned n, uint8_t *resp, unsigned *trace)
{
    uint16_t idx = 1;
    resp[0] = 0x62;
    for (unsigned k = 0; k < n; k++) {
        int need = did_need(dids[k]);
        if (idx + (uint16_t)need > RESP_CAP) {
            resp[0] = 0x7F;
            resp[1] = 0x22;
            resp[2] = NRC_14;
            return 3;
        }
        for (int j = 0; j < need; j++) {
            resp[idx + (uint16_t)j] = 0xA5;
        }
        if (trace) {
            trace[k] = idx;
        }
        idx = (uint16_t)(idx + need);
    }
    return idx;
}

static int failures = 0;

#define CHECK(cond, ...) do { \
    if (!(cond)) { printf("FAIL: "); printf(__VA_ARGS__); printf("\n"); failures++; } \
} while (0)

int main(void)
{
    static uint8_t resp[RESP_CAP + 32];
    static unsigned trace[128];
    uint16_t vins[127];
    for (unsigned i = 0; i < 127; i++) {
        vins[i] = 0xF190;
    }

#ifdef TEST_BUGGY
    /* 14x VIN DIDs must fit logically (1+14*19=267) but the uint8_t index
     * cannot represent it. */
    for (unsigned n = 1; n <= 20; n++) {
        int end = buggy_sid22(vins, n, resp, trace);
        int want = 1 + (int)n * 19;
        CHECK(end == want, "BUGGY n=%u end=%d want=%d", n, end, want);
    }
#else
    /* Sweep 1..127 VIN DIDs: monotonic idx, no wrap, clean NRC at cap. */
    int saw_nrc = 0;
    unsigned prev_ok_end = 0;
    for (unsigned n = 1; n <= 127; n++) {
        int rc = fixed_sid22(vins, n, resp, trace);
        int want = 1 + (int)n * 19;
        if (want <= RESP_CAP) {
            CHECK(rc == want, "n=%u end=%d want=%d", n, rc, want);
            /* Monotonic: each DID starts where the previous ended. */
            for (unsigned k = 1; k < n; k++) {
                CHECK(trace[k] > trace[k - 1],
                      "n=%u idx not monotonic at %u", n, k);
            }
            CHECK(rc <= RESP_CAP, "n=%u exceeds cap", n);
            prev_ok_end = (unsigned)rc;
        } else {
            CHECK(rc == 3, "n=%u must NRC, got %d", n, rc);
            CHECK(resp[0] == 0x7F && resp[1] == 0x22 && resp[2] == NRC_14,
                  "n=%u NRC bytes wrong", n);
            saw_nrc = 1;
        }
    }
    CHECK(saw_nrc, "must hit capacity within 127 VINs");
    /* 13 VINs fit (1+13*19=248), 14th overflows (267>256). */
    CHECK(prev_ok_end == 248, "last fitting end=%u want 248", prev_ok_end);

    /* Repro: 14x VIN wraps the uint8_t index to 11. The 14th DID starts
     * at 248 and its 19 bytes spill past 256, wrapping to bytes 0..10 and
     * overwriting the response header. */
    {
        int end = buggy_sid22(vins, 14, resp, trace);
        CHECK(end == 11, "repro: buggy 14xVIN end=%d want wrapped 11", end);
        CHECK(trace[13] + 19 > 256,
              "repro: buggy 14th DID must spill past the buffer end");
    }
#endif

    if (failures == 0) {
        printf("PASS h5_sid22_bounds\n");
    } else {
        printf("%d FAILURES h5_sid22_bounds\n", failures);
    }
    return failures != 0;
}

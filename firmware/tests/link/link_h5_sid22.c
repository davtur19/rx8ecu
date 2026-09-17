/*
 * link_h5_sid22.c — Link pilot h5: compile-link-run against the REAL
 * obd_sid22_readDataByIdentifier in firmware/c/uds.c (H5-fixed uint16_t
 * idx + sid22_need output bound), not a model replica.
 *
 * Mechanism proof: links the real uds.c TU, so a firmware revert of the H5
 * fix (`uint16_t idx`, `sid22_need` bound vs UDS_MAX_RESPONSE_SIZE) fails
 * this binary at run time, and a signature change fails at compile time
 * (extern decl via uds.h). The multi-DID bound is driven through the real
 * static sid22_need via the extern entry (no -Dstatic= hacks).
 *
 * Constant-DID boundary (the whole point of h5 scoping): ONLY DIDs whose
 * arms perform zero MMIO are exercised —
 *   F806 (6 B), F808 (6 B), F187 (6 B), F190 VIN (19 B),
 *   F193 (4 B), F18A (4 B).
 * NEVER touched: literal-address sensor arms 0x0202/0x010C/0x010D/0x0105
 * (bare 0xFFFFCA00-04 derefs) and the OBD service arms (0xFFFFCA00-09).
 * Those arms remain linked but unexecuted — exactly like uncalled functions
 * in any TU link; no mock, no page mapping needed.
 *
 * Stubs (linker-demanded ONLY, enumerated from `nm -u uds.o` / link
 * errors — nothing more): the TU references three DTC SID handlers used
 * solely by uds_handler dispatch arms, which this test never calls:
 *   obd_sid12_readDTCByStatus, obd_sid14_clearDTC, obd_sid18_readDTCInfo.
 * Each stub is trivial (returns negative-NRC, counts calls); the test
 * asserts all counters stay zero, proving the exercised constant-DID
 * paths never reach them.
 *
 * No MMIO-executing init at link/run: uds.c file-scope statics are plain
 * zero-init (uds_flags, uds_session_shadow, uds_security_shadow), there
 * are no constructor attributes, and uds_init (which WOULD touch
 * 0xFFFFDE5C/0xFFFFD20C via the session/security inlines) is never called.
 *
 * Proves:
 *   (a) each constant DID returns its exact bytes + length;
 *   (b) a six-constant multi-DID request concatenates at the right offsets;
 *   (c) sid22_need bound: 13x VIN fits (len 248), 14x VIN -> NRC 0x14;
 *   (d) malformed (odd/short) -> NRC 0x13; unknown DID echoes + 0x31.
 *
 * Build (see firmware/tests/Makefile link-check):
 *   gcc -std=c11 -Wall -Wextra -Werror -O2 \
 *       -I../include link/link_h5_sid22.c ../c/uds.c -o /tmp/fwtest/link_h5_sid22
 */
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "uds.h"

/* Extern declaration comes from the real uds.h (linking the real uds.c
 * TU): a signature change in firmware breaks this build. Pin the H5
 * contract values so a revert breaks the build, not just the run. */
_Static_assert(UDS_MAX_RESPONSE_SIZE == 256, "UDS_MAX_RESPONSE_SIZE revert");
_Static_assert(UDS_SID_READ_DATA_ID == 0x22, "SID 0x22 revert");
_Static_assert(UDS_POS_RESPONSE_OFFSET == 0x40, "positive-offset revert");
_Static_assert(UDS_NRC_RESPONSE_TOO_LONG == 0x14, "NRC 0x14 revert");
_Static_assert(UDS_NRC_INCORRECT_MSG_LEN == 0x13, "NRC 0x13 revert");
_Static_assert(UDS_NRC_REQUEST_OUT_OF_RANGE == 0x31, "NRC 0x31 revert");

/* ---- Linker-demanded DTC stubs (never executed on h5 paths) ---- */
static int stub_sid12_calls = 0;
static int stub_sid14_calls = 0;
static int stub_sid18_calls = 0;

int obd_sid12_readDTCByStatus(uint8_t sub_func, uint8_t status_mask,
                              uint8_t *out_buf)
{
    (void)sub_func;
    (void)status_mask;
    (void)out_buf;
    stub_sid12_calls++;
    return -0x11;
}

int obd_sid14_clearDTC(uint8_t group_hi, uint8_t group_lo)
{
    (void)group_hi;
    (void)group_lo;
    stub_sid14_calls++;
    return -0x11;
}

int obd_sid18_readDTCInfo(uint8_t sub_func, uint8_t status_mask,
                          uint8_t *out_buf)
{
    (void)sub_func;
    (void)status_mask;
    (void)out_buf;
    stub_sid18_calls++;
    return -0x11;
}

static int failures = 0;

#define CHECK(cond, ...) do { \
    if (!(cond)) { printf("FAIL: "); printf(__VA_ARGS__); printf("\n"); failures++; } \
} while (0)

static void check_bytes(const char *what, const uint8_t *got,
                        const uint8_t *want, unsigned n)
{
    if (memcmp(got, want, n) != 0) {
        unsigned k;
        printf("FAIL: %s mismatch\n  got :", what);
        for (k = 0; k < n; k++)
            printf(" %02X", got[k]);
        printf("\n  want:");
        for (k = 0; k < n; k++)
            printf(" %02X", want[k]);
        printf("\n");
        failures++;
    }
}

/* Caller-provided response buffer: exactly the documented contract size. */
static uint8_t resp[UDS_MAX_RESPONSE_SIZE];

static const uint8_t VIN_STR[17] = "JM1FE179X60000001";

int main(void)
{
    int len;
    unsigned k;

    /* (a) single constant DIDs: exact bytes + lengths. */
    {
        static const uint8_t q[] = { 0xF8, 0x06 };
        static const uint8_t want[] =
            { 0x62, 0xF8, 0x06, 0x60, 0xE1, 0xD4, 0x00 };
        len = obd_sid22_readDataByIdentifier(q, sizeof(q), resp);
        CHECK(len == 7, "F806 len=%d want 7", len);
        check_bytes("F806", resp, want, sizeof(want));
    }
    {
        static const uint8_t q[] = { 0xF8, 0x08 };
        static const uint8_t want[] =
            { 0x62, 0xF8, 0x08, 0x00, 0x00, 0x00, 0x00 };
        len = obd_sid22_readDataByIdentifier(q, sizeof(q), resp);
        CHECK(len == 7, "F808 len=%d want 7", len);
        check_bytes("F808", resp, want, sizeof(want));
    }
    {
        static const uint8_t q[] = { 0xF1, 0x87 };
        static const uint8_t want[] =
            { 0x62, 0xF1, 0x87, 0x00, 0x00, 0x00, 0x00 };
        len = obd_sid22_readDataByIdentifier(q, sizeof(q), resp);
        CHECK(len == 7, "F187 len=%d want 7", len);
        check_bytes("F187", resp, want, sizeof(want));
    }
    {
        static const uint8_t q[] = { 0xF1, 0x90 };
        uint8_t want[20];
        want[0] = 0x62;
        want[1] = 0xF1;
        want[2] = 0x90;
        memcpy(&want[3], VIN_STR, 17);
        len = obd_sid22_readDataByIdentifier(q, sizeof(q), resp);
        CHECK(len == 20, "F190 len=%d want 20", len);
        check_bytes("F190", resp, want, sizeof(want));
    }
    {
        static const uint8_t q[] = { 0xF1, 0x93 };
        static const uint8_t want[] = { 0x62, 0xF1, 0x93, 0x06, 0x04 };
        len = obd_sid22_readDataByIdentifier(q, sizeof(q), resp);
        CHECK(len == 5, "F193 len=%d want 5", len);
        check_bytes("F193", resp, want, sizeof(want));
    }
    {
        static const uint8_t q[] = { 0xF1, 0x8A };
        static const uint8_t want[] = { 0x62, 0xF1, 0x8A, 0x00, 0x00 };
        len = obd_sid22_readDataByIdentifier(q, sizeof(q), resp);
        CHECK(len == 5, "F18A len=%d want 5", len);
        check_bytes("F18A", resp, want, sizeof(want));
    }

    /* (b) six-constant multi-DID: 1 + 6+6+6+19+4+4 = 46. */
    {
        static const uint8_t q[] = {
            0xF8, 0x06, 0xF8, 0x08, 0xF1, 0x87,
            0xF1, 0x90, 0xF1, 0x93, 0xF1, 0x8A,
        };
        uint8_t want[46];
        unsigned o = 0;
        want[o++] = 0x62;
        { static const uint8_t b[] = { 0xF8, 0x06, 0x60, 0xE1, 0xD4, 0x00 };
          memcpy(&want[o], b, 6); o += 6; }
        { static const uint8_t b[] = { 0xF8, 0x08, 0x00, 0x00, 0x00, 0x00 };
          memcpy(&want[o], b, 6); o += 6; }
        { static const uint8_t b[] = { 0xF1, 0x87, 0x00, 0x00, 0x00, 0x00 };
          memcpy(&want[o], b, 6); o += 6; }
        want[o++] = 0xF1; want[o++] = 0x90;
        memcpy(&want[o], VIN_STR, 17); o += 17;
        { static const uint8_t b[] = { 0xF1, 0x93, 0x06, 0x04 };
          memcpy(&want[o], b, 4); o += 4; }
        { static const uint8_t b[] = { 0xF1, 0x8A, 0x00, 0x00 };
          memcpy(&want[o], b, 4); o += 4; }
        len = obd_sid22_readDataByIdentifier(q, sizeof(q), resp);
        CHECK(len == 46, "multi-6 len=%d want 46", len);
        check_bytes("multi-6", resp, want, sizeof(want));
    }

    /* (c) sid22_need bound via the real entry: 13x VIN fits (1+13*19 =
     * 248), the 14th (267 > 256) returns NRC 0x14. */
    {
        uint8_t q13[26], q14[28];
        static const uint8_t nrc14[] = { 0x7F, 0x22, 0x14 };
        for (k = 0; k < 13; k++) {
            q13[2 * k] = 0xF1;
            q13[2 * k + 1] = 0x90;
        }
        memcpy(q14, q13, sizeof(q13));
        q14[26] = 0xF1;
        q14[27] = 0x90;
        len = obd_sid22_readDataByIdentifier(q13, sizeof(q13), resp);
        CHECK(len == 248, "13xVIN len=%d want 248", len);
        if (len == 248) {
            CHECK(resp[0] == 0x62, "13xVIN header=0x%02X want 0x62", resp[0]);
            /* Last VIN block starts at 1+12*19 = 229. */
            CHECK(resp[229] == 0xF1 && resp[230] == 0x90,
                  "13xVIN last block tag=%02X %02X", resp[229], resp[230]);
            CHECK(memcmp(&resp[231], VIN_STR, 17) == 0,
                  "13xVIN last VIN bytes wrong");
        }
        len = obd_sid22_readDataByIdentifier(q14, sizeof(q14), resp);
        CHECK(len == 3, "14xVIN len=%d want 3 (NRC)", len);
        check_bytes("14xVIN NRC", resp, nrc14, sizeof(nrc14));
    }

    /* (d) malformed + unknown DID. */
    {
        static const uint8_t nrc13[] = { 0x7F, 0x22, 0x13 };
        static const uint8_t q1[] = { 0xF1 };
        static const uint8_t q3[] = { 0xF1, 0x90, 0xF1 };
        static const uint8_t unk[] = { 0x12, 0x34 };
        static const uint8_t want_unk[] = { 0x62, 0x12, 0x34, 0x31 };
        len = obd_sid22_readDataByIdentifier(NULL, 0, resp);
        CHECK(len == 3, "empty len=%d want 3 (NRC)", len);
        check_bytes("empty NRC", resp, nrc13, sizeof(nrc13));
        len = obd_sid22_readDataByIdentifier(q1, sizeof(q1), resp);
        CHECK(len == 3, "odd-1 len=%d want 3 (NRC)", len);
        check_bytes("odd-1 NRC", resp, nrc13, sizeof(nrc13));
        len = obd_sid22_readDataByIdentifier(q3, sizeof(q3), resp);
        CHECK(len == 3, "odd-3 len=%d want 3 (NRC)", len);
        check_bytes("odd-3 NRC", resp, nrc13, sizeof(nrc13));
        len = obd_sid22_readDataByIdentifier(unk, sizeof(unk), resp);
        CHECK(len == 4, "unknown len=%d want 4", len);
        check_bytes("unknown", resp, want_unk, sizeof(want_unk));
    }

    /* Stubs must never have executed on the constant-DID paths. */
    CHECK(stub_sid12_calls == 0, "sid12 stub called %d times",
          stub_sid12_calls);
    CHECK(stub_sid14_calls == 0, "sid14 stub called %d times",
          stub_sid14_calls);
    CHECK(stub_sid18_calls == 0, "sid18 stub called %d times",
          stub_sid18_calls);

    if (failures == 0) {
        printf("PASS link_h5_sid22 (real uds.c TU)\n");
    } else {
        printf("%d FAILURES link_h5_sid22\n", failures);
    }
    return failures != 0;
}

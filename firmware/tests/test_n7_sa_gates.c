/*
 * test_n7_sa_gates.c — N7 regression: SecurityAccess length gates match the
 * FINDINGS msg_len spec exactly (RequestSeed msg_len=1, SendKey msg_len=4
 * excluding the SID byte → data_len 0 / 3 after SID+sub-function strip).
 *
 * Firmware site: firmware/c/uds.c obd_sid27_securityAccess (seed gate
 *   `data_len != 0`, key gate `data_len != 3`). Pre-fix: `data_len < 1`
 *   rejected bare `27 01`, and `data_len < 4` rejected `27 02 K1K2K3`
 *   (always NRC 0x13 both ways — SecurityAccess totally bricked).
 * Full SendKey unlock stays gated per N1 (→ NRC 0x12), which is NOT 0x13.
 *
 * Host-self-contained: dispatch model mirroring the firmware gates.
 *
 * Build:
 *   gcc -std=c11 -Wall -Wextra -Werror -O2 test_n7_sa_gates.c -o /tmp/fwtest/test_n7_sa_gates
 *   gcc ... -DTEST_BUGGY ... (must FAIL)
 */
#include <stdint.h>
#include <stdio.h>

static int neg(uint8_t sid, uint8_t nrc, uint8_t *out)
{
    out[0] = 0x7F;
    out[1] = sid;
    out[2] = nrc;
    return 3;
}

/* Mirror of obd_sid27_securityAccess length gating + NRC selection.
 * `seeded` models the D214 seed-present check. */
static int model_sid27(uint8_t sub, uint8_t len, int seeded, uint8_t *out)
{
    if (sub == 0x01 || sub == 0x03) {
#ifdef TEST_BUGGY
        if (len < 1) {
            return neg(0x27, 0x13, out);
        }
#else
        if (len != 0) {
            return neg(0x27, 0x13, out);
        }
#endif
        out[0] = 0x67;
        out[1] = sub;
        out[2] = 0x45;
        out[3] = 0x82;
        out[4] = 0x0A;
        return 5;
    }
    if (sub == 0x02 || sub == 0x04) {
#ifdef TEST_BUGGY
        if (len < 4) {
            return neg(0x27, 0x13, out);
        }
#else
        if (len != 3) {
            return neg(0x27, 0x13, out);
        }
#endif
        if (!seeded) {
            return neg(0x27, 0x22, out);
        }
#ifdef TEST_BUGGY
        out[0] = 0x67;
        out[1] = sub;
        return 2;
#else
        return neg(0x27, 0x12, out); /* N1: SendKey gated, not 0x13 */
#endif
    }
    return neg(0x27, 0x12, out);
}

static int failures = 0;

#define CHECK(cond, ...) do { \
    if (!(cond)) { printf("FAIL: "); printf(__VA_ARGS__); printf("\n"); failures++; } \
} while (0)

/* Expect a positive 5-byte seed response. */
#define CHECK_SEED(sub, len) do { \
    uint8_t o[8] = { 0 }; \
    int n = model_sid27((sub), (len), 1, o); \
    CHECK(n == 5 && o[0] == 0x67 && o[1] == (sub), \
          "seed sub=%02X len=%u → n=%d %02X %02X, want 5/67/%02X", \
          (sub), (unsigned)(len), n, o[0], o[1], (sub)); \
} while (0)

/* Expect NRC 0x13. */
#define CHECK_13(sub, len, seeded) do { \
    uint8_t o[8] = { 0 }; \
    int n = model_sid27((sub), (len), (seeded), o); \
    CHECK(n == 3 && o[0] == 0x7F && o[1] == 0x27 && o[2] == 0x13, \
          "sub=%02X len=%u must be 7F 27 13 (got n=%d %02X %02X %02X)", \
          (sub), (unsigned)(len), n, o[0], o[1], o[2]); \
} while (0)

int main(void)
{
    uint8_t o[8] = { 0 };
    int n;

    /* Bare `27 01` / `27 03` (data_len 0) → seed response, not 0x13. */
    CHECK_SEED(0x01, 0);
    CHECK_SEED(0x03, 0);

    /* Seed with trailing bytes → 0x13 (exact msg_len match). */
    CHECK_13(0x01, 1, 1);
    CHECK_13(0x03, 2, 1);

    /* `27 02` / `27 04` + 3-byte key → key path (gated 0x12, NOT 0x13). */
    n = model_sid27(0x02, 3, 1, o);
    CHECK(n == 3 && o[0] == 0x7F && o[1] == 0x27 && o[2] == 0x12,
          "27 02+key must be 7F 27 12 (got n=%d %02X %02X %02X)",
          n, o[0], o[1], o[2]);
    n = model_sid27(0x04, 3, 1, o);
    CHECK(n == 3 && o[2] == 0x12, "27 04+key must be 7F 27 12");

    /* Short SendKey inputs → 0x13. */
    CHECK_13(0x02, 0, 1);
    CHECK_13(0x02, 2, 1);
    CHECK_13(0x04, 1, 1);

    /* Overlong SendKey (4 key bytes) → 0x13. */
    CHECK_13(0x02, 4, 1);

    /* Full key but no seed issued yet → 0x22, not 0x13. */
    n = model_sid27(0x02, 3, 0, o);
    CHECK(n == 3 && o[2] == 0x22, "key-without-seed must be 0x22");

    /* Unknown sub-function → 0x12. */
    n = model_sid27(0x05, 0, 1, o);
    CHECK(n == 3 && o[2] == 0x12, "sub 0x05 must be 0x12");

    if (failures == 0) {
        printf("PASS n7_sa_gates\n");
    } else {
        printf("%d FAILURES n7_sa_gates\n", failures);
    }
    return failures != 0;
}

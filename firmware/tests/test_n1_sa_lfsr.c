/*
 * test_n1_sa_lfsr.c — N1 regression: SID 0x27 uses the ROM-verified 24-bit
 * Galois LFSR (not the old XOR-rotate-nibble fiction whose level table sat
 * on the 0x5FAC5 FF padding), answers RequestSeed with [0x67, sub, 3B], and
 * keeps the ROM-unreachable SendKey path gated off.
 *
 * Firmware sites: firmware/c/uds.c uds_sa_lfsr_clock / uds_sa_compute_key /
 *   uds_sa_level_init / security_access_validate_key / obd_sid27_securityAccess.
 * ROM reference: tools/mazda_security.py (taps 0x909028, init 0xC541A9,
 *   stock vector seed 0x45820A + "MazdA" level 1 → key 0xA07258),
 *   KNOWLEDGE.md:54-64, FINDINGS.md 2026-08-04 (response [0x67, sub, 3B],
 *   SendKey 0x58592-0x58610 unreachable).
 *
 * Host-self-contained: verbatim port of the LFSR + dispatch models mirroring
 * the firmware arms (incl. the N7 length gates).
 *
 * Build:
 *   gcc -std=c11 -Wall -Wextra -Werror -O2 test_n1_sa_lfsr.c -o /tmp/fwtest/test_n1_sa_lfsr
 *   gcc ... -DTEST_BUGGY ... (must FAIL)
 */
#include <stdint.h>
#include <stdio.h>

/* ROM constants (uds.c UDS_SA_*). */
#define SA_TAPS     0x909028u
#define SA_INIT_L1  0xC541A9u
#define SA_MASK24   0xFFFFFFu

#ifndef TEST_BUGGY /* fixed crypto port (unused in buggy mode) */
static uint32_t sa_clock(uint32_t state, uint8_t bit)
{
    uint8_t fb = (uint8_t)((state & 1u) ^ (bit & 1u));
    state >>= 1;
    if (fb != 0) {
        state ^= SA_TAPS;
    }
    return state & SA_MASK24;
}

/* Fixed crypto: verbatim port of uds_sa_compute_key. */
static void sa_compute(const uint8_t seed[3], const uint8_t secret[5],
                       uint32_t init, uint8_t key[3])
{
    uint32_t seed24 = ((uint32_t)seed[0] << 16) |
                      ((uint32_t)seed[1] << 8) | (uint32_t)seed[2];
    uint32_t w1 = ((uint32_t)secret[0] << 24) |
                  ((seed24 & 0xFFu) << 16) | (seed24 & 0xFF00u) |
                  ((seed24 >> 16) & 0xFFu);
    uint32_t w2 = ((uint32_t)secret[4] << 24) |
                  ((uint32_t)secret[3] << 16) |
                  ((uint32_t)secret[2] << 8) | (uint32_t)secret[1];
    uint32_t state = init & SA_MASK24;
    for (uint8_t i = 0; i < 32; i++) {
        state = sa_clock(state, (uint8_t)((w1 >> i) & 1u));
    }
    for (uint8_t i = 0; i < 32; i++) {
        state = sa_clock(state, (uint8_t)((w2 >> i) & 1u));
    }
    uint8_t b0 = (uint8_t)(((state >> 16) & 0xFu) | ((state & 0xFu) << 4));
    uint8_t b1 = (uint8_t)(((state >> 20) & 0xFu) | (((state >> 12) & 0xFu) << 4));
    uint8_t b2 = (uint8_t)((state >> 4) & 0xFFu);
    key[0] = b2;
    key[1] = b1;
    key[2] = b0;
}
#endif /* TEST_BUGGY */

#ifdef TEST_BUGGY
/* Pre-fix crypto: the removed XOR-rotate-nibble math with the old level
 * table (copied from uds.c before the N1 fix). Seed bytes are passed in
 * place of the RAM shadow reads. */
static int buggy_validate(uint8_t level, const uint8_t *key,
                          const uint8_t seed[3])
{
    static const uint8_t prefix[8] =
        { 0x4D, 0x61, 0x7A, 0x64, 0x41, 0xFF, 0xFF, 0xFF };
    static const uint8_t ltab[4][3] = {
        { 0xFF, 0xFF, 0x00 }, { 0xC5, 0x41, 0x00 },
        { 0xA9, 0xA3, 0x95 }, { 0x82, 0xFF, 0xFF },
    };
    uint8_t buf[8];
    buf[0] = seed[0];
    buf[1] = seed[1];
    buf[2] = seed[2];
    buf[3] = prefix[3];
    buf[4] = prefix[4];
    buf[5] = prefix[5];
    buf[6] = prefix[6];
    buf[7] = prefix[7];
    uint8_t lv = (uint8_t)(level & 0x03);
    for (int pass = 0; pass < 2; pass++) {
        int count = (pass == 0) ? 8 : 3;
        for (int i = 0; i < count; i++) {
            uint8_t carry = buf[0] & 0x01;
            for (int b = 0; b < 7; b++) {
                buf[b] = (uint8_t)((buf[b] >> 1) |
                                   ((buf[b + 1] & 0x01) ? 0x80 : 0x00));
            }
            buf[7] = (uint8_t)((buf[7] >> 1) | (carry ? 0x80 : 0x00));
        }
    }
    uint8_t ca = (uint8_t)(buf[0] ^ 0x08 ^ 0x20);
    uint8_t cb = (uint8_t)(buf[1] ^ 0x10 ^ 0x80);
    uint8_t cc = (uint8_t)(buf[2] ^ 0x10);
    uint8_t r[3];
    r[0] = (uint8_t)(((ca & 0xF0) >> 4) | ((ltab[lv][0] & 0x0F) << 4));
    r[1] = (uint8_t)(((cb & 0xF0) >> 4) | ((ltab[lv][1] & 0x0F) << 4));
    r[2] = (uint8_t)(((cc & 0xF0) >> 4) | ((ltab[lv][2] & 0x0F) << 4));
    return (r[0] == key[0] && r[1] == key[1] && r[2] == key[2]) ? 1 : 0;
}
#endif

/* Negative-response helper: [0x7F, sid, nrc], len 3. */
static int neg(uint8_t sid, uint8_t nrc, uint8_t *out)
{
    out[0] = 0x7F;
    out[1] = sid;
    out[2] = nrc;
    return 3;
}

/* Seed-response builder model. Fixed: [0x67, sub, 3B] (len 5).
 * Buggy: appended SEED_ID as a 4th byte (len 6). */
static int seed_resp(uint8_t sub, const uint8_t *seed, uint8_t *out)
{
    out[0] = 0x67;
    out[1] = sub;
    out[2] = seed[0];
    out[3] = seed[1];
    out[4] = seed[2];
#ifdef TEST_BUGGY
    out[5] = 0x5A; /* stand-in SEED_ID byte */
    return 6;
#else
    return 5;
#endif
}

/* SID 0x27 dispatch model mirroring obd_sid27_securityAccess (fixed gates:
 * seed data_len==0, key data_len==3; SendKey unlock gated → NRC 0x12).
 * Buggy: seed data_len<1, key data_len<4, live unlock path. */
static int model_sid27(uint8_t sub, const uint8_t *data, uint8_t len,
                       int seeded, const uint8_t seed[3], uint8_t *out)
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
        return seed_resp(sub, seed, out);
    }
    if (sub == 0x02 || sub == 0x04) {
#ifdef TEST_BUGGY
        if (len < 4) {
            return neg(0x27, 0x13, out);
        }
        if (!seeded) {
            return neg(0x27, 0x22, out);
        }
        uint8_t lvl = (sub == 0x02) ? 0x01 : 0x03;
        if (buggy_validate(lvl, data, seed)) {
            out[0] = 0x67;
            out[1] = sub;
            return 2;
        }
        return neg(0x27, 0x35, out);
#else
        if (len != 3) {
            return neg(0x27, 0x13, out);
        }
        if (!seeded) {
            return neg(0x27, 0x22, out);
        }
        /* Validation runs against the ROM LFSR (N7), but the unlock is
         * gated off as ROM-unreachable (N1) → NRC 0x12. */
        static const uint8_t secret[5] = { 'M', 'a', 'z', 'd', 'A' };
        uint8_t lvl = (sub == 0x02) ? 0x01 : 0x03;
        uint8_t expect[3];
        sa_compute(seed, secret, (lvl == 1) ? SA_INIT_L1 : SA_INIT_L1, expect);
        /* The validation runs (mirrors the firmware call); the unlock it
         * would grant is gated off — result discarded, NRC 0x12 below. */
        int valid = (expect[0] == data[0] && expect[1] == data[1] &&
                     expect[2] == data[2]) ? 1 : 0;
        (void)valid;
        return neg(0x27, 0x12, out);
#endif
    }
    return neg(0x27, 0x12, out);
}

static int failures = 0;

#define CHECK(cond, ...) do { \
    if (!(cond)) { printf("FAIL: "); printf(__VA_ARGS__); printf("\n"); failures++; } \
} while (0)

int main(void)
{
    static const uint8_t seed[3] = { 0x45, 0x82, 0x0A };
#ifndef TEST_BUGGY
    static const uint8_t secret[5] = { 'M', 'a', 'z', 'd', 'A' };
#endif
    static const uint8_t want_key[3] = { 0xA0, 0x72, 0x58 };
    uint8_t out[8] = { 0 };

    /* 1. ROM-verified stock vector (mazda_security.py self-test). */
#ifdef TEST_BUGGY
    CHECK(buggy_validate(0x01, want_key, seed) == 1,
          "buggy crypto must accept the ROM stock vector");
#else
    uint8_t got[3];
    sa_compute(seed, secret, SA_INIT_L1, got);
    CHECK(got[0] == want_key[0] && got[1] == want_key[1] &&
          got[2] == want_key[2],
          "LFSR stock vector got %02X %02X %02X want A0 72 58",
          got[0], got[1], got[2]);
    CHECK(SA_INIT_L1 == 0xC541A9u, "level-1 INIT must be 0xC541A9");
    CHECK(SA_TAPS == 0x909028u, "LFSR taps must be 0x909028");
#endif

    /* 2. Seed response shape [0x67, sub, 3B]. */
    {
        int n = seed_resp(0x01, seed, out);
        CHECK(n == 5, "seed resp len=%d want 5", n);
        CHECK(out[0] == 0x67 && out[1] == 0x01, "seed header %02X %02X",
              out[0], out[1]);
        CHECK(out[2] == 0x45 && out[3] == 0x82 && out[4] == 0x0A,
              "seed bytes %02X %02X %02X want 45 82 0A",
              out[2], out[3], out[4]);
    }

    /* 3. Bare `27 01` (data_len 0) → seed response, not NRC 0x13. */
    {
        int n = model_sid27(0x01, NULL, 0, 1, seed, out);
        CHECK(n == 5 && out[0] == 0x67,
              "27 01 len=%d first=%02X want 5/0x67", n, out[0]);
    }

    /* 4. `27 01` + 1 extra byte → NRC 0x13 (exact msg_len gate). */
    {
        uint8_t d[1] = { 0x00 };
        int n = model_sid27(0x01, d, 1, 1, seed, out);
        CHECK(n == 3 && out[0] == 0x7F && out[2] == 0x13,
              "27 01+pad must be 7F 27 13");
    }

    /* 5. `27 02` + correct 3-byte key → gated NRC 0x12 (and NOT 0x13). */
    {
        int n = model_sid27(0x02, want_key, 3, 1, seed, out);
        CHECK(n == 3 && out[0] == 0x7F && out[1] == 0x27 && out[2] == 0x12,
              "27 02+key must be gated 7F 27 12 (got len=%d %02X %02X %02X)",
              n, out[0], out[1], out[2]);
    }

    /* 6. Short SendKey (2 key bytes) → NRC 0x13. */
    {
        uint8_t d[2] = { 0xA0, 0x72 };
        int n = model_sid27(0x02, d, 2, 1, seed, out);
        CHECK(n == 3 && out[2] == 0x13, "short SendKey must be 0x13");
    }

    if (failures == 0) {
        printf("PASS n1_sa_lfsr\n");
    } else {
        printf("%d FAILURES n1_sa_lfsr\n", failures);
    }
    return failures != 0;
}

/*
 * test_c2_sid34_size.c — C2 regression: SID 0x34 must store the download
 * size right-aligned (BE32); the pre-fix code stored it shifted <<8, so a
 * flash download could never complete (remaining never reaches 0).
 *
 * Firmware sites: firmware/c/uds.c obd_sid34_requestDownload (store),
 *   obd_sid36_transferData (reconstruct/update), obd_sid37_requestTransferExit
 *   (exit check). The parse loops (mem_addr/mem_size) were already correct;
 *   only the persisted RAM image was skewed.
 *
 * Host-self-contained: stub RAM image bytes + exact copies of the store /
 * reconstruct expressions. Vectors cover (addr_bytes,size_bytes) in {1..4}^2
 * plus an end-to-end 0x34/0x36xN/0x37 script, plus the C2 width validator
 * (exactly 3+3 accepted, 1/2/4-byte widths rejected with NRC 0x13).
 *
 * Build:
 *   gcc -std=c11 -Wall -Wextra -Werror -O2 test_c2_sid34_size.c -o /tmp/fwtest/test_c2_sid34_size
 *   gcc ... -DTEST_BUGGY ... (must FAIL)
 */
#include <stdint.h>
#include <stdio.h>

/* Stub of the 8 persisted RAM image bytes:
 * [0]=format [1]=HI [2]=MID [3]=LO [4]=B3 [5]=B2 [6]=B1 [7]=B0 */
static uint8_t img[8];

/* Parse loops copied verbatim from obd_sid34_requestDownload. */
uint32_t parse_be(const uint8_t *data, uint8_t n)
{
    uint32_t v = 0;
    for (uint8_t i = 0; i < n; i++) {
        v = (v << 8) | data[i];
    }
    return v;
}

/* Pre-fix store: raw-index copies (left-aligned, B0 forced 0 for sb<4;
 * MEM_HI/MEM_LO wrong unless addr_bytes==3). */
void buggy_store(const uint8_t *data, uint8_t addr_bytes, uint8_t size_bytes)
{
    img[0] = 0;
    img[1] = data[1];
    img[2] = data[2];
    img[3] = (addr_bytes >= 3) ? data[3] : 0;
    img[4] = data[1 + addr_bytes];
    img[5] = (size_bytes >= 2) ? data[2 + addr_bytes] : 0;
    img[6] = (size_bytes >= 3) ? data[3 + addr_bytes] : 0;
    img[7] = (size_bytes >= 4) ? data[4 + addr_bytes] : 0;
}

/* Fixed store: right-aligned BE32/BE24 from the correctly parsed values. */
void fixed_store(uint32_t mem_addr, uint32_t mem_size)
{
    img[1] = (uint8_t)(mem_addr >> 16);
    img[2] = (uint8_t)(mem_addr >> 8);
    img[3] = (uint8_t)(mem_addr);
    img[4] = (uint8_t)(mem_size >> 24);
    img[5] = (uint8_t)(mem_size >> 16);
    img[6] = (uint8_t)(mem_size >> 8);
    img[7] = (uint8_t)(mem_size);
}

/* Reconstruct copied verbatim from obd_sid36_transferData / sid37 exit. */
uint32_t reconstruct_size(void)
{
    return ((uint32_t)img[4] << 24) | ((uint32_t)img[5] << 16) |
           ((uint32_t)img[6] << 8) | (uint32_t)img[7];
}

/* C2 validator model: the firmware demands exactly addr_bytes==3 &&
 * size_bytes==3 (its own ROM contract, uds.c data_len+1==8); the pre-fix
 * code accepted 1..4 and truncated 4-byte values to 24 bits in the store. */
int model_validate(uint8_t addr_bytes, uint8_t size_bytes)
{
#ifdef TEST_BUGGY
    return (addr_bytes >= 1 && addr_bytes <= 4 &&
            size_bytes >= 1 && size_bytes <= 4) ? 0 : -0x13;
#else
    return (addr_bytes == 3 && size_bytes == 3) ? 0 : -0x13;
#endif
}

uint32_t reconstruct_addr(void)
{
    return ((uint32_t)img[1] << 16) | ((uint32_t)img[2] << 8) | (uint32_t)img[3];
}

static int failures = 0;

#define CHECK(cond, ...) do { \
    if (!(cond)) { printf("FAIL: "); printf(__VA_ARGS__); printf("\n"); failures++; } \
} while (0)

/* Build a request payload: [format][addr BE][size BE]. */
static uint8_t build_req(uint8_t *out, uint8_t ab, uint8_t sb,
                         uint32_t addr, uint32_t size)
{
    out[0] = (uint8_t)((sb << 4) | ab);
    for (int k = ab - 1; k >= 0; k--) {
        out[1 + (ab - 1 - k)] = (uint8_t)(addr >> (8 * k));
    }
    for (int k = sb - 1; k >= 0; k--) {
        out[1 + ab + (sb - 1 - k)] = (uint8_t)(size >> (8 * k));
    }
    return (uint8_t)(1 + ab + sb);
}

int main(void)
{
    /* C2 validator: only the 3+3 encoding is legal; 1/2/4-byte widths are
     * cleanly rejected with NRC 0x13 (no truncation path remains). */
    for (uint8_t ab = 0; ab <= 5; ab++) {
        for (uint8_t sb = 0; sb <= 5; sb++) {
            int want = (ab == 3 && sb == 3) ? 0 : -0x13;
            CHECK(model_validate(ab, sb) == want,
                  "validate ab=%u sb=%u → %d want %d",
                  ab, sb, model_validate(ab, sb), want);
        }
    }

    /* Representative values per byte-width (fit in ab/sb bytes). */
    const uint32_t addrs[4] = {0x5Au, 0x1234u, 0x010203u, 0x04050607u};
    const uint32_t sizes[4] = {0x09u, 0x0789u, 0x000789u, 0x01020304u};

    for (uint8_t ab = 1; ab <= 4; ab++) {
        for (uint8_t sb = 1; sb <= 4; sb++) {
            uint8_t req[9];
            uint32_t a = addrs[ab - 1];
            uint32_t s = sizes[sb - 1];
            (void)build_req(req, ab, sb, a, s);
            uint32_t mem_addr = parse_be(req + 1, ab);
            uint32_t mem_size = parse_be(req + 1 + ab, sb);
            CHECK(mem_addr == a, "parse addr ab=%u", ab);
            CHECK(mem_size == s, "parse size sb=%u", sb);

#ifdef TEST_BUGGY
            buggy_store(req, ab, sb);
            CHECK(reconstruct_size() == mem_size,
                  "BUGGY ab=%u sb=%u stored=0x%08lX want=0x%08lX",
                  ab, sb, (unsigned long)reconstruct_size(), (unsigned long)mem_size);
            if (ab <= 3) {
                CHECK(reconstruct_addr() == mem_addr,
                      "BUGGY addr ab=%u stored=0x%06lX want=0x%06lX",
                      ab, (unsigned long)reconstruct_addr(), (unsigned long)mem_addr);
            }
#else
            fixed_store(mem_addr, mem_size);
            CHECK(reconstruct_size() == mem_size,
                  "fixed ab=%u sb=%u stored=0x%08lX want=0x%08lX",
                  ab, sb, (unsigned long)reconstruct_size(), (unsigned long)mem_size);
            if (ab <= 3) {
                CHECK(reconstruct_addr() == mem_addr,
                      "fixed addr ab=%u stored=0x%06lX want=0x%06lX",
                      ab, (unsigned long)reconstruct_addr(), (unsigned long)mem_addr);
            } else {
                /* 4-byte addresses fold to BE24 (3-byte RAM image). */
                CHECK(reconstruct_addr() == (mem_addr & 0xFFFFFFu),
                      "fixed addr ab=4 folds to BE24: 0x%06lX",
                      (unsigned long)reconstruct_addr());
            }
#endif
        }
    }

#ifndef TEST_BUGGY
    /* Repro: documented ECU standard case format 0x33, size 0x000789. */
    {
        uint8_t req[9];
        (void)build_req(req, 3, 3, 0x000100u, 0x000789u);
        uint32_t mem_size = parse_be(req + 4, 3);
        buggy_store(req, 3, 3);
        uint32_t bad = reconstruct_size();
        CHECK(bad == 0x00078900u,
              "repro: buggy 0x33/0x000789 stored 0x%08lX (want skewed 0x00078900)",
              (unsigned long)bad);
        /* After transferring exactly 0x789 bytes, remaining != 0. */
        uint32_t rem = bad - 0x789u;
        CHECK(rem == 0x00078177u && rem != 0,
              "repro: buggy remaining after full xfer 0x%08lX -> NRC 0x71 forever",
              (unsigned long)rem);
        (void)mem_size;
    }

    /* End-to-end: 0x34 store, 0x36 x N drain, 0x37 exit check. */
    {
        uint8_t req[9];
        (void)build_req(req, 3, 3, 0x000100u, 0x000789u);
        uint32_t mem_addr = parse_be(req + 1, 3);
        uint32_t mem_size = parse_be(req + 4, 3);
        fixed_store(mem_addr, mem_size);
        uint32_t remaining = reconstruct_size();
        uint32_t moved = 0;
        while (remaining > 0) {
            uint32_t chunk = remaining > 128 ? 128 : remaining;
            remaining -= chunk;
            moved += chunk;
            /* Firmware writes back BE32 each block; mirror it. */
            img[4] = (uint8_t)(remaining >> 24);
            img[5] = (uint8_t)(remaining >> 16);
            img[6] = (uint8_t)(remaining >> 8);
            img[7] = (uint8_t)(remaining);
        }
        CHECK(moved == 0x789u, "e2e moved 0x%lX want 0x789", (unsigned long)moved);
        uint32_t exit_rem = reconstruct_size();
        CHECK(exit_rem == 0, "e2e exit remaining=%lu (want 0, positive exit)",
              (unsigned long)exit_rem);
    }
#endif

    if (failures == 0) {
        printf("PASS c2_sid34_size\n");
    } else {
        printf("%d FAILURES c2_sid34_size\n", failures);
    }
    return failures != 0;
}

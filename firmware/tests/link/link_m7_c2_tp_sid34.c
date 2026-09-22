/*
 * link_m7_c2_tp_sid34.c — Link pilot m7/c2: compile-link-run against the
 * REAL M7 TesterPresent arm and the REAL C2 SID 0x34/0x36/0x37 download
 * chain in firmware/c/uds.c, not model replicas.
 *
 * Mechanism proof: links the real uds.c TU, so a firmware revert of the
 * M7 fix (`tp_sub != 0x00`, or the TP-flag store), of the C2 fix
 * (exactly-3+3 validator, or the right-aligned BE24/BE32 store into
 * UDS_DL_*), or of the sid36 reconstruct/update / sid37 clear paths fails
 * this binary at run time; a signature change fails at compile time
 * (extern decls via uds.h).
 *
 * Scope split (the whole point of m7/c2 scoping — h5 pattern, D page):
 *   - M7 rides through the REAL uds_handler, but ONLY with SID 0x3E:
 *     the TesterPresent arm returns BEFORE uds_dispatch_lookup, so the
 *     ROM dispatch table at 0x5F57C and the session-gate table at
 *     0x5FA7D are never dereferenced (no ROM read — the h3 blocker
 *     stays blocked and is not re-derived here).
 *   - C2 rides through the REAL extern entries obd_sid34_requestDownload
 *     / obd_sid36_transferData / obd_sid37_requestTransferExit (h5
 *     style: direct entry, no dispatch), so their session/security
 *     gates, validator, store, reconstruct, and clear all execute
 *     against mapped RAM — never against ROM.
 *
 * Stubs (linker-demanded ONLY, enumerated from `nm -u uds.o` — identical
 * set to link_h5_sid22, nothing more): obd_sid12_readDTCByStatus,
 * obd_sid14_clearDTC, obd_sid18_readDTCInfo. Each counts calls; the test
 * asserts all counters stay zero (no exercised path dispatches a DTC
 * SID). Firmware sources untouched.
 *
 * Host execution boundary (one D page + one flash sandbox, mmap
 * MAP_FIXED):
 *   - D page 0xFFFFD000/0x1000 covers EVERY RAM address the exercised
 *     paths touch: session 0xFFFFDE5C, security 0xFFFFD20C, TP flag
 *     0xFFFFD215, and the whole download image 0xFFFFD218..0xFFFFD225
 *     (format/addr/size/seq/state + the 4-byte checksum at D222).
 *   - Flash sandbox 0x00070000/0x1000 covers the sid36 payload write:
 *     the C2 3+3 gate caps mem_addr at 0xFFFFFF, and the RAM window
 *     (>= 0xFFFF8000) is unreachable with 3 address bytes, so every
 *     legal download target sits in flash 0x000000..0x0007FFFF —
 *     0x70000 is above mmap_min_addr and inside UDS_DL_FLASH_END.
 *   - No FW_HOST_TEST accessor needed: uds_handler and the three sid
 *     entries are public externs; uds_set_session/uds_set_security are
 *     public static inlines in uds.h. uds_init is never called (h5
 *     boundary); uds.c file-scope statics are plain zero-init.
 *
 * Proves (every assert killable; every zero-expect is primed nonzero
 * first — F1 lesson):
 *   (a) M7: `3E 00` and bare `3E` → positive [7E 00] with the TP-flag
 *       store landing (primed 0xEE → 1); `3E 80`/`3E 01` → NRC
 *       [7F 3E 12] with the TP flag left at its primed nonzero value
 *       (kills both a dropped store and an ungated echo);
 *   (b) the three DTC stubs stay uncalled after the M7 pass;
 *   (c) sid34 gates: default session → 0x22, locked security → 0x33,
 *       both leaving the 0xEE-poisoned DL image untouched;
 *   (d) sid34 C2 validator: only 3+3 accepted — 2+2, 4+4, overlong,
 *       short, zero-width all → 0x13 with the poisoned image intact;
 *   (e) sid34 range: beyond-flash → 0x31, size 0 → 0x31, image intact;
 *   (f) sid34 happy: 5-byte positive [74 00 01 00 80] and EVERY DL byte
 *       right-aligned (B0=4 primed 0xEE, B1=0 primed 0xEE, checksum
 *       u32 0xFFFFFFFF → 0, seq=1, state=ACTIVE);
 *   (g) sid36: wrong seq → 0x73 with the flash target still primed;
 *       correct seq → [76 01], 4 payload bytes land at 0x70000 (the
 *       neighbor byte keeps its 0xEE prime), checksum 0x338, remaining
 *       4 → 0, MEM_LO 0 → 4, seq 1 → 2; payload>remaining is capped
 *       (no extra flash write, checksum stable); data_len 0 → 0x13;
 *       state≠ACTIVE → 0x22; default session → 0x22;
 *   (h) sid37: remaining≠0 → 0x71 with state unchanged; happy →
 *       [77 00] clearing STATE 1→0, SEQ 2→0, checksum 0x338→0,
 *       FORMAT 0x33→0, MEM_HI/MEM_MID/MEM_LO nonzero→0; SIZE B3..B0
 *       clear stores are 0→0 only (the remaining==0 gate reads exactly
 *       those four bytes, so a nonzero→0 SIZE transition is unreachable
 *       on the happy path — asserted stay-0 instead); state≠ACTIVE →
 *       0x22; default session → 0x22;
 *   (i) the three DTC stubs stay uncalled at the end (whole run).
 *
 * Build (see firmware/tests/Makefile link-check):
 *   gcc -std=c11 -Wall -Wextra -Werror -O2 \
 *       -I../include link/link_m7_c2_tp_sid34.c ../c/uds.c \
 *       -o /tmp/fwtest/link_m7_c2_tp_sid34
 */
#include <stdint.h>
#include <stdio.h>
#include <stddef.h>
#include <sys/mman.h>

#include "uds.h"

/* Extern declarations come from the real uds.h (linking the real uds.c
 * TU): a signature change in firmware breaks this build. Pin the M7/C2
 * contract values so a revert breaks the build, not just the run. */
_Static_assert(UDS_SID_TESTER_PRESENT == 0x3E, "SID 0x3E revert");
_Static_assert(UDS_SID_REQ_DOWNLOAD == 0x34, "SID 0x34 revert");
_Static_assert(UDS_SID_TRANSFER_DATA == 0x36, "SID 0x36 revert");
_Static_assert(UDS_SID_REQ_TRANS_EXIT == 0x37, "SID 0x37 revert");
_Static_assert(UDS_SID_NEGATIVE_RESP == 0x7F, "negative-resp header revert");
_Static_assert(UDS_POS_RESPONSE_OFFSET == 0x40, "positive-offset revert");
_Static_assert(UDS_NRC_SUB_NOT_SUPPORTED == 0x12, "NRC 0x12 revert");
_Static_assert(UDS_NRC_INCORRECT_MSG_LEN == 0x13, "NRC 0x13 revert");
_Static_assert(UDS_NRC_CONDITIONS_NOT_CORRECT == 0x22, "NRC 0x22 revert");
_Static_assert(UDS_NRC_SECURITY_ACCESS_DENIED == 0x33, "NRC 0x33 revert");
_Static_assert(UDS_NRC_REQUEST_OUT_OF_RANGE == 0x31, "NRC 0x31 revert");
_Static_assert(UDS_NRC_WRONG_BLOCK_SEQ == 0x73, "NRC 0x73 revert");
_Static_assert(UDS_NRC_TRANSFER_SUSPENDED == 0x71, "NRC 0x71 revert");
_Static_assert(UDS_SESSION_PROGRAMMING == 0x02, "session programming revert");
_Static_assert(UDS_SECURITY_LOCKED == 0x7F, "security locked revert");
_Static_assert(UDS_SECURITY_LEVEL_1 == 0x5F, "security level1 revert");
_Static_assert(UDS_DL_STATE_ACTIVE == 0x01, "DL state active revert");
_Static_assert(UDS_DL_FLASH_END == 0x0007FFFFu, "DL flash end revert");
_Static_assert(UDS_DL_FORMAT_ADDR == 0xFFFFD218u, "DL_FORMAT revert");
_Static_assert(UDS_DL_MEM_HI_ADDR == 0xFFFFD219u, "DL_MEM_HI revert");
_Static_assert(UDS_DL_MEM_MID_ADDR == 0xFFFFD21Au, "DL_MEM_MID revert");
_Static_assert(UDS_DL_MEM_LO_ADDR == 0xFFFFD21Bu, "DL_MEM_LO revert");
_Static_assert(UDS_DL_SIZE_B3_ADDR == 0xFFFFD21Cu, "DL_SIZE_B3 revert");
_Static_assert(UDS_DL_SIZE_B2_ADDR == 0xFFFFD21Du, "DL_SIZE_B2 revert");
_Static_assert(UDS_DL_SIZE_B1_ADDR == 0xFFFFD21Eu, "DL_SIZE_B1 revert");
_Static_assert(UDS_DL_SIZE_B0_ADDR == 0xFFFFD21Fu, "DL_SIZE_B0 revert");
_Static_assert(UDS_DL_BLOCK_SEQ_ADDR == 0xFFFFD220u, "DL_BLOCK_SEQ revert");
_Static_assert(UDS_DL_STATE_ADDR == 0xFFFFD221u, "DL_STATE revert");
_Static_assert(UDS_DL_CHECKSUM_ADDR == 0xFFFFD222u, "DL_CHECKSUM revert");
_Static_assert(UDS_SESSION_LEVEL_ADDR == 0xFFFFDE5Cu, "session addr revert");
_Static_assert(UDS_SECURITY_LEVEL_ADDR == 0xFFFFD20Cu, "security addr revert");
_Static_assert(UDS_TESTER_PRESENT_ADDR == 0xFFFFD215u, "TP flag addr revert");
_Static_assert(UDS_MAX_RESPONSE_SIZE == 256, "UDS_MAX_RESPONSE_SIZE revert");

/* The addresses above live in the uds.h/uds.c bodies, so pin the pages
 * the test maps — a firmware move of any of them must also move the
 * mapping or the asserts fail loudly. One 4 KiB D page covers session,
 * security, TP flag, and the whole download image incl. the 4-byte
 * checksum; one 4 KiB flash sandbox covers the sid36 payload write. */
#define M7C2_D_PAGE_BASE   0xFFFFD000u
#define M7C2_D_PAGE_LEN    0x1000u
#define M7C2_FLASH_BASE    0x00070000u
#define M7C2_FLASH_LEN     0x1000u

#define M7C2_IN_D(addr, n) \
    ((addr) >= M7C2_D_PAGE_BASE && (addr) + (n) <= M7C2_D_PAGE_BASE + M7C2_D_PAGE_LEN)
#define M7C2_IN_FLASH(addr, n) \
    ((addr) >= M7C2_FLASH_BASE && (addr) + (n) <= M7C2_FLASH_BASE + M7C2_FLASH_LEN)

_Static_assert(M7C2_IN_D(UDS_SESSION_LEVEL_ADDR, 1), "session outside D page");
_Static_assert(M7C2_IN_D(UDS_SECURITY_LEVEL_ADDR, 1), "security outside D page");
_Static_assert(M7C2_IN_D(UDS_TESTER_PRESENT_ADDR, 1), "TP flag outside D page");
_Static_assert(M7C2_IN_D(UDS_DL_FORMAT_ADDR, 1), "DL format outside D page");
_Static_assert(M7C2_IN_D(UDS_DL_SIZE_B0_ADDR, 1), "DL size-B0 outside D page");
_Static_assert(M7C2_IN_D(UDS_DL_STATE_ADDR, 1), "DL state outside D page");
_Static_assert(M7C2_IN_D(UDS_DL_CHECKSUM_ADDR, 4), "DL checksum outside D page");
_Static_assert(M7C2_IN_FLASH(M7C2_FLASH_BASE, 4), "flash target outside sandbox");
_Static_assert(M7C2_FLASH_BASE + 4u <= UDS_DL_FLASH_END,
               "flash target beyond UDS_DL_FLASH_END");

/* ---- Linker-demanded DTC stubs (never executed on m7/c2 paths) ---- */
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

static volatile uint8_t *m7c2_u8(uint32_t addr)
{
    return (volatile uint8_t *)(uintptr_t)addr;
}

static volatile uint32_t *m7c2_u32(uint32_t addr)
{
    return (volatile uint32_t *)(uintptr_t)addr;
}

/* Caller-provided response buffer: exactly the documented contract size. */
static uint8_t resp[UDS_MAX_RESPONSE_SIZE];

/* Poison the ENTIRE download image (format..state + checksum, 14 bytes
 * at D218..D225) with a nonzero sentinel. Reject vectors assert it is
 * still 0xEE afterwards — a mutant that stores on a reject path turns
 * every one of those zero-ish expects red. */
static void dl_poison(void)
{
    for (uint32_t a = UDS_DL_FORMAT_ADDR; a <= UDS_DL_CHECKSUM_ADDR + 3u; a++)
        *m7c2_u8(a) = 0xEEu;
}

static void dl_expect_poison(const char *label)
{
    for (uint32_t a = UDS_DL_FORMAT_ADDR; a <= UDS_DL_CHECKSUM_ADDR + 3u; a++) {
        CHECK(*m7c2_u8(a) == 0xEEu,
              "%s: DL byte 0x%08X = 0x%02X want prime 0xEE",
              label, (unsigned)a, (unsigned)*m7c2_u8(a));
    }
}

/* Common negative-response check: real sid34/36/37 return the uds_negative_response
 * LENGTH (3) with [7F sid nrc], not a negative number (sid12/18 convention
 * differs — that stays in h2). */
static void expect_nrc(int rc, uint8_t sid, uint8_t nrc, const char *label)
{
    CHECK(rc == 3, "%s: rc=%d want 3", label, rc);
    if (rc == 3) {
        CHECK(resp[0] == UDS_SID_NEGATIVE_RESP && resp[1] == sid &&
              resp[2] == nrc,
              "%s: resp %02X %02X %02X want 7F %02X %02X",
              label, resp[0], resp[1], resp[2], sid, nrc);
    }
}

int main(void)
{
    void *pd = mmap((void *)(uintptr_t)M7C2_D_PAGE_BASE, M7C2_D_PAGE_LEN,
                    PROT_READ | PROT_WRITE,
                    MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED, -1, 0);
    if (pd == (void *)-1) {
        printf("FAIL: mmap(0xFFFFD000) failed\n");
        return 1;
    }
    void *pf = mmap((void *)(uintptr_t)M7C2_FLASH_BASE, M7C2_FLASH_LEN,
                    PROT_READ | PROT_WRITE,
                    MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED, -1, 0);
    if (pf == (void *)-1) {
        printf("FAIL: mmap(0x70000) failed\n");
        return 1;
    }

    /* Prime the flash sandbox with a nonzero sentinel: the sid36 payload
     * vector asserts the 4 written bytes AND that byte +4 keeps 0xEE
     * (no overrun). */
    for (uint32_t i = 0; i < M7C2_FLASH_LEN; i++)
        *m7c2_u8(M7C2_FLASH_BASE + i) = 0xEEu;

    int rc;

    /* (a) M7 through the REAL uds_handler (0x3E returns before the
     * dispatch lookup — no ROM read). TP flag primed nonzero before
     * every call: positive vectors want the store (0xEE → 1), reject
     * vectors want the prime untouched. */
    {
        static const uint8_t ok00[2] = { 0x3E, 0x00 };
        static const uint8_t bare[1] = { 0x3E };
        static const uint8_t bad80[2] = { 0x3E, 0x80 };
        static const uint8_t bad01[2] = { 0x3E, 0x01 };

        *m7c2_u8(UDS_TESTER_PRESENT_ADDR) = 0xEEu;
        rc = uds_handler(ok00, 2, resp);
        CHECK(rc == 2 && resp[0] == 0x7E && resp[1] == 0x00,
              "3E 00: rc=%d bytes %02X %02X want 2/7E/00",
              rc, resp[0], resp[1]);
        CHECK(*m7c2_u8(UDS_TESTER_PRESENT_ADDR) == 1u,
              "3E 00 TP flag = 0x%02X want 1 (store dropped?)",
              (unsigned)*m7c2_u8(UDS_TESTER_PRESENT_ADDR));

        *m7c2_u8(UDS_TESTER_PRESENT_ADDR) = 0xEEu;
        rc = uds_handler(bare, 1, resp);
        CHECK(rc == 2 && resp[0] == 0x7E && resp[1] == 0x00,
              "3E bare: rc=%d bytes %02X %02X want 2/7E/00",
              rc, resp[0], resp[1]);
        CHECK(*m7c2_u8(UDS_TESTER_PRESENT_ADDR) == 1u,
              "3E bare TP flag = 0x%02X want 1",
              (unsigned)*m7c2_u8(UDS_TESTER_PRESENT_ADDR));

        *m7c2_u8(UDS_TESTER_PRESENT_ADDR) = 0xEEu;
        rc = uds_handler(bad80, 2, resp);
        expect_nrc(rc, 0x3E, UDS_NRC_SUB_NOT_SUPPORTED, "3E 80");
        CHECK(*m7c2_u8(UDS_TESTER_PRESENT_ADDR) == 0xEEu,
              "3E 80 TP flag = 0x%02X want prime 0xEE (ungated store)",
              (unsigned)*m7c2_u8(UDS_TESTER_PRESENT_ADDR));

        *m7c2_u8(UDS_TESTER_PRESENT_ADDR) = 0xEEu;
        rc = uds_handler(bad01, 2, resp);
        expect_nrc(rc, 0x3E, UDS_NRC_SUB_NOT_SUPPORTED, "3E 01");
        CHECK(*m7c2_u8(UDS_TESTER_PRESENT_ADDR) == 0xEEu,
              "3E 01 TP flag = 0x%02X want prime 0xEE",
              (unsigned)*m7c2_u8(UDS_TESTER_PRESENT_ADDR));

        rc = uds_handler(NULL, 0, resp);
        expect_nrc(rc, 0x00, UDS_NRC_INCORRECT_MSG_LEN, "empty req");
    }

    /* (b) no DTC dispatch reached from the M7 pass. */
    CHECK(stub_sid12_calls == 0, "sid12 stub called %d times", stub_sid12_calls);
    CHECK(stub_sid14_calls == 0, "sid14 stub called %d times", stub_sid14_calls);
    CHECK(stub_sid18_calls == 0, "sid18 stub called %d times", stub_sid18_calls);

    /* Prime programming session + unlocked security (real inlines write
     * the mapped D page), then poison the DL image. */
    uds_set_session(UDS_SESSION_PROGRAMMING);
    uds_set_security(UDS_SECURITY_LEVEL_1);
    dl_poison();

    /* (c) sid34 session/security gates — poisoned image must survive. */
    {
        static const uint8_t good[7] =
            { 0x33, 0x07, 0x00, 0x00, 0x00, 0x00, 0x04 };

        uds_set_session(UDS_SESSION_DEFAULT);
        rc = obd_sid34_requestDownload(good, 7, resp);
        expect_nrc(rc, 0x34, UDS_NRC_CONDITIONS_NOT_CORRECT, "sid34 default-session");
        dl_expect_poison("sid34 default-session");
        uds_set_session(UDS_SESSION_PROGRAMMING);

        uds_set_security(UDS_SECURITY_LOCKED);
        rc = obd_sid34_requestDownload(good, 7, resp);
        expect_nrc(rc, 0x34, UDS_NRC_SECURITY_ACCESS_DENIED, "sid34 locked");
        dl_expect_poison("sid34 locked");
        uds_set_security(UDS_SECURITY_LEVEL_1);
    }

    /* (d) sid34 C2 validator: ONLY 3+3. Every vector is rejected with
     * 0x13 and leaves the poisoned image untouched. */
    {
        static const uint8_t two_two[5] = { 0x22, 0x00, 0x70, 0x00, 0x04 };
        static const uint8_t four_four[9] =
            { 0x44, 0x00, 0x07, 0x00, 0x00, 0x00, 0x00, 0x00, 0x04 };
        static const uint8_t good7[7] =
            { 0x33, 0x07, 0x00, 0x00, 0x00, 0x00, 0x04 };
        static const uint8_t zero_w[1] = { 0x00 };

        rc = obd_sid34_requestDownload(two_two, 5, resp);
        expect_nrc(rc, 0x34, UDS_NRC_INCORRECT_MSG_LEN, "sid34 2+2");
        dl_expect_poison("sid34 2+2");

        rc = obd_sid34_requestDownload(four_four, 9, resp);
        expect_nrc(rc, 0x34, UDS_NRC_INCORRECT_MSG_LEN, "sid34 4+4");
        dl_expect_poison("sid34 4+4");

        rc = obd_sid34_requestDownload(good7, 8, resp);
        expect_nrc(rc, 0x34, UDS_NRC_INCORRECT_MSG_LEN, "sid34 overlong");
        dl_expect_poison("sid34 overlong");

        rc = obd_sid34_requestDownload(good7, 6, resp);
        expect_nrc(rc, 0x34, UDS_NRC_INCORRECT_MSG_LEN, "sid34 short");
        dl_expect_poison("sid34 short");

        rc = obd_sid34_requestDownload(zero_w, 1, resp);
        expect_nrc(rc, 0x34, UDS_NRC_INCORRECT_MSG_LEN, "sid34 0-width");
        dl_expect_poison("sid34 0-width");

        rc = obd_sid34_requestDownload(NULL, 0, resp);
        expect_nrc(rc, 0x34, UDS_NRC_INCORRECT_MSG_LEN, "sid34 len0");
        dl_expect_poison("sid34 len0");
    }

    /* (e) sid34 range validation: beyond flash end and size 0 → 0x31,
     * image untouched. */
    {
        static const uint8_t beyond[7] =
            { 0x33, 0x08, 0x00, 0x00, 0x00, 0x00, 0x10 };
        static const uint8_t zero_sz[7] =
            { 0x33, 0x07, 0x00, 0x00, 0x00, 0x00, 0x00 };

        rc = obd_sid34_requestDownload(beyond, 7, resp);
        expect_nrc(rc, 0x34, UDS_NRC_REQUEST_OUT_OF_RANGE, "sid34 beyond-flash");
        dl_expect_poison("sid34 beyond-flash");

        rc = obd_sid34_requestDownload(zero_sz, 7, resp);
        expect_nrc(rc, 0x34, UDS_NRC_REQUEST_OUT_OF_RANGE, "sid34 size0");
        dl_expect_poison("sid34 size0");
    }

    /* (f) sid34 happy path: 3+3, addr 0x00070000, size 4. Image was
     * poisoned 0xEE, so every stored byte — including the zero ones —
     * is a primed-nonzero → new-value transition (killable). */
    {
        static const uint8_t good[7] =
            { 0x33, 0x07, 0x00, 0x00, 0x00, 0x00, 0x04 };

        rc = obd_sid34_requestDownload(good, 7, resp);
        CHECK(rc == 5, "sid34 happy: rc=%d want 5", rc);
        if (rc == 5) {
            CHECK(resp[0] == 0x74 && resp[1] == 0x00 && resp[2] == 0x01 &&
                  resp[3] == 0x00 && resp[4] == 0x80,
                  "sid34 happy: resp %02X %02X %02X %02X %02X want 74 00 01 00 80",
                  resp[0], resp[1], resp[2], resp[3], resp[4]);
        }
        CHECK(*m7c2_u8(UDS_DL_FORMAT_ADDR) == 0x33u,
              "DL format = 0x%02X want 0x33",
              (unsigned)*m7c2_u8(UDS_DL_FORMAT_ADDR));
        CHECK(*m7c2_u8(UDS_DL_MEM_HI_ADDR) == 0x07u,
              "DL MEM_HI = 0x%02X want 0x07 (BE24 store)",
              (unsigned)*m7c2_u8(UDS_DL_MEM_HI_ADDR));
        CHECK(*m7c2_u8(UDS_DL_MEM_MID_ADDR) == 0x00u,
              "DL MEM_MID = 0x%02X want 0 (prime 0xEE)",
              (unsigned)*m7c2_u8(UDS_DL_MEM_MID_ADDR));
        CHECK(*m7c2_u8(UDS_DL_MEM_LO_ADDR) == 0x00u,
              "DL MEM_LO = 0x%02X want 0 (prime 0xEE)",
              (unsigned)*m7c2_u8(UDS_DL_MEM_LO_ADDR));
        CHECK(*m7c2_u8(UDS_DL_SIZE_B3_ADDR) == 0x00u,
              "DL SIZE_B3 = 0x%02X want 0 (prime 0xEE)",
              (unsigned)*m7c2_u8(UDS_DL_SIZE_B3_ADDR));
        CHECK(*m7c2_u8(UDS_DL_SIZE_B2_ADDR) == 0x00u,
              "DL SIZE_B2 = 0x%02X want 0 (prime 0xEE)",
              (unsigned)*m7c2_u8(UDS_DL_SIZE_B2_ADDR));
        CHECK(*m7c2_u8(UDS_DL_SIZE_B1_ADDR) == 0x00u,
              "DL SIZE_B1 = 0x%02X want 0 (prime 0xEE, kills left-align)",
              (unsigned)*m7c2_u8(UDS_DL_SIZE_B1_ADDR));
        CHECK(*m7c2_u8(UDS_DL_SIZE_B0_ADDR) == 0x04u,
              "DL SIZE_B0 = 0x%02X want 0x04 (right-aligned BE32 low byte)",
              (unsigned)*m7c2_u8(UDS_DL_SIZE_B0_ADDR));
        CHECK(*m7c2_u8(UDS_DL_BLOCK_SEQ_ADDR) == 0x01u,
              "DL seq = 0x%02X want 1",
              (unsigned)*m7c2_u8(UDS_DL_BLOCK_SEQ_ADDR));
        CHECK(*m7c2_u8(UDS_DL_STATE_ADDR) == UDS_DL_STATE_ACTIVE,
              "DL state = 0x%02X want ACTIVE 1",
              (unsigned)*m7c2_u8(UDS_DL_STATE_ADDR));
        CHECK(*m7c2_u32(UDS_DL_CHECKSUM_ADDR) == 0u,
              "DL checksum = 0x%08lX want 0 (prime 0xEEEEEEEE)",
              (unsigned long)*m7c2_u32(UDS_DL_CHECKSUM_ADDR));
    }

    /* (g) sid36 chain over the real TU. */
    {
        static const uint8_t payload[4] = { 0xDE, 0xAD, 0xBE, 0xEF };
        static const uint8_t fat[8] =
            { 0xDE, 0xAD, 0xBE, 0xEF, 0x11, 0x22, 0x33, 0x44 };

        /* wrong block sequence → 0x73, flash target untouched. */
        rc = obd_sid36_transferData(2, payload, 4, resp);
        expect_nrc(rc, 0x36, UDS_NRC_WRONG_BLOCK_SEQ, "sid36 seq2");
        CHECK(*m7c2_u8(M7C2_FLASH_BASE) == 0xEEu,
              "sid36 seq2 wrote flash byte0 = 0x%02X want prime 0xEE",
              (unsigned)*m7c2_u8(M7C2_FLASH_BASE));

        /* correct seq → positive, 4 bytes land, neighbor keeps prime,
         * checksum/remaining/addr/seq all update. */
        rc = obd_sid36_transferData(1, payload, 4, resp);
        CHECK(rc == 2 && resp[0] == 0x76 && resp[1] == 0x01,
              "sid36 happy: rc=%d bytes %02X %02X want 2/76/01",
              rc, resp[0], resp[1]);
        CHECK(*m7c2_u8(M7C2_FLASH_BASE + 0) == 0xDEu &&
              *m7c2_u8(M7C2_FLASH_BASE + 1) == 0xADu &&
              *m7c2_u8(M7C2_FLASH_BASE + 2) == 0xBEu &&
              *m7c2_u8(M7C2_FLASH_BASE + 3) == 0xEFu,
              "sid36 payload: %02X %02X %02X %02X want DE AD BE EF",
              (unsigned)*m7c2_u8(M7C2_FLASH_BASE + 0),
              (unsigned)*m7c2_u8(M7C2_FLASH_BASE + 1),
              (unsigned)*m7c2_u8(M7C2_FLASH_BASE + 2),
              (unsigned)*m7c2_u8(M7C2_FLASH_BASE + 3));
        CHECK(*m7c2_u8(M7C2_FLASH_BASE + 4) == 0xEEu,
              "sid36 overran: byte4 = 0x%02X want prime 0xEE",
              (unsigned)*m7c2_u8(M7C2_FLASH_BASE + 4));
        CHECK(*m7c2_u32(UDS_DL_CHECKSUM_ADDR) == 0x338u,
              "sid36 checksum = 0x%08lX want 0x338",
              (unsigned long)*m7c2_u32(UDS_DL_CHECKSUM_ADDR));
        CHECK(*m7c2_u8(UDS_DL_SIZE_B0_ADDR) == 0x00u,
              "sid36 remaining B0 = 0x%02X want 0 (was 4)",
              (unsigned)*m7c2_u8(UDS_DL_SIZE_B0_ADDR));
        CHECK(*m7c2_u8(UDS_DL_MEM_LO_ADDR) == 0x04u,
              "sid36 MEM_LO = 0x%02X want 0x04 (target advanced)",
              (unsigned)*m7c2_u8(UDS_DL_MEM_LO_ADDR));
        CHECK(*m7c2_u8(UDS_DL_BLOCK_SEQ_ADDR) == 0x02u,
              "sid36 seq = 0x%02X want 2",
              (unsigned)*m7c2_u8(UDS_DL_BLOCK_SEQ_ADDR));

        /* payload > remaining: capped to 0 — no write, checksum stable,
         * seq still advances (positive response). */
        rc = obd_sid36_transferData(2, fat, 8, resp);
        CHECK(rc == 2 && resp[0] == 0x76 && resp[1] == 0x02,
              "sid36 capped: rc=%d bytes %02X %02X want 2/76/02",
              rc, resp[0], resp[1]);
        CHECK(*m7c2_u8(M7C2_FLASH_BASE + 4) == 0xEEu,
              "sid36 capped overran: byte4 = 0x%02X want prime 0xEE",
              (unsigned)*m7c2_u8(M7C2_FLASH_BASE + 4));
        CHECK(*m7c2_u32(UDS_DL_CHECKSUM_ADDR) == 0x338u,
              "sid36 capped checksum = 0x%08lX want 0x338",
              (unsigned long)*m7c2_u32(UDS_DL_CHECKSUM_ADDR));

        /* data_len 0 → 0x13 (state still active, seq now 3). */
        rc = obd_sid36_transferData(3, payload, 0, resp);
        expect_nrc(rc, 0x36, UDS_NRC_INCORRECT_MSG_LEN, "sid36 len0");

        /* state ≠ ACTIVE → 0x22, state byte keeps its prime. */
        *m7c2_u8(UDS_DL_STATE_ADDR) = 0xEEu;
        rc = obd_sid36_transferData(4, payload, 4, resp);
        expect_nrc(rc, 0x36, UDS_NRC_CONDITIONS_NOT_CORRECT, "sid36 idle");
        CHECK(*m7c2_u8(UDS_DL_STATE_ADDR) == 0xEEu,
              "sid36 idle: state = 0x%02X want prime 0xEE",
              (unsigned)*m7c2_u8(UDS_DL_STATE_ADDR));
        *m7c2_u8(UDS_DL_STATE_ADDR) = UDS_DL_STATE_ACTIVE;

        /* default session → 0x22 (session gate first). */
        uds_set_session(UDS_SESSION_DEFAULT);
        rc = obd_sid36_transferData(4, payload, 4, resp);
        expect_nrc(rc, 0x36, UDS_NRC_CONDITIONS_NOT_CORRECT, "sid36 default-session");
        uds_set_session(UDS_SESSION_PROGRAMMING);
    }

    /* (h) sid37 exit chain. */
    {
        /* remaining ≠ 0 → 0x71, state byte keeps its nonzero prime. */
        *m7c2_u8(UDS_DL_SIZE_B0_ADDR) = 0x04u;
        *m7c2_u8(UDS_DL_STATE_ADDR) = 0x01u;
        rc = obd_sid37_requestTransferExit(resp);
        expect_nrc(rc, 0x37, UDS_NRC_TRANSFER_SUSPENDED, "sid37 remaining");
        CHECK(*m7c2_u8(UDS_DL_STATE_ADDR) == 0x01u,
              "sid37 remaining: state = 0x%02X want 1 (cleared on reject)",
              (unsigned)*m7c2_u8(UDS_DL_STATE_ADDR));

        /* happy: remaining 0 (SIZE B3..B0 all 0 — the firmware gate
         * reads exactly those bytes, so they CANNOT be primed nonzero
         * here and their clear stores are 0→0; asserted stay-0 below),
         * state 1, seq 2, checksum 0x338, format 0x33, and MEM_HI /
         * MEM_MID / MEM_LO primed nonzero — each of those clears is a
         * killable primed-nonzero → 0 transition. */
        *m7c2_u8(UDS_DL_SIZE_B0_ADDR) = 0x00u;
        *m7c2_u8(UDS_DL_STATE_ADDR) = 0x01u;
        *m7c2_u8(UDS_DL_BLOCK_SEQ_ADDR) = 0x02u;
        *m7c2_u32(UDS_DL_CHECKSUM_ADDR) = 0x338u;
        *m7c2_u8(UDS_DL_FORMAT_ADDR) = 0x33u;
        *m7c2_u8(UDS_DL_MEM_HI_ADDR) = 0x07u;
        *m7c2_u8(UDS_DL_MEM_MID_ADDR) = 0xEEu;
        *m7c2_u8(UDS_DL_MEM_LO_ADDR) = 0x04u;
        rc = obd_sid37_requestTransferExit(resp);
        CHECK(rc == 2 && resp[0] == 0x77 && resp[1] == 0x00,
              "sid37 happy: rc=%d bytes %02X %02X want 2/77/00",
              rc, resp[0], resp[1]);
        CHECK(*m7c2_u8(UDS_DL_STATE_ADDR) == 0x00u,
              "sid37 state = 0x%02X want 0 (was 1)",
              (unsigned)*m7c2_u8(UDS_DL_STATE_ADDR));
        CHECK(*m7c2_u8(UDS_DL_BLOCK_SEQ_ADDR) == 0x00u,
              "sid37 seq = 0x%02X want 0 (was 2)",
              (unsigned)*m7c2_u8(UDS_DL_BLOCK_SEQ_ADDR));
        CHECK(*m7c2_u32(UDS_DL_CHECKSUM_ADDR) == 0u,
              "sid37 checksum = 0x%08lX want 0 (was 0x338)",
              (unsigned long)*m7c2_u32(UDS_DL_CHECKSUM_ADDR));
        CHECK(*m7c2_u8(UDS_DL_FORMAT_ADDR) == 0x00u,
              "sid37 format = 0x%02X want 0 (was 0x33)",
              (unsigned)*m7c2_u8(UDS_DL_FORMAT_ADDR));
        CHECK(*m7c2_u8(UDS_DL_MEM_HI_ADDR) == 0x00u,
              "sid37 MEM_HI = 0x%02X want 0 (was 7)",
              (unsigned)*m7c2_u8(UDS_DL_MEM_HI_ADDR));
        CHECK(*m7c2_u8(UDS_DL_MEM_MID_ADDR) == 0x00u,
              "sid37 MEM_MID = 0x%02X want 0 (was prime 0xEE)",
              (unsigned)*m7c2_u8(UDS_DL_MEM_MID_ADDR));
        CHECK(*m7c2_u8(UDS_DL_MEM_LO_ADDR) == 0x00u,
              "sid37 MEM_LO = 0x%02X want 0 (was 4)",
              (unsigned)*m7c2_u8(UDS_DL_MEM_LO_ADDR));
        /* SIZE clear stores: the remaining==0 gate forces SIZE to all 0
         * BEFORE the happy path, so nonzero→0 is unreachable here —
         * assert the bytes stay 0 after the clear stores (a write of a
         * nonzero residue, e.g. a left-shifted leftover, is red). */
        CHECK(*m7c2_u8(UDS_DL_SIZE_B3_ADDR) == 0x00u &&
              *m7c2_u8(UDS_DL_SIZE_B2_ADDR) == 0x00u &&
              *m7c2_u8(UDS_DL_SIZE_B1_ADDR) == 0x00u &&
              *m7c2_u8(UDS_DL_SIZE_B0_ADDR) == 0x00u,
              "sid37 SIZE B3..B0 = %02X %02X %02X %02X want 0 0 0 0",
              (unsigned)*m7c2_u8(UDS_DL_SIZE_B3_ADDR),
              (unsigned)*m7c2_u8(UDS_DL_SIZE_B2_ADDR),
              (unsigned)*m7c2_u8(UDS_DL_SIZE_B1_ADDR),
              (unsigned)*m7c2_u8(UDS_DL_SIZE_B0_ADDR));

        /* state ≠ ACTIVE → 0x22, prime survives. */
        *m7c2_u8(UDS_DL_STATE_ADDR) = 0xEEu;
        rc = obd_sid37_requestTransferExit(resp);
        expect_nrc(rc, 0x37, UDS_NRC_CONDITIONS_NOT_CORRECT, "sid37 idle");
        CHECK(*m7c2_u8(UDS_DL_STATE_ADDR) == 0xEEu,
              "sid37 idle: state = 0x%02X want prime 0xEE",
              (unsigned)*m7c2_u8(UDS_DL_STATE_ADDR));
        *m7c2_u8(UDS_DL_STATE_ADDR) = 0x01u;

        /* default session → 0x22 (session gate first), state survives. */
        uds_set_session(UDS_SESSION_DEFAULT);
        rc = obd_sid37_requestTransferExit(resp);
        expect_nrc(rc, 0x37, UDS_NRC_CONDITIONS_NOT_CORRECT, "sid37 default-session");
        CHECK(*m7c2_u8(UDS_DL_STATE_ADDR) == 0x01u,
              "sid37 default-session: state = 0x%02X want 1",
              (unsigned)*m7c2_u8(UDS_DL_STATE_ADDR));
        uds_set_session(UDS_SESSION_PROGRAMMING);
    }

    /* (i) stubs never executed across the whole run. */
    CHECK(stub_sid12_calls == 0, "sid12 stub called %d times (end)", stub_sid12_calls);
    CHECK(stub_sid14_calls == 0, "sid14 stub called %d times (end)", stub_sid14_calls);
    CHECK(stub_sid18_calls == 0, "sid18 stub called %d times (end)", stub_sid18_calls);

    munmap((void *)(uintptr_t)M7C2_FLASH_BASE, M7C2_FLASH_LEN);
    munmap((void *)(uintptr_t)M7C2_D_PAGE_BASE, M7C2_D_PAGE_LEN);

    if (failures == 0) {
        printf("PASS link_m7_c2_tp_sid34 (real uds.c TU)\n");
    } else {
        printf("%d FAILURES link_m7_c2_tp_sid34\n", failures);
    }
    return failures != 0;
}

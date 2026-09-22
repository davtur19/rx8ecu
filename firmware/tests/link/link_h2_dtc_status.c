/*
 * link_h2_dtc_status.c — Link pilot h2: compile-link-run against the REAL
 * DTC status path in firmware/c/dtc.c + the REAL dtc_read_status inline in
 * firmware/include/dtc.h (H2 SEVERITY|FLAGS3 composite fix), not a model
 * replica.
 *
 * Mechanism proof: links the real dtc.c TU, so a firmware revert of any
 * reader (obd_sid18_readDTCInfo, obd_sid12_readDTCByStatus,
 * dtc_find_worst_priority) or of the dtc_read_status inline (dtc.h:447:
 * `sev | fl3` reading +0x07/+0x09 instead of the never-written-by-readers
 * TYPE byte +0x06) fails this binary at run time, and a signature change
 * fails at compile time (extern decls via dtc.h).
 *
 * Refactor-path coverage (the whole point of h2 scoping):
 *   - composite inline: dtc_read_status returns SEVERITY|FLAGS3; the test
 *     poisons the TYPE byte (+0x06) to a value the composite can never
 *     produce, so a TYPE-reading mutant diverges on BOTH nonzero and zero
 *     expected composites;
 *   - writer roundtrip: dtc_state_machine(mode 1, SET) writes TYPE=0xC0,
 *     SEVERITY=0x80, FLAGS3|=0x10 through the real TU, then the real
 *     readers observe the composite;
 *   - real readers: sid18 sub 0x03 counts by mask through
 *     dtc_read_status over ALL 21 slots; sid12 sub 2/4 emits the status
 *     byte verbatim; worst_priority ranks by the SEVERITY byte and
 *     reports the composite (i<20 ROM quirk stays);
 *   - pending clear: sid18 sub 0xFF clears FLAGS3 pending for every slot
 *     (real write path), then counts occupied codes.
 *
 * Host execution boundary (same mechanism as link_m2_checksum — this is
 * the same TU and the same MMIO page):
 *   - Zero stubs: dtc.c has no undefined externs (`nm -u dtc.o` clean) —
 *     exactly like can.c (h1) and engine.c (h4).
 *   - MMIO is real: the SH-2 0xFFFF8xxx RAM page does not exist on the
 *     host, so the test maps ONE 4 KiB page at 0xFFFF8000 with
 *     mmap(MAP_FIXED), covering guard words 0xFFFF8920/24, the primary
 *     table 0xFFFF8928..0xFFFF8D6C (21 x 0x34), and the slot-index byte
 *     0xFFFF8D70. Every load/store the exercised functions perform then
 *     executes for real. No FW_HOST_TEST accessor: dtc_read_status is a
 *     public static inline in dtc.h, callable from the test TU directly.
 *   - No constructor/init-time MMIO: dtc.c file-scope statics are plain
 *     zero-init (dtc_slot_count, dtc_backup_count).
 *
 * Proves (every assert killable; zero-expects are primed first):
 *   (a) dtc_read_status == SEVERITY|FLAGS3 with TYPE byte poisoned 0x00
 *       (composite 0x90) and with TYPE byte poisoned 0xFF (composite 0 —
 *       a TYPE reader returns 0xFF here, so the zero-assert is not
 *       vacuous);
 *   (b) writer roundtrip: real dtc_state_machine SET persists
 *       TYPE=0xC0 / SEV=0x80 / FLAGS3|=0x10 and the inline reads 0x90;
 *   (c) sid18 sub 0x03: mask 0x80 -> 2, mask 0x10 -> 2, mask 0x20 -> 1
 *       (pending slot), bad sub -> NRC 0x12;
 *   (d) sid12 sub 2: len 8 with status bytes 0x90; mask 0x20 emits the
 *       pending record with status 0x20; sub 4 mirrors sub 2; bad sub ->
 *       NRC 0x12;
 *   (e) worst_priority mask 0x80: count 2, lowest-SEVERITY code 0x0202,
 *       status 0x90; mask 0x20: count 1, code 0x0505, status 0x20;
 *   (f) sid18 sub 0xFF clears pending: inline(6) 0x20 -> 0, mask 0x20
 *       count 1 -> 0, mask 0x80 count stays 2, occupied-code count 4,
 *       sid12 mask 0x20 len 5 -> 2.
 *
 * Build (see firmware/tests/Makefile link-check):
 *   gcc -std=c11 -Wall -Wextra -Werror -Wno-error=unused-function -O2 \
 *       -I../include link/link_h2_dtc_status.c ../c/dtc.c \
 *       -o /tmp/fwtest/link_h2_dtc_status
 */
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>

#include "dtc.h"
#include "uds.h"

/* Extern declarations come from the real dtc.h/uds.h (linking the real
 * dtc.c TU): a signature change in firmware breaks this build. Pin the
 * H2 contract values so a revert breaks the build, not just the run. */
_Static_assert(DTC_PRIMARY_TABLE_BASE == 0xFFFF8928, "DTC_PRIMARY_TABLE_BASE revert");
_Static_assert(DTC_PRIMARY_ENTRY_SIZE == 0x34, "DTC_PRIMARY_ENTRY_SIZE revert");
_Static_assert(DTC_PRIMARY_MAX_SLOTS == 21, "DTC_PRIMARY_MAX_SLOTS revert");
_Static_assert(DTC_REC_TYPE_OFFSET == 0x06, "DTC_REC_TYPE_OFFSET revert");
_Static_assert(DTC_REC_SEVERITY_OFFSET == 0x07, "DTC_REC_SEVERITY_OFFSET revert");
_Static_assert(DTC_REC_FLAGS3_OFFSET == 0x09, "DTC_REC_FLAGS3_OFFSET revert");
_Static_assert(DTC_STATUS_CONFIRMED == 0x80, "DTC_STATUS_CONFIRMED revert");
_Static_assert(DTC_STATUS_TEST_FAILED == 0x10, "DTC_STATUS_TEST_FAILED revert");
_Static_assert(DTC_STATUS_PENDING == 0x20, "DTC_STATUS_PENDING revert");
_Static_assert(UDS_NRC_SUB_NOT_SUPPORTED == 0x12, "NRC 0x12 revert");

/* The reader loops and the slot-index byte live in the .c body / header
 * macros, so pin the addresses the test maps — a firmware move of the
 * primary table must also move this mapping or the asserts fail loudly.
 * One 4 KiB page at 0xFFFF8000 covers guards 0xFFFF8920/24, the table
 * 0xFFFF8928..0xFFFF8D6C, and 0xFFFF8D70 (same page as link_m2). */
#define H2_PAGE_BASE 0xFFFF8000u
#define H2_PAGE_LEN  0x1000u

static int failures = 0;

#define CHECK(cond, ...) do { \
    if (!(cond)) { printf("FAIL: "); printf(__VA_ARGS__); printf("\n"); failures++; } \
} while (0)

static volatile uint8_t *h2_u8(uint32_t addr)
{
    return (volatile uint8_t *)(uintptr_t)addr;
}

static volatile uint16_t *h2_u16(uint32_t addr)
{
    return (volatile uint16_t *)(uintptr_t)addr;
}

static uint32_t h2_slot_addr(unsigned slot)
{
    return (uint32_t)DTC_PRIMARY_TABLE_BASE
        + (uint32_t)slot * (uint32_t)DTC_PRIMARY_ENTRY_SIZE;
}

/* Zero the whole mapped table region (21 records -> codes 0x0000 =
 * empty, all status bytes 0). */
static void h2_zero_table(void)
{
    uint32_t base = (uint32_t)DTC_PRIMARY_TABLE_BASE;
    uint32_t len = (uint32_t)DTC_PRIMARY_MAX_SLOTS * (uint32_t)DTC_PRIMARY_ENTRY_SIZE;
    for (uint32_t a = base; a < base + len; a++)
        *h2_u8(a) = 0x00u;
}

/* Write slot record fields used by the h2 scenarios. */
static void h2_setup_slot(unsigned slot, uint16_t code,
                          uint8_t type, uint8_t sev, uint8_t fl3)
{
    uint32_t base = h2_slot_addr(slot);
    *h2_u16(base + DTC_REC_CODE_OFFSET) = code;
    *h2_u8(base + DTC_REC_TYPE_OFFSET) = type;
    *h2_u8(base + DTC_REC_SEVERITY_OFFSET) = sev;
    *h2_u8(base + DTC_REC_FLAGS3_OFFSET) = fl3;
}

int main(void)
{
    void *p = mmap((void *)(uintptr_t)H2_PAGE_BASE, H2_PAGE_LEN,
                   PROT_READ | PROT_WRITE,
                   MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED, -1, 0);
    if (p == (void *)-1) {
        printf("FAIL: mmap(0xFFFF8000) failed\n");
        return 1;
    }

    h2_zero_table();

    /* Fixture slots (TYPE byte poisoned against the composite):
     *   s3 code 0x0202: TYPE 0x00, SEV 0x80, FL3 0x10 -> composite 0x90
     *   s4 code 0x0303: TYPE 0xFF, SEV 0x00, FL3 0x00 -> composite 0
     *       (occupied but status 0: must not match any nonzero mask)
     *   s6 code 0x0505: TYPE 0x00, SEV 0x00, FL3 0x20 -> composite 0x20
     *   s5 code 0x0404: written by the REAL SET path below, not here. */
    h2_setup_slot(3, 0x0202u, 0x00u, DTC_STATUS_CONFIRMED,
                  DTC_STATUS_TEST_FAILED);
    h2_setup_slot(4, 0x0303u, 0xFFu, 0x00u, 0x00u);
    h2_setup_slot(6, 0x0505u, 0x00u, 0x00u, DTC_STATUS_PENDING);

    /* (a) composite inline vs poisoned TYPE byte. Nonzero expect kills
     * TYPE/SEV-only/FL3-only readers; the zero expect is primed by the
     * nonzero one and is killable because TYPE holds 0xFF. */
    CHECK(dtc_read_status(3) == (DTC_STATUS_CONFIRMED | DTC_STATUS_TEST_FAILED),
          "inline s3 = 0x%02X want 0x90", dtc_read_status(3));
    CHECK(dtc_read_status(6) == DTC_STATUS_PENDING,
          "inline s6 = 0x%02X want 0x20", dtc_read_status(6));
    CHECK(dtc_read_status(4) == 0,
          "inline s4 (TYPE=0xFF) = 0x%02X want 0", dtc_read_status(4));

    /* (b) writer roundtrip through the REAL dtc_state_machine SET path.
     * Slot 5 starts fully zero: the SET write itself makes every byte
     * nonzero, so each post-assert is killable by a writer that drops
     * that store, and the composite 0x90 kills every inline mutant. */
    *h2_u16(h2_slot_addr(5) + DTC_REC_CODE_OFFSET) = 0x0404u;
    dtc_state_machine(0x0404u, 1);
    CHECK(*h2_u8(h2_slot_addr(5) + DTC_REC_TYPE_OFFSET) == 0xC0u,
          "SET TYPE s5 = 0x%02X want 0xC0",
          *h2_u8(h2_slot_addr(5) + DTC_REC_TYPE_OFFSET));
    CHECK(*h2_u8(h2_slot_addr(5) + DTC_REC_SEVERITY_OFFSET) == 0x80u,
          "SET SEV s5 = 0x%02X want 0x80",
          *h2_u8(h2_slot_addr(5) + DTC_REC_SEVERITY_OFFSET));
    CHECK((*h2_u8(h2_slot_addr(5) + DTC_REC_FLAGS3_OFFSET) & DTC_STATUS_TEST_FAILED) != 0,
          "SET FLAGS3 s5 = 0x%02X lacks 0x10",
          *h2_u8(h2_slot_addr(5) + DTC_REC_FLAGS3_OFFSET));
    CHECK(dtc_read_status(5) == (DTC_STATUS_CONFIRMED | DTC_STATUS_TEST_FAILED),
          "inline s5 after SET = 0x%02X want 0x90", dtc_read_status(5));

    /* (c) sid18 sub 0x03: count by mask over all 21 slots. Expected
     * counts are all nonzero (primed), so a zero-returning mutant is
     * red on the first line. */
    uint8_t buf[256];
    int rc;

    memset(buf, 0xEE, sizeof buf);
    rc = obd_sid18_readDTCInfo(0x03, DTC_STATUS_CONFIRMED, buf);
    CHECK(rc == 3 && buf[0] == 0x58 && buf[1] == 0x03 && buf[2] == 2,
          "sid18 0x80: rc=%d bytes %02X %02X %02X want 3/58/03/02",
          rc, buf[0], buf[1], buf[2]);

    memset(buf, 0xEE, sizeof buf);
    rc = obd_sid18_readDTCInfo(0x03, DTC_STATUS_TEST_FAILED, buf);
    CHECK(rc == 3 && buf[2] == 2,
          "sid18 0x10: rc=%d count=%u want 3/2", rc, buf[2]);

    memset(buf, 0xEE, sizeof buf);
    rc = obd_sid18_readDTCInfo(0x03, DTC_STATUS_PENDING, buf);
    CHECK(rc == 3 && buf[2] == 1,
          "sid18 0x20: rc=%d count=%u want 3/1", rc, buf[2]);

    rc = obd_sid18_readDTCInfo(0x01, DTC_STATUS_CONFIRMED, buf);
    CHECK(rc == -UDS_NRC_SUB_NOT_SUPPORTED,
          "sid18 bad sub: rc=%d want %d", rc, -UDS_NRC_SUB_NOT_SUPPORTED);

    /* (d) sid12 sub 2/4: status byte emitted verbatim. Occupied s4 has
     * composite 0 so it must NOT appear under mask 0x80 (a TYPE reader
     * would emit it via TYPE=0xFF -> len 9, red here). */
    memset(buf, 0xEE, sizeof buf);
    rc = obd_sid12_readDTCByStatus(2, DTC_STATUS_CONFIRMED, buf);
    CHECK(rc == 8 && buf[0] == 0x52 && buf[1] == 0x02,
          "sid12 0x80: rc=%d hdr %02X %02X want 8/52/02",
          rc, buf[0], buf[1]);
    CHECK(buf[2] == 0x02 && buf[3] == 0x02 && buf[4] == 0x90,
          "sid12 rec1 %02X %02X %02X want 02 02 90", buf[2], buf[3], buf[4]);
    CHECK(buf[5] == 0x04 && buf[6] == 0x04 && buf[7] == 0x90,
          "sid12 rec2 %02X %02X %02X want 04 04 90", buf[5], buf[6], buf[7]);

    memset(buf, 0xEE, sizeof buf);
    rc = obd_sid12_readDTCByStatus(2, DTC_STATUS_PENDING, buf);
    CHECK(rc == 5 && buf[2] == 0x05 && buf[3] == 0x05 && buf[4] == 0x20,
          "sid12 0x20: rc=%d rec %02X %02X %02X want 5/05 05 20",
          rc, buf[2], buf[3], buf[4]);

    memset(buf, 0xEE, sizeof buf);
    rc = obd_sid12_readDTCByStatus(4, DTC_STATUS_CONFIRMED, buf);
    CHECK(rc == 8 && buf[1] == 0x04,
          "sid12 sub4: rc=%d sub byte %02X want 8/04", rc, buf[1]);

    rc = obd_sid12_readDTCByStatus(3, DTC_STATUS_CONFIRMED, buf);
    CHECK(rc == -UDS_NRC_SUB_NOT_SUPPORTED,
          "sid12 bad sub: rc=%d want %d", rc, -UDS_NRC_SUB_NOT_SUPPORTED);

    /* (e) worst_priority: out params primed to 0xEE so a function that
     * stops writing them is red even on the zero-path; expected counts
     * and codes are nonzero. */
    uint16_t wcode = 0xEEEEu;
    uint8_t wsev = 0xEEu, wst = 0xEEu;
    int n = dtc_find_worst_priority(DTC_STATUS_CONFIRMED, &wcode, &wsev, &wst);
    CHECK(n == 2 && wcode == 0x0202u && wsev == 0x80u && wst == 0x90u,
          "worst 0x80: n=%d code=0x%04X sev=0x%02X st=0x%02X want 2/0202/80/90",
          n, wcode, wsev, wst);

    wcode = 0xEEEEu;
    wsev = 0xEEu;
    wst = 0xEEu;
    n = dtc_find_worst_priority(DTC_STATUS_PENDING, &wcode, &wsev, &wst);
    CHECK(n == 1 && wcode == 0x0505u && wsev == 0x00u && wst == 0x20u,
          "worst 0x20: n=%d code=0x%04X sev=0x%02X st=0x%02X want 1/0505/00/20",
          n, wcode, wsev, wst);

    /* (f) sid18 sub 0xFF: clear pending everywhere, then report occupied
     * codes. Prime the nonzero pending state again before the call so
     * the post-clear zeros are killable by a no-clear mutant. */
    CHECK(dtc_read_status(6) == DTC_STATUS_PENDING,
          "prime s6 pending = 0x%02X want 0x20", dtc_read_status(6));

    memset(buf, 0xEE, sizeof buf);
    rc = obd_sid18_readDTCInfo(0xFF, 0x00, buf);
    CHECK(rc == 3 && buf[0] == 0x58 && buf[1] == 0xFF && buf[2] == 4,
          "sid18 0xFF: rc=%d bytes %02X %02X %02X want 3/58/FF/04",
          rc, buf[0], buf[1], buf[2]);

    CHECK(dtc_read_status(6) == 0,
          "s6 after pending clear = 0x%02X want 0", dtc_read_status(6));
    CHECK(dtc_read_status(3) == (DTC_STATUS_CONFIRMED | DTC_STATUS_TEST_FAILED),
          "s3 confirmed survives clear = 0x%02X want 0x90", dtc_read_status(3));

    memset(buf, 0xEE, sizeof buf);
    rc = obd_sid18_readDTCInfo(0x03, DTC_STATUS_PENDING, buf);
    CHECK(rc == 3 && buf[2] == 0,
          "sid18 0x20 after clear: rc=%d count=%u want 3/0", rc, buf[2]);

    memset(buf, 0xEE, sizeof buf);
    rc = obd_sid18_readDTCInfo(0x03, DTC_STATUS_CONFIRMED, buf);
    CHECK(rc == 3 && buf[2] == 2,
          "sid18 0x80 after clear: rc=%d count=%u want 3/2", rc, buf[2]);

    memset(buf, 0xEE, sizeof buf);
    rc = obd_sid12_readDTCByStatus(2, DTC_STATUS_PENDING, buf);
    CHECK(rc == 2,
          "sid12 0x20 after clear: rc=%d want 2", rc);

    munmap(p, H2_PAGE_LEN);

    if (failures == 0) {
        printf("PASS link_h2_dtc_status (real dtc.c TU + dtc.h inline)\n");
    } else {
        printf("%d FAILURES link_h2_dtc_status\n", failures);
    }
    return failures != 0;
}

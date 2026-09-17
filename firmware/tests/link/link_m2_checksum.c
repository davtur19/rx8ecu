/*
 * link_m2_checksum.c — Link pilot m2: compile-link-run against the REAL
 * dtc_region_checksum_validate_8928 in firmware/c/dtc.c (MMIO pilot,
 * class M), not a model replica.
 *
 * Mechanism proof: links the real dtc.c TU, so a firmware revert of the M2
 * guard logic (`0xFFFF8920/0xFFFF8924` blank check) or the 15-byte
 * per-entry sum (`(sum & 0xFFu) != 0xA5u`) fails this binary at run time,
 * and a signature change fails at compile time (extern decl via dtc.h).
 *
 * Refactor-path coverage (both paths from the scoping plan execute here):
 *   - macro-addressed table: `table` derives from DTC_PRIMARY_TABLE_BASE
 *     (dtc.h:44), DTC_PRIMARY_ENTRY_SIZE/MAX_SLOTS; the test asserts the
 *     macro values at compile time, so a macro revert breaks the build;
 *   - literal guards: dtc.c:1868-1869 reads 0xFFFF8920/0xFFFF8924 as bare
 *     literals (NOT -D-redirectable — a -D probe confirmed the header
 *     macro still expands to 0xFFFF8928 and the guard literal is
 *     hard-coded in the .c body);
 *   - dtc_read_code inline literal path (dtc.h:415-419): the loop's
 *     skip-empty check calls the real inline, which dereferences the same
 *     table addresses.
 *
 * Host execution boundary (deterministic, verified 2026-09-17):
 *   - No stubs, no mocks, no -D redirection: the whole TU links with
 *     `nm -u` clean (dtc.c has zero undefined externs), so NO stub .c
 *     files are needed — exactly like the h1 pilot (can.c).
 *   - MMIO is real: the SH-2 0xFFFF8xxx RAM page does not exist on the
 *     host (a bare deref segfaults, verified: SIGSEGV rc=139), so the
 *     test maps it with mmap(MAP_FIXED) at 0xFFFF8000 (one 4 KiB page
 *     covering guards 0xFFFF8920/24 + table 0xFFFF8928..0xFFFF8D6C).
 *     Every load/store the function performs then executes for real —
 *     nothing is stubbed or skipped, including the literal-guard
 *     sub-path. No production accessor refactor was needed for THIS
 *     function; the pilot still motivates it for the wider TU (bare
 *     0xFFFFxxxx derefs elsewhere in dtc.c remain un-runnable on host
 *     without the same page mapping).
 *
 * Proves:
 *   (a) blank guards fail: guard0 0xFFFF/0x0000 or guard1 0xFFFF/0x0000
 *       -> 0 (M2 guard semantics);
 *   (b) valid guards + all slots empty (code 0xFFFF) -> 1 (erased table
 *       carries no checksum);
 *   (c) valid guards + one entry with 15-byte sum == 0xA5 -> 1;
 *   (d) valid guards + one entry with sum != 0xA5 -> 0;
 *   (e) empty slots are skipped even with a garbage payload that would
 *       fail the sum (code 0xFFFF/0x0000, sum != 0xA5) -> 1.
 *
 * Build (see firmware/tests/Makefile link-check):
 *   gcc -std=c11 -Wall -Wextra -Werror -Wno-error=unused-function -O2 \
 *       -I../include link/link_m2_checksum.c ../c/dtc.c -o /tmp/fwtest/link_m2_checksum
 */
#include <stdint.h>
#include <stdio.h>
#include <sys/mman.h>

#include "dtc.h"

/* Extern declaration comes from the real dtc.h (linking the real dtc.c
 * TU): a signature change in firmware breaks this build. */
_Static_assert(DTC_PRIMARY_TABLE_BASE == 0xFFFF8928, "DTC_PRIMARY_TABLE_BASE revert");
_Static_assert(DTC_PRIMARY_ENTRY_SIZE == 0x34, "DTC_PRIMARY_ENTRY_SIZE revert");
_Static_assert(DTC_PRIMARY_MAX_SLOTS == 21, "DTC_PRIMARY_MAX_SLOTS revert");

/* The guard literals live in the .c body (not header macros), so pin the
 * addresses the test maps — a firmware move of the guard words must also
 * move this mapping, or (a)/(b) fail loudly. */
#define M2_PAGE_BASE 0xFFFF8000u
#define M2_PAGE_LEN  0x1000u
#define M2_GUARD0    0xFFFF8920u
#define M2_GUARD1    0xFFFF8924u

static int failures = 0;

#define CHECK(cond, ...) do { \
    if (!(cond)) { printf("FAIL: "); printf(__VA_ARGS__); printf("\n"); failures++; } \
} while (0)

static volatile uint8_t *m2_u8(uint32_t addr)
{
    return (volatile uint8_t *)(uintptr_t)addr;
}

static volatile uint16_t *m2_u16(uint32_t addr)
{
    return (volatile uint16_t *)(uintptr_t)addr;
}

static uint32_t m2_slot_addr(unsigned slot)
{
    return (uint32_t)DTC_PRIMARY_TABLE_BASE
        + (uint32_t)slot * (uint32_t)DTC_PRIMARY_ENTRY_SIZE;
}

/* Erase the whole mapped page (guards + table) to blank-flash 0xFF. */
static void m2_erase(void)
{
    for (uint32_t a = M2_PAGE_BASE; a < M2_PAGE_BASE + M2_PAGE_LEN; a++)
        *m2_u8(a) = 0xFFu;
}

/* Write slot `slot` with code `code` and force the 15-byte
 * (+0x00..+0x0E) sum to `want_sum` (mod 256): payload bytes +0x02..+0x0D
 * cleared, byte +0x0E carries the adjustment. */
static void m2_write_entry(unsigned slot, uint16_t code, uint8_t want_sum)
{
    uint32_t base = m2_slot_addr(slot);
    unsigned j;

    *m2_u16(base) = code;
    for (j = 2; j < 14; j++)
        *m2_u8(base + j) = 0x00u;
    /* want: code_lo + code_hi + adj == want_sum (mod 256). */
    *m2_u8(base + 14) = (uint8_t)((uint32_t)want_sum
        - (uint32_t)(code & 0xFFu) - (uint32_t)((code >> 8) & 0xFFu));
}

int main(void)
{
    void *p = mmap((void *)(uintptr_t)M2_PAGE_BASE, M2_PAGE_LEN,
                   PROT_READ | PROT_WRITE,
                   MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED, -1, 0);
    if (p == (void *)-1) {
        printf("FAIL: mmap(0xFFFF8000) failed\n");
        return 1;
    }

    /* (a) blank guards fail — erased (0xFFFF) and cleared (0x0000). */
    m2_erase(); /* both guards 0xFFFF */
    CHECK(dtc_region_checksum_validate_8928() == 0,
          "blank guards 0xFFFF -> %d want 0",
          dtc_region_checksum_validate_8928());
    m2_erase();
    *m2_u16(M2_GUARD0) = 0x0000u;
    *m2_u16(M2_GUARD1) = 0x1234u;
    CHECK(dtc_region_checksum_validate_8928() == 0,
          "guard0 0x0000 -> %d want 0",
          dtc_region_checksum_validate_8928());
    m2_erase();
    *m2_u16(M2_GUARD0) = 0x1234u;
    *m2_u16(M2_GUARD1) = 0xFFFFu;
    CHECK(dtc_region_checksum_validate_8928() == 0,
          "guard1 0xFFFF -> %d want 0",
          dtc_region_checksum_validate_8928());
    m2_erase();
    *m2_u16(M2_GUARD0) = 0x1234u;
    *m2_u16(M2_GUARD1) = 0x0000u;
    CHECK(dtc_region_checksum_validate_8928() == 0,
          "guard1 0x0000 -> %d want 0",
          dtc_region_checksum_validate_8928());

    /* (b) valid guards + fully erased table (all codes 0xFFFF) -> 1. */
    m2_erase();
    *m2_u16(M2_GUARD0) = 0x1234u;
    *m2_u16(M2_GUARD1) = 0x5678u;
    CHECK(dtc_region_checksum_validate_8928() == 1,
          "valid guards + empty table -> %d want 1",
          dtc_region_checksum_validate_8928());

    /* (c) one entry with sum == 0xA5 -> 1 (slots 0 and 20 = edges). */
    m2_write_entry(0, 0x0102u, 0xA5u);
    CHECK(dtc_region_checksum_validate_8928() == 1,
          "slot0 sum 0xA5 -> %d want 1",
          dtc_region_checksum_validate_8928());
    m2_write_entry(20, 0x0403u, 0xA5u);
    CHECK(dtc_region_checksum_validate_8928() == 1,
          "slots 0+20 sum 0xA5 -> %d want 1",
          dtc_region_checksum_validate_8928());

    /* (d) one entry with sum != 0xA5 -> 0; boundary 0xA4/0xA6. */
    m2_write_entry(7, 0x0201u, 0xA4u);
    CHECK(dtc_region_checksum_validate_8928() == 0,
          "slot7 sum 0xA4 -> %d want 0",
          dtc_region_checksum_validate_8928());
    m2_write_entry(7, 0x0201u, 0xA6u);
    CHECK(dtc_region_checksum_validate_8928() == 0,
          "slot7 sum 0xA6 -> %d want 0",
          dtc_region_checksum_validate_8928());
    m2_write_entry(7, 0x0201u, 0x00u);
    CHECK(dtc_region_checksum_validate_8928() == 0,
          "slot7 sum 0x00 -> %d want 0",
          dtc_region_checksum_validate_8928());

    /* (e) empty slots are skipped even with a failing payload sum. */
    m2_erase();
    *m2_u16(M2_GUARD0) = 0x1234u;
    *m2_u16(M2_GUARD1) = 0x5678u;
    m2_write_entry(0, 0x0102u, 0xA5u);   /* one good entry */
    m2_write_entry(5, 0xFFFFu, 0x00u);   /* erased slot, bad sum */
    m2_write_entry(9, 0x0000u, 0x00u);   /* cleared slot, bad sum */
    CHECK(dtc_region_checksum_validate_8928() == 1,
          "empty slots w/ bad payload skipped -> %d want 1",
          dtc_region_checksum_validate_8928());

    munmap(p, M2_PAGE_LEN);

    if (failures == 0) {
        printf("PASS link_m2_checksum (real dtc.c TU)\n");
    } else {
        printf("%d FAILURES link_m2_checksum\n", failures);
    }
    return failures != 0;
}

/*
 * link_main.c — Link pilot 15: compile-link-run against the REAL
 * firmware/c/main.c TU (cooperative RTOS task dispatcher / queue
 * scheduler — the ROM 0x6C8 main loop), not a model replica. Closes the
 * last zero-coverage core TU pair alongside link_boot: this TU had no
 * link rule, no model harness exercising the .c body, and no c/tests on
 * any side (the only prior contact was the gate source-grep for the C1
 * addr-width fix).
 *
 * Mechanism proof: links the real main.c with ZERO stubs — the undefined
 * symbol chain is closed entirely by in-repo TUs, verified at pilot time:
 *   nm -u main.o   = eeprom_read_validate + {serial_rx_handler_ch0,
 *                     serial_rx_handler_ch1, serial_rx_handler_ch2,
 *                     serial_data_write_handler}
 *   nm -u serial.o = {atu_timer_init, atu_capture_compare_init} (timer.c)
 *   nm -u eeprom.o = EMPTY, nm -u timer.o = EMPTY
 * So a firmware revert of the C1 addr-width fix (uint32_t queue address),
 * the M3 phantom-enqueue fix (copy temp_buf BEFORE advancing), the
 * negative-wrap in pending_count, the %100 read-index wrap, or the
 * watchdog feed constant fails this binary at run time; a signature
 * change fails at compile (extern decls via main.h — the SAME header
 * main.c includes); a rename of a serial_ or atu_ symbol fails at link.
 *
 * Host execution boundary (TWO 4 KiB pages, mmap MAP_FIXED):
 *   0xFFFFD000 — task queue 0xFFFFD4E0..0xFFFFD7FF (100 x 8B), uint16
 *                write/read indices 0xFFFFDFB4/0xFFFFDFB6, dispatcher
 *                flag 0xFFFFDFB8, scheduler busy flag 0xFFFFDFBA, EEPROM
 *                validation buffer 0xFFFFDFE4..0xFFFFDFEC (the whole
 *                eeprom_read_validate path is pure RAM);
 *   0xFFFFE000 — WDT_TCSR 0xFFFFEC10 (watchdogTimerRead feed store).
 * (D page shared with link_l10/m7/rtos/eeprom, E with link_m8/eeprom —
 * separate processes, MAP_FIXED cannot collide.)
 * No ROM/low address is dereferenced: objdump immediates of main.o are
 * only 0xFFFFD4E0/D4E8/D808 (queue), 0xFFFFDFB4/DFB6/DFB8/DFBA (control
 * bytes), 0xFFFFEC10 (WDT) plus data constants (0xA53C feed, 0x51EB851F
 * div magic) — 0x6C8/0xD8 and friends appear in comments only.
 *
 * Every zero-expect is primed NON-ZERO first (h4 F1 lesson); no
 * tautological/self-referential asserts. Kills (each demonstrated by a
 * single-edit mutant of the real firmware sources, IDENTICAL Makefile
 * CFLAGS — table in the pilot commit body):
 *   S1 task_queue_init: slots primed 0x00 + indices primed 0x1234/0x5678
 *      -> exactly 800 x 0xFF + both indices 0. Kills: dropped index
 *      reset, loop bound 100->99 (slot 99 stays primed), C1-style
 *      `uint16_t addr` narrowing (writes truncate below mmap_min_addr
 *      = 65536 -> SIGSEGV -> nonzero exit).
 *   S2 task_queue_pending_count: (5,3)->2, (3,5)->98, (7,7)->0,
 *      (0,99)->1. Kills: dropped `if (diff<0) diff += SIZE`
 *      (main.c:84) — the wrap vector is the killer.
 *   S3 task_queue_get_next: read idx 99 -> returns 99 AND wraps to 0,
 *      then returns 0 -> 1. Kills: missing `% TASK_QUEUE_SIZE`
 *      (main.c:105), return-value corruption (post-increment return).
 *   S4 task_scheduler_dispatch BUSY path (busy=1, marker 0x55 primed,
 *      payload primed, slot 7 primed NON-payload 0x77, w=7): slot 7
 *      receives the 8 payload bytes, w -> 8, marker -> 0xAA; a 2nd call
 *      (marker consumed) must NOT re-enqueue; then busy=0 with marker/
 *      payload/slot-42 sentinels primed -> state completely untouched.
 *      Kills: M3 phantom enqueue (copy dropped, advance kept), double
 *      consume/re-enqueue, ANY side effect in the intentionally-empty
 *      busy==0 branch (w2 gap pin).
 *   S5 watchdogTimerRead: TCSR primed 0x1234 -> exactly 0xA53C after.
 *      Kills: wrong feed constant, dropped store, narrowed store
 *      address -> SIGSEGV.
 *
 * Documented limits (h5 style — real, not faked asserts):
 *   - main_task_dispatcher (while(1) at main.c:248) is LINKED BUT NEVER
 *     ENTERED: it has no exit path on the host. Its dispatcher-flag
 *     clear (main.c:245), the serial dispatch arms (main.c:283/287/291/
 *     303), the in-loop watchdog service and the idle path are therefore
 *     not executed by this harness;
 *   - fatal_error_infinite_loop (while(1) at main.c:337): linked but
 *     never entered (hangs by design);
 *   - cpu_idle_sleep (static inline, main.c:202-205): never called by
 *     any TU (rom-check: the ROM dispatcher never sleeps) — not emitted,
 *     never entered;
 *   - task_read8/16 + task_write16 accessors (main.c:42-60): only call
 *     sites are inside main_task_dispatcher — never executed;
 *   - the WDT read-back `(void)WDT_TCSR` (main.c:217) EXECUTES inside
 *     S5 but is indistinguishable from its absence on the host (a read
 *     of static memory has no side effect) — unobservable; the feed
 *     store is what S5 asserts;
 *   - busy==0 branch (main.c:151-162): the ROM diag_transfer_210 call is
 *     a DOCUMENTED w2 gap (no C counterpart for ROM 0xACE callee), so the
 *     branch is intentionally empty. S4 pins it as a no-op; it does NOT
 *     prove ROM behavior there (unproven, NEEDS-ROM-CHECK per main.h).
 *
 * Build (see firmware/tests/Makefile link-check):
 *   gcc -std=c11 -Wall -Wextra -Werror -O2 -I../include \
 *       link/link_main.c ../c/main.c ../c/serial.c ../c/eeprom.c \
 *       ../c/timer.c -o /tmp/fwtest/link_main -lm
 * (all four TUs compile clean under -Werror — no relaxations, no stubs.)
 */
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>

#include "main.h"    /* real extern prototypes — same header main.c uses */
#include "eeprom.h"  /* eeprom_read_validate (called through the scheduler) */

/* ---- MMIO pins ------------------------------------------------------- */
#define PG_D     0xFFFFD000u
#define PG_E     0xFFFFE000u
#define PG_LEN   0x1000u

#define A_QUEUE   0xFFFFD4E0u  /* platform.h TASK_QUEUE_BASE */
#define A_BUSY    0xFFFFDFBAu  /* main.c task_scheduler_dispatch busy flag */
#define A_FLAG    0xFFFFDFB8u  /* main.c:245 dispatcher flag (never entered) */
#define A_WDT     0xFFFFEC10u  /* platform.h WDT_TCSR */

/* uint64 math: the F-page-style base+0x1000 overflows 32 bits. */
#define IN_PG(base, a) ((uint64_t)(a) >= (uint64_t)(base) && \
                        (uint64_t)(a) < (uint64_t)(base) + (uint64_t)PG_LEN)

/* Real firmware macro pins (a firmware move kills these at COMPILE time). */
_Static_assert(TASK_QUEUE_BASE == 0xFFFFD4E0u, "task queue moved");
_Static_assert(TASK_QUEUE_SIZE == 100, "queue length moved");
_Static_assert(TASK_QUEUE_ENTRY_SIZE == 8, "entry size moved");
_Static_assert(IN_PG(PG_D, TASK_QUEUE_BASE) &&
               IN_PG(PG_D, TASK_QUEUE_BASE +
                             (uint64_t)TASK_QUEUE_SIZE * TASK_QUEUE_ENTRY_SIZE - 1),
               "queue outside mapped D page");
_Static_assert((uintptr_t)&TASK_QUEUE_WRITE_IDX == 0xFFFFDFB4u,
               "write index moved");
_Static_assert((uintptr_t)&TASK_QUEUE_READ_IDX == 0xFFFFDFB6u,
               "read index moved");
_Static_assert(A_BUSY == 0xFFFFDFBAu && A_FLAG == 0xFFFFDFB8u,
               "control bytes moved");
_Static_assert((uintptr_t)&WDT_TCSR == A_WDT, "WDT_TCSR moved");
_Static_assert(IN_PG(PG_E, A_WDT), "WDT outside mapped E page");
_Static_assert(EEPROM_RAM_BUF_A == 0xFFFFDFE4u &&
               EEPROM_RAM_BUF_A_MARKER == 0xFFFFDFECu &&
               EEPROM_RAM_BUF_A_MARKER == EEPROM_RAM_BUF_A + 8,
               "EEPROM validation buffer/marker moved");
_Static_assert(IN_PG(PG_D, EEPROM_RAM_BUF_A) &&
               IN_PG(PG_D, EEPROM_RAM_BUF_A_MARKER),
               "EEPROM buffer outside mapped D page");
_Static_assert(EEPROM_VALID_MARKER == 0x55 && EEPROM_CONSUMED_MARKER == 0xAA,
               "EEPROM marker bytes moved");

static int failures = 0;

#define CHECK(cond, ...) do { \
    if (!(cond)) { printf("FAIL: "); printf(__VA_ARGS__); printf("\n"); failures++; } \
} while (0)

static volatile uint8_t *mm_u8(uint32_t addr)
{
    return (volatile uint8_t *)(uintptr_t)addr;
}

static int map_page(uintptr_t base)
{
    void *p = mmap((void *)base, PG_LEN, PROT_READ | PROT_WRITE,
                   MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED, -1, 0);
    if (p != (void *)base) {
        printf("FAIL: mmap 0x%lx\n", (unsigned long)base);
        return 0;
    }
    return 1;
}

/* ---- S1: task_queue_init -------------------------------------------- */
static void s1_queue_init(void)
{
    volatile uint8_t *q = mm_u8(A_QUEUE);
    int nz;

    /* Prime every slot 0x00 and BOTH indices NON-zero (F1): after init
     * every byte must be 0xFF and both indices exactly 0. */
    memset((void *)(uintptr_t)A_QUEUE, 0x00,
           (size_t)TASK_QUEUE_SIZE * TASK_QUEUE_ENTRY_SIZE);
    TASK_QUEUE_WRITE_IDX = 0x1234;
    TASK_QUEUE_READ_IDX  = 0x5678;

    task_queue_init();

    CHECK(TASK_QUEUE_WRITE_IDX == 0 && TASK_QUEUE_READ_IDX == 0,
          "S1 init indices not both 0 (w=%04X r=%04X)",
          (unsigned)TASK_QUEUE_WRITE_IDX, (unsigned)TASK_QUEUE_READ_IDX);
    nz = 0;
    for (int i = 0; i < TASK_QUEUE_SIZE * TASK_QUEUE_ENTRY_SIZE; i++) {
        if (q[i] != 0xFF) nz++;
    }
    CHECK(nz == 0, "S1 init fill: %d of 800 slots != 0xFF", nz);
    /* Slot-99 endpoint pins (C1: last byte lives at 0xFFFFD7FF — the
     * loop-bound-99 mutant leaves these primed 0x00). */
    CHECK(q[0] == 0xFF && q[799] == 0xFF,
          "S1 endpoints q[0]=%02X q[799]=%02X", q[0], q[799]);
}

/* ---- S2: task_queue_pending_count ----------------------------------- */
static void s2_pending_count(void)
{
    TASK_QUEUE_WRITE_IDX = 5; TASK_QUEUE_READ_IDX = 3;
    CHECK(task_queue_pending_count() == 2,
          "S2 pending (5,3)=%d want 2", task_queue_pending_count());
    TASK_QUEUE_WRITE_IDX = 3; TASK_QUEUE_READ_IDX = 5;
    CHECK(task_queue_pending_count() == 98,
          "S2 pending wrap (3,5)=%d want 98", task_queue_pending_count());
    TASK_QUEUE_WRITE_IDX = 7; TASK_QUEUE_READ_IDX = 7;
    CHECK(task_queue_pending_count() == 0,
          "S2 pending empty (7,7)=%d want 0", task_queue_pending_count());
    TASK_QUEUE_WRITE_IDX = 0; TASK_QUEUE_READ_IDX = 99;
    CHECK(task_queue_pending_count() == 1,
          "S2 pending (0,99)=%d want 1", task_queue_pending_count());
}

/* ---- S3: task_queue_get_next ---------------------------------------- */
static void s3_get_next(void)
{
    uint16_t r;

    /* read idx 99: return the consumed index 99 AND wrap to 0. */
    TASK_QUEUE_READ_IDX = 99;
    r = task_queue_get_next();
    CHECK(r == 99, "S3 get_next@99 ret=%u want 99", (unsigned)r);
    CHECK(TASK_QUEUE_READ_IDX == 0,
          "S3 wrap after 99: idx=%u want 0", (unsigned)TASK_QUEUE_READ_IDX);
    r = task_queue_get_next();
    CHECK(r == 0, "S3 get_next@0 ret=%u want 0", (unsigned)r);
    CHECK(TASK_QUEUE_READ_IDX == 1,
          "S3 idx after 0: %u want 1", (unsigned)TASK_QUEUE_READ_IDX);
}

/* ---- S4: task_scheduler_dispatch (busy + non-busy paths) ------------- */
static void s4_scheduler_dispatch(void)
{
    volatile uint8_t *busy = mm_u8(A_BUSY);
    volatile uint8_t *eb   = mm_u8(EEPROM_RAM_BUF_A);
    volatile uint8_t *q    = mm_u8(A_QUEUE);
    volatile uint8_t *slot7 = mm_u8(A_QUEUE + 7u * TASK_QUEUE_ENTRY_SIZE);
    int nz;

    /* --- busy path: marker valid, payload primed NON-payload, w=7,
     * slot 7 primed 0x77 (nonzero, != payload) --- */
    *busy = 1;
    for (int i = 0; i < 8; i++) eb[i] = (uint8_t)(0xA0 + i);
    eb[8] = EEPROM_VALID_MARKER;             /* 0x55: validate succeeds */
    for (int i = 0; i < 8; i++) slot7[i] = 0x77;
    TASK_QUEUE_WRITE_IDX = 7;

    task_scheduler_dispatch();

    nz = 0;
    for (int i = 0; i < 8; i++) if (slot7[i] != (uint8_t)(0xA0 + i)) nz++;
    CHECK(nz == 0, "S4 busy path: slot7 payload not copied (%d bad bytes)", nz);
    CHECK(TASK_QUEUE_WRITE_IDX == 8,
          "S4 busy path: write_idx=%u want 8",
          (unsigned)TASK_QUEUE_WRITE_IDX);
    CHECK(eb[8] == EEPROM_CONSUMED_MARKER,
          "S4 busy path: marker=%02X want 0xAA (consume)", eb[8]);

    /* --- marker consumed: 2nd call must NOT re-enqueue --- */
    task_scheduler_dispatch();
    CHECK(TASK_QUEUE_WRITE_IDX == 8,
          "S4 phantom re-enqueue on consumed marker: w=%u want 8",
          (unsigned)TASK_QUEUE_WRITE_IDX);
    CHECK(eb[8] == EEPROM_CONSUMED_MARKER,
          "S4 re-consumed marker=%02X want 0xAA", eb[8]);

    /* --- busy==0: branch is intentionally EMPTY (documented w2 gap).
     * Prime marker 0x55 + a different payload + slot-42 sentinels, so ANY
     * side effect in the empty branch (enqueue, validate/consume, copy)
     * is observable. --- */
    *busy = 0;
    for (int i = 0; i < 8; i++) eb[i] = (uint8_t)(0xB1 + i);
    eb[8] = EEPROM_VALID_MARKER;
    for (int i = 0; i < 8; i++) q[42u * TASK_QUEUE_ENTRY_SIZE + i] = 0x5A;
    TASK_QUEUE_WRITE_IDX = 42;

    task_scheduler_dispatch();

    CHECK(TASK_QUEUE_WRITE_IDX == 42,
          "S4 busy0: write_idx mutated w=%u want 42",
          (unsigned)TASK_QUEUE_WRITE_IDX);
    nz = 0;
    for (int i = 0; i < 8; i++) {
        if (q[42u * TASK_QUEUE_ENTRY_SIZE + i] != 0x5A) nz++;
    }
    CHECK(nz == 0, "S4 busy0: slot42 sentinel touched (%d bytes)", nz);
    CHECK(eb[8] == EEPROM_VALID_MARKER,
          "S4 busy0: marker consumed %02X want 0x55 (phantom validate)",
          eb[8]);
}

/* ---- S5: watchdogTimerRead ------------------------------------------ */
static void s5_watchdog_feed(void)
{
    /* Prime NON-zero 0x1234 -> exactly the ROM feed 0xA53C after. */
    WDT_TCSR = 0x1234;
    watchdogTimerRead();
    CHECK(WDT_TCSR == 0xA53C,
          "S5 WDT feed: TCSR=%04X want A53C", (unsigned)WDT_TCSR);
}

int main(void)
{
    if (!map_page(PG_D) || !map_page(PG_E)) {
        return 1;   /* mmap failure already printed as FAIL */
    }

    s1_queue_init();
    s2_pending_count();
    s3_get_next();
    s4_scheduler_dispatch();
    s5_watchdog_feed();

    /* Note: main_task_dispatcher / fatal_error_infinite_loop are linked
     * but NEVER entered (documented in the header comment above). */

    if (failures) {
        printf("link_main: %d FAIL(s)\n", failures);
    } else {
        printf("link_main: all scenarios pass (5/5)\n");
    }
    return failures != 0;
}

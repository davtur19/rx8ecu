/*
 * link_rtos_queue_dispatch.c — Link pilot 12: compile-link-run against the
 * REAL firmware/c/rtos.c TU (the .c body itself — pilot n2 only ever linked
 * the rtos.h header inlines, so every function defined in rtos.c was
 * unlinked until now), exercising init / queue enqueue-dequeue /
 * dispatch-to-handler / scheduler / context save-restore against mapped
 * memory — not a model replica.
 *
 * Mechanism proof: links the real rtos.c, so a firmware revert (dropping the
 * enqueue byte stores, breaking a dispatch call, removing the handler==0
 * early return, changing the 0xFF init fill, breaking the priority restore
 * or the scheduler re-entrancy latch) fails this binary at run time; a
 * signature change in rtos.h/rtos.c fails at compile time (-Werror, real
 * prototypes); missing rtos.c definitions fail at link.
 *
 * Target / TU choice (confirmed from source + objdump, not assumed):
 *   - `nm -u rtos.o` = EMPTY (0 undefined externs) — zero stubs needed;
 *     rtos.c compiles clean under -Wall -Wextra -Werror.
 *   - No ROM read: objdump immediates of rtos.o are only 0xFFFFD4E0 (queue
 *     base, formed as 0xFFFFDFB4-0xAD4), 0xFFFFD800 (queue end),
 *     0xFFFFDFB4/0xFFFFDFB6 (uint16 indexes) plus 0x00FFFFFF masks. The
 *     dispatch table 0x6873C is comment-only (never dereferenced).
 *   - One MMIO page: EVERY RAM address rtos.c touches lives in
 *     0xFFFFD000..0xFFFFDFFF — queue 0xFFFFD4E0..0xFFFFD7FF (100 x 8) and
 *     the write/read indexes 0xFFFFDFB4/0xFFFFDFB6 — the same D page
 *     already proven mappable MAP_FIXED by pilots m7/c2 and l10.
 *   - rtos_dispatch casts the 24-bit RTOS_DISP_HANDLER_MASK field to a
 *     function pointer: harness handlers must live below 0x01000000, so
 *     this binary links -no-pie (non-PIE .text at 0x400000). The runtime
 *     precondition CHECK below fails loudly if that ever stops holding.
 *   - Context save/restore take uint32_t *sp (SH-2 word addresses); the
 *     harness fake stack therefore lives INSIDE the mapped D page
 *     (top 0xFFFFD080, 0x44 frame grows down to 0xFFFFD03C) — a host stack
 *     pointer would be truncated by the 32-bit parameter.
 *
 * Host execution boundary (one MMIO page, mmap MAP_FIXED):
 *   - Map 0xFFFFD000 (4 KiB). Prime BEFORE every zero-expect (F1 lesson):
 *     indexes primed 0x1234/0x5678 (killable vs init's 0), queue bytes
 *     primed 0x00 (killable vs init's 0xFF fill), fake-stack frame primed
 *     0xA5 (killable vs context-save zeros; 0xA5 must SURVIVE in the FP
 *     slot for non-TIMER saves — proves the type guard).
 *
 * Contract pins (_Static_assert): RTOS_QUEUE_BASE/ENTRY_SIZE/MAX_SLOTS +
 * exact queue end 0xFFFFD800, WRITE/READ_ADDR, platform.h TASK_QUEUE_*
 * aliasing, handler/type/priority masks+shifts, priority and type enums,
 * context frame sizes 0x34/0x44, dispatch table base 0x6873C, and full
 * page membership of the queue region and both index addresses.
 *
 * Proves (every assert killable):
 *   (a) rtos_init: indexes primed nonzero -> 0, queue primed 0x00 -> all
 *       800 bytes 0xFF, empty/full/count/priority contracts;
 *   (b) dequeue on empty -> -1 with output params untouched (primed);
 *   (c) enqueue/dequeue roundtrip: exact dispatch+arg, big-endian raw slot
 *       bytes, index advance (kills dropped enqueue stores);
 *   (d) 3-item FIFO order + count decrements;
 *   (e) index-arithmetic contracts across wrap (count=15 at r=90/w=5,
 *       full at r=98/w=97) — the rtos_queue_count/ is_full wrap branches;
 *   (f) enqueue/dequeue across the 99->0 slot wrap (fresh 0xFF slots);
 *   (g) fill-to-full: 99 pending, is_full, 100th -> -1 with write index
 *       frozen, then full FIFO drain;
 *   (h) rtos_dispatch per type: BASIC arg=handler (ROM ignores arg),
 *       SUBFUNC/BUFFER arg=(handler, arg), TIMER arg=argument; types 3/7
 *       must NOT call (primed nonzero call count);
 *   (i) handler==0 early return (call count primed nonzero; a guard
 *       removal calls through NULL -> SIGSEGV, also red);
 *   (j) scheduler: empty no-op with latch released, single-task dispatch
 *       with exact arg, current_priority restored to S3 after an S0
 *       dispatch, FIFO across mixed priorities, re-entrancy latch (nested
 *       rtos_scheduler from inside a handler must NOT re-enter: log must
 *       be "AaB", a removed latch yields "ABa"), null-handler task
 *       survives, rtos_yield dispatches pending work and restores
 *       priority;
 *   (k) context save/restore: sp -= 0x44 / sp restored exactly, core 52
 *       bytes zeroed (primed A5), FP 16 bytes untouched for BASIC (primed
 *       A5 survives) but zeroed for TIMER.
 *
 * NOT covered (documented residual): the scheduler re-enqueue/skip_count
 * branch (priority > current_priority at loop level) is unreachable via
 * the public API on the host: current_priority only dips below S3 DURING a
 * dispatch, and the scheduler_running latch blocks re-entry from handlers,
 * so loop-level priority is always S3 and every valid task (0..3) dispatches.
 *
 * Build (see firmware/tests/Makefile link-check):
 *   gcc -std=c11 -Wall -Wextra -Werror -O2 -no-pie -I../include \
 *       link/link_rtos_queue_dispatch.c ../c/rtos.c \
 *       -o /tmp/fwtest/link_rtos_queue_dispatch
 */
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>

#include "platform.h"
#include "rtos.h"

/* Real rtos.h/rtos.c prototypes come from the linked TU: a signature
 * change breaks this build. Pin the address-map + dispatch contracts. */
_Static_assert(RTOS_QUEUE_BASE == 0xFFFFD4E0u, "RTOS_QUEUE_BASE revert");
_Static_assert(RTOS_QUEUE_ENTRY_SIZE == 8, "RTOS_QUEUE_ENTRY_SIZE revert");
_Static_assert(RTOS_QUEUE_MAX_SLOTS == 100, "RTOS_QUEUE_MAX_SLOTS revert");
_Static_assert(RTOS_QUEUE_WRITE_ADDR == 0xFFFFDFB4u, "WRITE_ADDR revert");
_Static_assert(RTOS_QUEUE_READ_ADDR == 0xFFFFDFB6u, "READ_ADDR revert");
_Static_assert(RTOS_QUEUE_BASE + RTOS_QUEUE_MAX_SLOTS * RTOS_QUEUE_ENTRY_SIZE
               == 0xFFFFD800u, "queue end (objdump 0xFFFFD800) revert");
_Static_assert(TASK_QUEUE_BASE == RTOS_QUEUE_BASE,
               "platform.h TASK_QUEUE_BASE diverges from RTOS_QUEUE_BASE");
_Static_assert(TASK_QUEUE_SIZE == RTOS_QUEUE_MAX_SLOTS,
               "platform.h TASK_QUEUE_SIZE diverges");
_Static_assert(TASK_QUEUE_ENTRY_SIZE == RTOS_QUEUE_ENTRY_SIZE,
               "platform.h TASK_QUEUE_ENTRY_SIZE diverges");
_Static_assert(RTOS_DISP_HANDLER_MASK == 0x00FFFFFFu, "HANDLER_MASK revert");
_Static_assert(RTOS_DISP_TYPE_SHIFT == 24, "TYPE_SHIFT revert");
_Static_assert(RTOS_DISP_TYPE_MASK == 0x07, "TYPE_MASK revert");
_Static_assert(RTOS_DISP_PRIO_SHIFT == 28, "PRIO_SHIFT revert");
_Static_assert(RTOS_DISP_PRIO_MASK == 0x03, "PRIO_MASK revert");
_Static_assert(RTOS_PRIORITY_S0 == 0 && RTOS_PRIORITY_S1 == 1
               && RTOS_PRIORITY_S2 == 2 && RTOS_PRIORITY_S3 == 3,
               "priority enum revert");
_Static_assert(RTOS_TYPE_BASIC == 0 && RTOS_TYPE_SUBFUNC == 1
               && RTOS_TYPE_BUFFER == 2 && RTOS_TYPE_RESERVED == 3
               && RTOS_TYPE_TIMER == 4, "type enum revert");
_Static_assert(RTOS_CTX_FRAME_SIZE == 0x34, "RTOS_CTX_FRAME_SIZE revert");
_Static_assert(RTOS_CTX_FRAME_SIZE_FP == 0x44, "RTOS_CTX_FRAME_SIZE_FP revert");
_Static_assert(RTOS_DISPATCH_TABLE_BASE == 0x6873C,
               "dispatch table base revert (comment-only, never read)");

/* Host execution boundary: one 4 KiB page. */
#define RT12_PAGE_BASE   0xFFFFD000u
#define RT12_PAGE_LEN    0x1000u
/* Fake SH-2 stack top inside the mapped page (uint32_t *sp truncates a
 * real host stack pointer). Frame [0xFFFFD03C, 0xFFFFD080) grows down. */
#define RT12_FAKE_SP     0xFFFFD080u
/* Function pointers must survive the 24-bit handler mask (-no-pie). */
#define RT12_HANDLER_MAX 0x00FFFFFFu

#define RT12_IN_PAGE(a, n) \
    ((a) >= RT12_PAGE_BASE && (a) - RT12_PAGE_BASE + (n) <= RT12_PAGE_LEN)

_Static_assert(RT12_IN_PAGE(RTOS_QUEUE_BASE,
                            RTOS_QUEUE_MAX_SLOTS * RTOS_QUEUE_ENTRY_SIZE),
               "queue region outside mapped D page");
_Static_assert(RT12_IN_PAGE(RTOS_QUEUE_WRITE_ADDR, 2u),
               "write index outside mapped D page");
_Static_assert(RT12_IN_PAGE(RTOS_QUEUE_READ_ADDR, 2u),
               "read index outside mapped D page");
_Static_assert(RT12_IN_PAGE(RT12_FAKE_SP - RTOS_CTX_FRAME_SIZE_FP,
                            RTOS_CTX_FRAME_SIZE_FP),
               "fake-stack context frame outside mapped D page");

/* Distinct primes so every zero-expect is killable (F1 lesson). */
#define RT12_IDX_PRIME_W 0x1234u   /* != 0: init must clear it */
#define RT12_IDX_PRIME_R 0x5678u
#define RT12_BYTE_PRIME  0x00u     /* init must fill 0xFF over it */
#define RT12_FRAME_PRIME 0xA5u     /* context save must zero over it */
#define RT12_CALL_PRIME  7u        /* no-call expects must stay primed */

static int failures = 0;

#define CHECK(cond, ...) do { \
    if (!(cond)) { printf("FAIL: "); printf(__VA_ARGS__); printf("\n"); failures++; } \
} while (0)

static volatile uint8_t *rt12_u8(uint32_t addr)
{
    return (volatile uint8_t *)(uintptr_t)addr;
}

/* ---- harness-local handlers (valid function pointers, never 0) ---- */
static unsigned h_calls = 0;
static uint32_t h_a1 = 0;
static uint32_t h_a2 = 0;

static void h_basic(uint32_t a)
{
    h_calls++;
    h_a1 = a;
    h_a2 = 0xB1B1B1B1u;
}

static void h_sub(uint32_t a, uint32_t b)
{
    h_calls++;
    h_a1 = a;
    h_a2 = b;
}

static void h_buffer(uint32_t a, uint32_t b)
{
    h_calls++;
    h_a1 = a;
    h_a2 = b;
}

static void h_timer(uint32_t id)
{
    h_calls++;
    h_a1 = id;
    h_a2 = 0x71717171u;
}

/* Order recorder for the mixed-priority FIFO check. */
static uint32_t seen[8];
static int seen_n = 0;

static void h_order(uint32_t a, uint32_t b)
{
    (void)a;
    if (seen_n < (int)(sizeof seen / sizeof seen[0])) {
        seen[seen_n] = b;
    }
    seen_n++;
}

/* Re-entrancy latch probe: A logs entry, calls the scheduler (must be a
 * no-op while the outer scheduler holds the latch), logs exit. B logs
 * entry. Latch intact -> "AaB"; latch removed -> nested dispatch of B
 * inside A -> "ABa". */
static char seq[16];
static int seq_n = 0;

static void rt12_log(char c)
{
    if (seq_n < (int)(sizeof seq) - 1) {
        seq[seq_n++] = c;
        seq[seq_n] = '\0';
    }
}

static void h_latch_a(uint32_t x)
{
    (void)x;
    rt12_log('A');
    rtos_scheduler(); /* outer scheduler holds scheduler_running */
    rt12_log('a');
}

static void h_latch_b(uint32_t x)
{
    (void)x;
    rt12_log('B');
}

/* Aggregate scan: any byte of the 800-byte queue differing from expect. */
static int rt12_count_bytes(uint32_t base, unsigned len, uint8_t expect)
{
    int bad = 0;
    for (unsigned i = 0; i < len; i++) {
        if (*rt12_u8(base + i) != expect) {
            bad++;
        }
    }
    return bad;
}

static void rt12_prime_queue(uint8_t value)
{
    for (unsigned i = 0; i < RTOS_QUEUE_MAX_SLOTS * RTOS_QUEUE_ENTRY_SIZE; i++) {
        *rt12_u8(RTOS_QUEUE_BASE + i) = value;
    }
}

/* Raw big-endian slot contents vs the values enqueue must have stored. */
static void rt12_check_slot(unsigned slot, uint32_t dispatch, uint32_t arg,
                            const char *tag)
{
    volatile uint8_t *e = rt12_u8(RTOS_QUEUE_BASE
                                  + (uint32_t)slot * RTOS_QUEUE_ENTRY_SIZE);
    uint32_t gd = ((uint32_t)e[0] << 24) | ((uint32_t)e[1] << 16)
                | ((uint32_t)e[2] << 8)  | (uint32_t)e[3];
    uint32_t ga = ((uint32_t)e[4] << 24) | ((uint32_t)e[5] << 16)
                | ((uint32_t)e[6] << 8)  | (uint32_t)e[7];
    CHECK(gd == dispatch,
          "%s slot%u raw dispatch=%08X want %08X (enqueue store dropped/corrupted)",
          tag, slot, gd, dispatch);
    CHECK(ga == arg,
          "%s slot%u raw arg=%08X want %08X (enqueue store dropped/corrupted)",
          tag, slot, ga, arg);
}

int main(void)
{
    void *page = mmap((void *)(uintptr_t)RT12_PAGE_BASE, RT12_PAGE_LEN,
                      PROT_READ | PROT_WRITE,
                      MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED, -1, 0);
    if (page == (void *)-1) {
        printf("FAIL: mmap(0xFFFFD000) failed\n");
        return 1;
    }

    /* Precondition: handler addresses must fit the 24-bit mask so the
     * cast inside rtos_dispatch reaches the real harness functions. If
     * this fires, the -no-pie link contract is broken — stop before
     * dispatching through truncated addresses. */
    {
        uint32_t hb = (uint32_t)(uintptr_t)&h_basic;
        uint32_t hs = (uint32_t)(uintptr_t)&h_sub;
        uint32_t hu = (uint32_t)(uintptr_t)&h_buffer;
        uint32_t ht = (uint32_t)(uintptr_t)&h_timer;
        uint32_t ho = (uint32_t)(uintptr_t)&h_order;
        uint32_t h1 = (uint32_t)(uintptr_t)&h_latch_a;
        uint32_t h2 = (uint32_t)(uintptr_t)&h_latch_b;
        if (hb > RT12_HANDLER_MAX || hs > RT12_HANDLER_MAX
            || hu > RT12_HANDLER_MAX || ht > RT12_HANDLER_MAX
            || ho > RT12_HANDLER_MAX || h1 > RT12_HANDLER_MAX
            || h2 > RT12_HANDLER_MAX) {
            printf("FAIL: handler %08X exceeds 24-bit RTOS_DISP_HANDLER_MASK "
                   "(link without -no-pie?)\n", hb);
            munmap(page, RT12_PAGE_LEN);
            return 1;
        }
    }

    /* ---- (a) rtos_init: prime, then require the exact post-init state ---- */
    rtos_set_write_index((uint16_t)RT12_IDX_PRIME_W);
    rtos_set_read_index((uint16_t)RT12_IDX_PRIME_R);
    CHECK(rtos_get_write_index() == RT12_IDX_PRIME_W
          && rtos_get_read_index() == RT12_IDX_PRIME_R,
          "index prime not in effect before init (w=%04X r=%04X)",
          rtos_get_write_index(), rtos_get_read_index());
    rt12_prime_queue(RT12_BYTE_PRIME);

    rtos_init();

    CHECK(rtos_get_write_index() == 0,
          "init write index=%04X want 0000 (primed %04X)",
          rtos_get_write_index(), RT12_IDX_PRIME_W);
    CHECK(rtos_get_read_index() == 0,
          "init read index=%04X want 0000 (primed %04X)",
          rtos_get_read_index(), RT12_IDX_PRIME_R);
    {
        int bad = rt12_count_bytes(RTOS_QUEUE_BASE,
                                   RTOS_QUEUE_MAX_SLOTS * RTOS_QUEUE_ENTRY_SIZE,
                                   0xFFu);
        CHECK(bad == 0,
              "init fill: %d of 800 bytes != 0xFF (primed 0x00 — fill dropped?)",
              bad);
    }
    CHECK(rtos_queue_is_empty() == 1, "after init queue not empty");
    CHECK(rtos_queue_is_full() == 0, "after init queue full");
    CHECK(rtos_queue_count() == 0, "after init count=%d want 0",
          rtos_queue_count());
    CHECK(rtos_get_current_priority() == RTOS_PRIORITY_S3,
          "after init priority=%u want S3(3)", rtos_get_current_priority());

    /* ---- (b) dequeue on empty: -1, outputs untouched (primed) ---- */
    {
        uint32_t od = 0x11111111u;
        uint32_t oa = 0x22222222u;
        int rc = rtos_task_dequeue(&od, &oa);
        CHECK(rc == -1, "dequeue-empty rc=%d want -1", rc);
        CHECK(od == 0x11111111u && oa == 0x22222222u,
              "dequeue-empty wrote outputs: %08X/%08X", od, oa);
    }

    /* ---- (c) single enqueue/dequeue roundtrip + raw BE bytes ---- */
    {
        uint32_t d = rtos_build_dispatch((uint32_t)(uintptr_t)&h_sub,
                                         RTOS_TYPE_SUBFUNC, RTOS_PRIORITY_S1);
        uint32_t arg = 0xDEADBEEFu;
        uint32_t od = 0;
        uint32_t oa = 0;
        int rc = rtos_task_enqueue(d, arg);
        CHECK(rc == 0, "enqueue rc=%d want 0", rc);
        CHECK(rtos_get_write_index() == 1, "write index=%u want 1",
              rtos_get_write_index());
        CHECK(rtos_queue_count() == 1, "count=%d want 1", rtos_queue_count());
        rt12_check_slot(0, d, arg, "roundtrip");
        rc = rtos_task_dequeue(&od, &oa);
        CHECK(rc == 0, "dequeue rc=%d want 0", rc);
        CHECK(od == d, "dequeue dispatch=%08X want %08X", od, d);
        CHECK(oa == arg, "dequeue arg=%08X want %08X", oa, arg);
        CHECK(rtos_get_read_index() == 1, "read index=%u want 1",
              rtos_get_read_index());
        CHECK(rtos_queue_is_empty() == 1, "queue not empty after drain");
        CHECK(rtos_queue_count() == 0, "count=%d want 0 after drain",
              rtos_queue_count());
        od = 0;
        oa = 0;
        CHECK(rtos_task_dequeue(&od, &oa) == -1,
              "second dequeue must be -1 (empty)");
    }

    /* ---- (d) 3-item FIFO + count decrements ---- */
    {
        uint32_t d = rtos_build_dispatch((uint32_t)(uintptr_t)&h_order,
                                         RTOS_TYPE_SUBFUNC, RTOS_PRIORITY_S2);
        CHECK(rtos_task_enqueue(d, 0x1111u) == 0, "fifo enqueue 1");
        CHECK(rtos_task_enqueue(d, 0x2222u) == 0, "fifo enqueue 2");
        CHECK(rtos_task_enqueue(d, 0x3333u) == 0, "fifo enqueue 3");
        CHECK(rtos_queue_count() == 3, "count=%d want 3", rtos_queue_count());
        {
            static const uint32_t want[3] = { 0x1111u, 0x2222u, 0x3333u };
            for (int i = 0; i < 3; i++) {
                uint32_t od = 0;
                uint32_t oa = 0;
                CHECK(rtos_task_dequeue(&od, &oa) == 0, "fifo dequeue %d", i);
                CHECK(od == d && oa == want[i],
                      "fifo[%d] got %08X want %08X (order corrupted)",
                      i, oa, want[i]);
                CHECK(rtos_queue_count() == 3 - i - 1,
                      "count=%d want %d", rtos_queue_count(), 3 - i - 1);
            }
        }
    }

    /* ---- (e) index-arithmetic wrap contracts (count / is_full) ---- */
    rtos_set_read_index(90);
    rtos_set_write_index(5); /* w < r: wrap branch 100-90+5 */
    CHECK(rtos_queue_count() == 15, "wrap count=%d want 15 (r=90 w=5)",
          rtos_queue_count());
    CHECK(rtos_queue_is_empty() == 0, "w=5 r=90 reported empty");
    CHECK(rtos_queue_is_full() == 0, "w=5 r=90 reported full");
    rtos_set_read_index(98);
    rtos_set_write_index(97); /* (97+1)%100 == 98 -> full across wrap */
    CHECK(rtos_queue_is_full() == 1, "w=97 r=98 must be full");
    CHECK(rtos_queue_count() == 99, "wrap-full count=%d want 99",
          rtos_queue_count());
    rtos_set_read_index(7);
    rtos_set_write_index(7);
    CHECK(rtos_queue_is_empty() == 1, "w=r=7 must be empty");
    CHECK(rtos_queue_count() == 0, "count at w=r want 0");

    /* Reset to the clean init state, then park both indexes at the
     * 99->0 wrap point (slots still freshly 0xFF-filled). */
    rtos_init();
    rtos_set_write_index(99);
    rtos_set_read_index(99);

    /* ---- (f) enqueue/dequeue across the 99->0 slot wrap ---- */
    {
        uint32_t d = rtos_build_dispatch((uint32_t)(uintptr_t)&h_buffer,
                                         RTOS_TYPE_BUFFER, RTOS_PRIORITY_S2);
        uint32_t a0 = 0xCAFEBABEu;
        uint32_t a1 = 0x0BADF00Du;
        CHECK(rtos_task_enqueue(d, a0) == 0, "wrap enqueue slot99");
        CHECK(rtos_task_enqueue(d, a1) == 0, "wrap enqueue slot0");
        /* 99 -> 0 -> 1 (mod 100): two enqueues from index 99 land on 1. */
        CHECK(rtos_get_write_index() == 1, "write index after wrap=%u want 1",
              rtos_get_write_index());
        rt12_check_slot(99, d, a0, "wrap");
        rt12_check_slot(0, d, a1, "wrap");
        {
            uint32_t od = 0;
            uint32_t oa = 0;
            CHECK(rtos_task_dequeue(&od, &oa) == 0 && od == d && oa == a0,
                  "wrap dequeue[0] got %08X want %08X", oa, a0);
            CHECK(rtos_task_dequeue(&od, &oa) == 0 && od == d && oa == a1,
                  "wrap dequeue[1] got %08X want %08X", oa, a1);
        }
        CHECK(rtos_get_read_index() == 1, "read index after wrap=%u want 1",
              rtos_get_read_index());
        CHECK(rtos_queue_is_empty() == 1, "queue not empty after wrap drain");
    }

    /* ---- (g) fill to full, reject 100th, FIFO drain ---- */
    {
        uint32_t d = rtos_build_dispatch((uint32_t)(uintptr_t)&h_order,
                                         RTOS_TYPE_SUBFUNC, RTOS_PRIORITY_S1);
        int ok = 0;
        for (int i = 0; i < 99; i++) {
            if (rtos_task_enqueue(d, 0x00A00000u + (uint32_t)i) == 0) {
                ok++;
            }
        }
        CHECK(ok == 99, "fill enqueued %d want 99", ok);
        CHECK(rtos_queue_is_full() == 1, "queue not full after 99 (r=1 w=0)");
        CHECK(rtos_queue_count() == 99, "full count=%d want 99",
              rtos_queue_count());
        {
            uint16_t w = rtos_get_write_index();
            CHECK(rtos_task_enqueue(d, 0xFFFFFFFFu) == -1,
                  "100th enqueue must be -1");
            CHECK(rtos_get_write_index() == w,
                  "write index moved on rejected enqueue: %u -> %u",
                  w, rtos_get_write_index());
        }
        {
            int order_bad = 0;
            for (int i = 0; i < 99; i++) {
                uint32_t od = 0;
                uint32_t oa = 0;
                if (rtos_task_dequeue(&od, &oa) != 0
                    || od != d || oa != 0x00A00000u + (uint32_t)i) {
                    order_bad++;
                }
            }
            CHECK(order_bad == 0, "fill drain: %d of 99 FIFO mismatches",
                  order_bad);
        }
        CHECK(rtos_queue_is_empty() == 1, "queue not empty after 99 drain");
        CHECK(rtos_queue_count() == 0, "count=%d want 0 after drain",
              rtos_queue_count());
    }

    /* ---- (h) rtos_dispatch per type (direct, harness-local handlers) ---- */
    h_calls = 0;
    h_a1 = 0;
    h_a2 = 0;
    {
        uint32_t hb = (uint32_t)(uintptr_t)&h_basic;
        uint32_t hs = (uint32_t)(uintptr_t)&h_sub;
        uint32_t hu = (uint32_t)(uintptr_t)&h_buffer;
        uint32_t ht = (uint32_t)(uintptr_t)&h_timer;

        rtos_dispatch(rtos_build_dispatch(hb, RTOS_TYPE_BASIC,
                                          RTOS_PRIORITY_S2), 0x1111u);
        CHECK(h_calls == 1, "BASIC dispatch calls=%u want 1 (call dropped?)",
              h_calls);
        CHECK(h_a1 == hb,
              "BASIC arg=%08X want handler %08X (ROM passes handler as r4)",
              h_a1, hb);

        rtos_dispatch(rtos_build_dispatch(hs, RTOS_TYPE_SUBFUNC,
                                          RTOS_PRIORITY_S1), 0xABCDu);
        CHECK(h_calls == 2, "SUBFUNC dispatch calls=%u want 2", h_calls);
        CHECK(h_a1 == hs && h_a2 == 0xABCDu,
              "SUBFUNC args=(%08X,%08X) want (%08X,ABCD)",
              h_a1, h_a2, hs);

        rtos_dispatch(rtos_build_dispatch(hu, RTOS_TYPE_BUFFER,
                                          RTOS_PRIORITY_S1), 0x5A5Au);
        CHECK(h_calls == 3, "BUFFER dispatch calls=%u want 3", h_calls);
        CHECK(h_a1 == hu && h_a2 == 0x5A5Au,
              "BUFFER args=(%08X,%08X) want (%08X,5A5A)",
              h_a1, h_a2, hu);

        rtos_dispatch(rtos_build_dispatch(ht, RTOS_TYPE_TIMER,
                                          RTOS_PRIORITY_S0), 0x7777u);
        CHECK(h_calls == 4, "TIMER dispatch calls=%u want 4", h_calls);
        CHECK(h_a1 == 0x7777u,
              "TIMER arg=%08X want 7777 (ROM passes timer_id, not handler)",
              h_a1);

        /* Unknown types must NOT call (call count primed nonzero first). */
        h_calls = RT12_CALL_PRIME;
        rtos_dispatch(rtos_build_dispatch(hb, RTOS_TYPE_RESERVED,
                                          RTOS_PRIORITY_S3), 0x99u);
        CHECK(h_calls == RT12_CALL_PRIME,
              "type3 dispatch called handler: calls=%u want %u",
              h_calls, RT12_CALL_PRIME);
        rtos_dispatch(rtos_build_dispatch(hb, 7u, RTOS_PRIORITY_S3), 0x99u);
        CHECK(h_calls == RT12_CALL_PRIME,
              "type7 dispatch called handler: calls=%u want %u",
              h_calls, RT12_CALL_PRIME);
    }

    /* ---- (i) handler==0 early return (guard removal -> SIGSEGV = red) ---- */
    h_calls = RT12_CALL_PRIME;
    rtos_dispatch(rtos_build_dispatch(0u, RTOS_TYPE_BASIC, RTOS_PRIORITY_S0),
                  0x42u);
    CHECK(h_calls == RT12_CALL_PRIME,
          "handler==0 did not early-return: calls=%u want %u",
          h_calls, RT12_CALL_PRIME);
    rtos_dispatch(rtos_build_dispatch(0u, RTOS_TYPE_TIMER, RTOS_PRIORITY_S3),
                  0x43u);
    CHECK(h_calls == RT12_CALL_PRIME,
          "handler==0 (TIMER) did not early-return: calls=%u want %u",
          h_calls, RT12_CALL_PRIME);

    /* ---- (j) scheduler ---- */
    rtos_init();
    h_calls = 0;
    h_a1 = 0;
    h_a2 = 0;
    seq_n = 0;
    seq[0] = '\0';
    seen_n = 0;

    h_calls = RT12_CALL_PRIME;
    rtos_scheduler(); /* empty queue: no-op, latch must be released */
    CHECK(h_calls == RT12_CALL_PRIME,
          "empty scheduler dispatched: calls=%u want %u",
          h_calls, RT12_CALL_PRIME);
    CHECK(rtos_get_current_priority() == RTOS_PRIORITY_S3,
          "priority after empty scheduler=%u want 3",
          rtos_get_current_priority());

    /* Single SUBFUNC task: exact arg through dequeue+dispatch. */
    h_calls = 0;
    CHECK(rtos_task_enqueue(rtos_build_dispatch(
              (uint32_t)(uintptr_t)&h_sub, RTOS_TYPE_SUBFUNC,
              RTOS_PRIORITY_S1), 0x00C0FFEEu) == 0, "sched enqueue");
    rtos_scheduler();
    CHECK(h_calls == 1, "scheduler calls=%u want 1", h_calls);
    CHECK(h_a1 == (uint32_t)(uintptr_t)&h_sub && h_a2 == 0x00C0FFEEu,
          "scheduler task args=(%08X,%08X) want (handler,00C0FFEE)",
          h_a1, h_a2);
    CHECK(rtos_queue_is_empty() == 1, "queue not empty after scheduler");
    CHECK(rtos_get_current_priority() == RTOS_PRIORITY_S3,
          "priority after S1 dispatch=%u want 3", rtos_get_current_priority());

    /* S0 dispatch must restore current_priority to S3 (kills a dropped
     * `current_priority = old_priority` restore: it would stick at 0). */
    h_calls = 0;
    CHECK(rtos_task_enqueue(rtos_build_dispatch(
              (uint32_t)(uintptr_t)&h_sub, RTOS_TYPE_SUBFUNC,
              RTOS_PRIORITY_S0), 0x111u) == 0, "S0 enqueue");
    rtos_scheduler();
    CHECK(h_calls == 1, "S0 scheduler calls=%u want 1", h_calls);
    CHECK(rtos_get_current_priority() == RTOS_PRIORITY_S3,
          "priority after S0 dispatch=%u want 3 (restore dropped?)",
          rtos_get_current_priority());

    /* Mixed priorities: at loop level current is S3, so all four
     * priorities dispatch, in FIFO order (not priority-sorted). */
    {
        static const uint32_t args[3] = { 0xA0u, 0xB0u, 0xC0u };
        static const uint8_t prios[3] = { RTOS_PRIORITY_S0, RTOS_PRIORITY_S3,
                                          RTOS_PRIORITY_S1 };
        seen_n = 0;
        for (int i = 0; i < 3; i++) {
            CHECK(rtos_task_enqueue(rtos_build_dispatch(
                      (uint32_t)(uintptr_t)&h_order, RTOS_TYPE_SUBFUNC,
                      prios[i]), args[i]) == 0, "mixed enqueue %d", i);
        }
        rtos_scheduler();
        CHECK(seen_n == 3 && seen[0] == args[0] && seen[1] == args[1]
              && seen[2] == args[2],
              "mixed dispatch order got [%08X,%08X,%08X] n=%d want FIFO "
              "A0,B0,C0 n=3",
              seen_n > 0 ? seen[0] : 0u, seen_n > 1 ? seen[1] : 0u,
              seen_n > 2 ? seen[2] : 0u, seen_n);
        CHECK(rtos_get_current_priority() == RTOS_PRIORITY_S3,
              "priority after mixed dispatch=%u want 3",
              rtos_get_current_priority());
    }

    /* Re-entrancy latch: nested rtos_scheduler() from inside a handler
     * must be a no-op -> log "AaB". A removed latch dispatches B inside
     * A -> "ABa" (red). */
    seq_n = 0;
    seq[0] = '\0';
    CHECK(rtos_task_enqueue(rtos_build_dispatch(
              (uint32_t)(uintptr_t)&h_latch_a, RTOS_TYPE_BASIC,
              RTOS_PRIORITY_S2), 0u) == 0, "latch enqueue A");
    CHECK(rtos_task_enqueue(rtos_build_dispatch(
              (uint32_t)(uintptr_t)&h_latch_b, RTOS_TYPE_BASIC,
              RTOS_PRIORITY_S1), 0u) == 0, "latch enqueue B");
    rtos_scheduler();
    CHECK(seq_n == 3 && memcmp(seq, "AaB", 3) == 0,
          "latch seq=\"%s\" want \"AaB\" (nested scheduler re-entered?)",
          seq);
    CHECK(rtos_queue_is_empty() == 1, "latch: queue not empty");
    CHECK(rtos_get_current_priority() == RTOS_PRIORITY_S3,
          "priority after latch test=%u want 3",
          rtos_get_current_priority());

    /* Null-handler task through the full scheduler path: must not crash,
     * must not touch the primed call count, must drain. */
    h_calls = RT12_CALL_PRIME;
    CHECK(rtos_task_enqueue(rtos_build_dispatch(
              0u, RTOS_TYPE_BASIC, RTOS_PRIORITY_S3), 0x55u) == 0,
          "null-task enqueue");
    rtos_scheduler();
    CHECK(h_calls == RT12_CALL_PRIME,
          "null-handler task called someone: calls=%u want %u",
          h_calls, RT12_CALL_PRIME);
    CHECK(rtos_queue_is_empty() == 1, "null-handler task not drained");

    /* rtos_yield: runs pending work and restores priority. */
    h_calls = 0;
    h_a1 = 0;
    CHECK(rtos_task_enqueue(rtos_build_dispatch(
              (uint32_t)(uintptr_t)&h_timer, RTOS_TYPE_TIMER,
              RTOS_PRIORITY_S2), 0x77u) == 0, "yield enqueue");
    rtos_yield();
    CHECK(h_calls == 1, "yield dispatched calls=%u want 1", h_calls);
    CHECK(h_a1 == 0x77u, "yield task arg=%08X want 77", h_a1);
    CHECK(rtos_get_current_priority() == RTOS_PRIORITY_S3,
          "priority after yield=%u want 3", rtos_get_current_priority());

    /* ---- (k) context save/restore on the in-page fake stack ---- */
    {
        uint32_t sp = RT12_FAKE_SP;
        int bad;

        /* Prime the whole frame region + margin with 0xA5. */
        for (uint32_t a = RT12_FAKE_SP - 0x80u; a < RT12_FAKE_SP; a++) {
            *rt12_u8(a) = RT12_FRAME_PRIME;
        }

        /* BASIC save: core zeroed (primed A5), FP slot untouched (A5
         * survives — proves the type guard), sp -= 0x44. */
        rtos_context_save(&sp, RTOS_TYPE_BASIC);
        CHECK(sp == RT12_FAKE_SP - RTOS_CTX_FRAME_SIZE_FP,
              "BASIC save sp=%08X want %08X", sp,
              RT12_FAKE_SP - RTOS_CTX_FRAME_SIZE_FP);
        bad = rt12_count_bytes(sp, RTOS_CTX_FRAME_SIZE, 0x00u);
        CHECK(bad == 0,
              "BASIC save core: %d of 52 bytes != 0 (primed A5)", bad);
        bad = rt12_count_bytes(sp + RTOS_CTX_FRAME_SIZE,
                               RTOS_CTX_FRAME_SIZE_FP - RTOS_CTX_FRAME_SIZE,
                               RT12_FRAME_PRIME);
        CHECK(bad == 0,
              "BASIC save FP slot: %d of 16 bytes != A5 (type guard broken?)",
              bad);
        rtos_context_restore(&sp, RTOS_TYPE_BASIC);
        CHECK(sp == RT12_FAKE_SP,
              "BASIC restore sp=%08X want %08X", sp, RT12_FAKE_SP);

        /* TIMER save: re-prime, then ALL 68 bytes must be zero. */
        for (uint32_t a = RT12_FAKE_SP - 0x80u; a < RT12_FAKE_SP; a++) {
            *rt12_u8(a) = RT12_FRAME_PRIME;
        }
        sp = RT12_FAKE_SP;
        rtos_context_save(&sp, RTOS_TYPE_TIMER);
        CHECK(sp == RT12_FAKE_SP - RTOS_CTX_FRAME_SIZE_FP,
              "TIMER save sp=%08X want %08X", sp,
              RT12_FAKE_SP - RTOS_CTX_FRAME_SIZE_FP);
        bad = rt12_count_bytes(sp, RTOS_CTX_FRAME_SIZE_FP, 0x00u);
        CHECK(bad == 0,
              "TIMER save frame: %d of 68 bytes != 0 (primed A5)", bad);
        rtos_context_restore(&sp, RTOS_TYPE_TIMER);
        CHECK(sp == RT12_FAKE_SP,
              "TIMER restore sp=%08X want %08X", sp, RT12_FAKE_SP);
    }

    munmap(page, RT12_PAGE_LEN);

    if (failures == 0) {
        printf("PASS link_rtos_queue_dispatch (real rtos.c TU)\n");
    } else {
        printf("%d FAILURES link_rtos_queue_dispatch\n", failures);
    }
    return failures != 0;
}

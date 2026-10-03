/*
 * link_boot.c — Link pilot 16: compile-link-run against the REAL
 * firmware/c/boot.c TU (boot chain: bsc/gpio/wdt/hw_init/ovrcount/
 * trampoline), not a model replica. Closes the last zero-coverage core
 * TU pair alongside link_main: this TU had no link rule, no model
 * harness exercising the .c body, and no c/tests on any side.
 *
 * NAMED BUILD CONDITIONAL (the GO for this pilot was conditional on it;
 * re-verified at pilot time, fail-closed):
 *   boot.c does NOT compile under stock `gcc -std=c11 -Wall -Wextra
 *   -Werror -O2`: exactly 12 -Warray-bounds ERRORS, and ALL of them are
 *   inside reset_handler — macro-expansion sites boot.c:277, 290, 303,
 *   314, 318, 320, 323, 324, 329, 331, 335, 340 (the diagnostics name
 *   the macro definitions ROM_DEFAULT_RV/ALT_OFFSET/REASON_ADDR/
 *   BOOT_CONT_ADDR/MAGIC_VALUE/WDT_STATUS/WDT_ALT at lines 43-53; GCC's
 *   `In function 'reset_handler'` context covers every one — no site
 *   lies outside reset_handler:274-346). The link rule therefore adds
 *   -Wno-error=array-bounds (precedent: the 5 rules that use
 *   -Wno-error=unused-function); with the flag boot.c compiles with 0
 *   errors and exactly those 12 warnings. If any -Werror site ever
 *   appears OUTSIDE reset_handler, this rule must be revisited (the
 *   relaxation would no longer be justified by the named conditional).
 *
 * Mechanism proof: zero stubs — undefined-symbol chain closed by in-repo
 * TUs, verified at pilot time:
 *   nm -u boot.o = {atu_configure_io_channel, spi_clk_high_wait,
 *                   spi_clk_low_wait}  (timer.c + eeprom.c)
 * boot.o has 10 T symbols: Manual_Reset, bsc_init, gpio_init,
 * reset_handler, wdt_init, hw_init_1/2/3, checkWatchdogTimer_OVRCOUNT,
 * vector_trampoline_set_sp. A firmware revert of the EC20 base fix, the
 * gpio values, the WDT magic sequence, the SPI config stores, the
 * hw_init_2 buffer/sync stores, or the hw_init_3 index stores fails this
 * binary at run time; a signature change fails at compile (boot.h).
 *
 * Host execution boundary (THREE 4 KiB pages, mmap MAP_FIXED,
 * MAP_SHARED — the fork probe observes child-side phase writes):
 *   0xFFFFD000 — EEPROM buf 0xFFFFDFE4..0xDFEB, marker 0xFFFFDFEC,
 *                serial queue 0xFFFFDFF0..0xDFF8, task indices
 *                0xFFFFDFB4/B6, boot magic 0xFFFFDFFC;
 *   0xFFFFE000 — WDT 0xFFFFEC10/EC12, BSC 0xFFFFEC20..EC26, tail poll
 *                0xFFFFED18, SPI 0xFFFFE401/402/404;
 *   0xFFFFF000 — BSC tail 0xFFFFF70A, PFC 0xFFFFF720..0xFFFFF778, ATU
 *                TIOR0 0xFFFFF740 (ATU_BASE+ATU_TIOR0_OFFSET).
 * (D shared with link_l10/m7/rtos/eeprom, E with link_m8/eeprom, F with
 * link_m4/m6/eeprom — separate processes, MAP_FIXED cannot collide.)
 *
 * Negative space (fork-probed INSIDE this harness, S9): page
 * 0x0000-0x0FFF is unmapable (mmap_min_addr=65536), so entering
 * reset_handler faults at its FIRST ROM deref 0x58C (ROM_DEFAULT_RV).
 * reset_handler's ENTIRE body and Manual_Reset's phase 3 (the
 * reset_handler(0,0) call, boot.c:81) are therefore documented
 * linked-but-never-entered paths; S9 asserts the fault address is
 * exactly 0x58C for both a direct reset_handler call and a full
 * Manual_Reset call, and — via the MAP_SHARED pages — that Manual_Reset
 * phases 1-2 (bsc_init, gpio_init) DID execute for real before the
 * fault (sentinels observed changed by the child).
 *
 * Every zero-expect is primed NON-ZERO first (h4 F1 lesson); no
 * tautological/self-referential asserts. Kills (each demonstrated by a
 * single-edit mutant of the real firmware sources, IDENTICAL Makefile
 * CFLAGS including -Wno-error=array-bounds — table in the pilot commit
 * body):
 *   S1 bsc_init: EC20..EC26/F70A/ED18 primed 0x5A5A -> 000F/FFFF/FFFF/
 *      0000, F70A=3C04, ED18=0. Kills: EC20->EC80 base revert (writes
 *      land on primed cells), dropped tail stores.
 *   S2 gpio_init: all 37 PFC registers primed 0x5A5A -> exact ROM
 *      finals (incl. the trap pair PMR3_BASE=0xEFFF written ONLY at
 *      boot.c:201 vs PMR2_BASE=0x9000 at :205); guards PMR12_3/4
 *      survive. Kills: PMR2/PMR3 mix-ups, dropped/changed stores.
 *   S3 wdt_init: RSTCSR/TCSR primed 0x1234 -> 5A1F/A53C. Kills: wrong
 *      magic, dropped ack/feed, narrowed store address -> SIGSEGV.
 *   S4 hw_init_1: SPI clk primed 0xFF, CONTROL/CONFIG primed 0xFFFF,
 *      ATU TIOR0 primed 0xA5A5 -> clk 0xFE (bit0 cleared, rest
 *      preserved), 0, 0, TIOR0=0 (REAL atu_configure_io_channel(0)
 *      effect). Kills: dropped SPI config stores, dropped/narrowed
 *      atu write, low-wait drop/clobber; removed wait bound -> hang ->
 *      3 s SIGALRM FAIL.
 *   S5 hw_init_2: buffers primed 0x5A, sync primed 0, marker primed
 *      0x55 + guards -> bufs 0, sync 0xAA, marker 0x55 MUST SURVIVE.
 *      Kills: marker-touching mutant (i<9 overrun), dropped sync,
 *      overrun guards.
 *   S6 hw_init_3: indices primed 0x1234/0x5678 -> both 0.
 *   S7 checkWatchdogTimer_OVRCOUNT: TCSR 0x0100 -> 1 (count 7);
 *      TCSR 0x0000 -> 0 (count 3); count 0 -> 0. Kills: mask/branch/
 *      return inversions.
 *   S8 vector_trampoline_set_sp (-no-pie rule, longjmp callee): callee
 *      pointer must fit in uint32 and MUST be reached (non-return is a
 *      FAIL). Kills: dropped entry() (falls to while(1) -> SIGALRM),
 *      pointer truncation (rule loses -no-pie -> runtime CHECK fails),
 *      wild jump -> SIGSEGV kills the run.
 *   S9 fork negative-space probe: reset_handler(0,0) and Manual_Reset
 *      both fault at EXACTLY 0x58C; Manual_Reset phase sentinels prove
 *      bsc_init+gpio_init executed inside the child first.
 *
 * Documented limits (h5 style — real, not faked asserts):
 *   - reset_handler: ENTIRE body never entered (first deref 0x58C
 *     faults; fork-probed in S9) — its wdt/hw_init calls, magic check,
 *     reason-byte store and trampoline jump are unreachable on the host;
 *   - Manual_Reset: phases 1-2 covered for real (S9 observed via shared
 *     pages); phase 3 unconditional (boot.c:81) so the function itself
 *     is only ever entered as a faulting path — documented, not entered
 *     to completion;
 *   - vector_trampoline_set_sp: the SP=0xFFFFDFA0 store is a documented
 *     host no-op (no SH-2 stack switch on x86-64) — unobservable; the
 *     trailing while(1) (boot.c:551) is unreachable in S8 because the
 *     callee longjmps out by construction;
 *   - wdt_init: the intermediate TCSR=0x5A00 store and read-back
 *     (boot.c:374-377) leave no trace in a final-state snapshot —
 *     unobservable; final RSTCSR/TCSR values are asserted;
 *   - bsc_init tail: the 0xFFFFED18 poll early-exit (bit15 set) is
 *     unobservable on static host memory (the code stores 0 first, so
 *     the poll ALWAYS times out — the bound's PRESENCE is what the 3 s
 *     SIGALRM enforces); only the stores are value-asserted;
 *   - hw_init_1: a dropped spi_clk_high_wait CALL is unobservable from
 *     final state (low_wait clears the very bit high_wait sets) —
 *     documented; its 4000-iter bound IS enforced (clk primed with
 *     status bit3 set makes it spin; removing the bound hangs ->
 *     SIGALRM FAIL);
 *   - S7: the overflow fast-return vs full-count timing is not asserted
 *     (flakiness) — return values of both branches are.
 *
 * Build (see firmware/tests/Makefile link-check):
 *   gcc -std=c11 -Wall -Wextra -Werror -Wno-error=array-bounds -O2
 *       -I../include -no-pie link/link_boot.c ../c/boot.c ../c/eeprom.c
 *       ../c/timer.c -o /tmp/fwtest/link_boot -lm
 */
#define _POSIX_C_SOURCE 200809L   /* sigaction/siginfo for the S9 probe */

#include <setjmp.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/wait.h>
#include <unistd.h>

#include "platform.h"  /* WDT/PFC/SPI/queue macros (same as boot.c) */
#include "boot.h"      /* real extern prototypes — same header boot.c uses */

/* ---- MMIO pins ------------------------------------------------------- */
#define PG_D   0xFFFFD000u
#define PG_E   0xFFFFE000u
#define PG_F   0xFFFFF000u
#define PG_LEN 0x1000u

#define A_BSC_BASE   0xFFFFEC20u  /* bsc_init base (no platform.h macro) */
#define A_BSC_TAIL_A 0xFFFFF70Au  /* bsc_init tail store a */
#define A_BSC_TAIL_B 0xFFFFED18u  /* bsc_init tail store b + poll cell */
#define A_ATU_TIOR0  (ATU_BASE + ATU_TIOR0_OFFSET)  /* 0xFFFFF740 */
#define A_ROM_RV     0x0000058Cu  /* reset_handler first deref (blocked) */

#define IN_PG(base, a) ((uint64_t)(a) >= (uint64_t)(base) && \
                        (uint64_t)(a) < (uint64_t)(base) + (uint64_t)PG_LEN)

/* Real firmware macro pins (compile-time kills on a firmware move). */
_Static_assert(IN_PG(PG_E, A_BSC_BASE) && IN_PG(PG_E, A_BSC_BASE + 6) &&
               IN_PG(PG_E, A_BSC_TAIL_B) && IN_PG(PG_E, (uintptr_t)&WDT_RSTCSR),
               "boot E-page pins outside mapped page");
_Static_assert(IN_PG(PG_F, A_BSC_TAIL_A) &&
               IN_PG(PG_F, (uintptr_t)&PFC_PMR12_4) &&
               IN_PG(PG_F, A_ATU_TIOR0),
               "boot F-page pins outside mapped page");
_Static_assert((uintptr_t)&WDT_TCSR == 0xFFFFEC10u &&
               (uintptr_t)&WDT_RSTCSR == 0xFFFFEC12u, "WDT addrs moved");
_Static_assert(A_BSC_BASE == 0xFFFFEC20u && A_BSC_TAIL_A == 0xFFFFF70Au &&
               A_BSC_TAIL_B == 0xFFFFED18u, "boot literals moved");
_Static_assert(A_ATU_TIOR0 == 0xFFFFF740u, "ATU TIOR0 address moved");
_Static_assert(IN_PG(PG_D, EEPROM_RAM_BUF_A) &&
               IN_PG(PG_D, EEPROM_RAM_BUF_A + 7) &&
               IN_PG(PG_D, EEPROM_RAM_BUF_A_MARKER) &&
               IN_PG(PG_D, SERIAL_QUEUE_BASE) &&
               IN_PG(PG_D, SERIAL_QUEUE_BASE + 8) &&
               IN_PG(PG_D, 0xFFFFDFB4u), "boot D-page pins outside page");
_Static_assert(SERIAL_QUEUE_BASE == 0xFFFFDFF0u &&
               EEPROM_RAM_BUF_A == 0xFFFFDFE4u, "queue/buf base moved");
_Static_assert(WDT_RSTCSR_VALUE == 0x5A1F && WDT_TCSR_VALUE == 0x5A00 &&
               WDT_FEED_VALUE == 0xA53C, "WDT magic values moved");
_Static_assert(SPI_CLK_HIGH == 0x01 && SPI_STATUS_BIT == 0x08,
               "SPI bits moved");

static int failures = 0;

#define CHECK(cond, ...) do { \
    if (!(cond)) { printf("FAIL: "); printf(__VA_ARGS__); printf("\n"); failures++; } \
} while (0)

static volatile uint8_t *mm_u8(uint32_t addr)
{
    return (volatile uint8_t *)(uintptr_t)addr;
}

static volatile uint16_t *mm_u16(uint32_t addr)
{
    return (volatile uint16_t *)(uintptr_t)addr;
}

/* ---- Hang watchdog: a removed bound must FAIL, not hang the gate ---- */
static char watch_msg[160];
static volatile sig_atomic_t watch_len;

static void on_alarm(int sig)
{
    (void)sig;
    if (watch_len > 0) {
        ssize_t w = write(STDOUT_FILENO, watch_msg, (size_t)watch_len);
        (void)w;
    }
    _exit(1);
}

static void arm_watch(const char *what)
{
    watch_len = (sig_atomic_t)snprintf(watch_msg, sizeof watch_msg,
        "FAIL: %s: 3s SIGALRM watchdog fired (unbounded loop / hang)\n", what);
    alarm(3);  /* every bounded path here runs in microseconds */
}

/* ---- S1: bsc_init ---------------------------------------------------- */
static void s1_bsc_init(void)
{
    volatile uint16_t *ec = mm_u16(A_BSC_BASE);

    /* Prime every target cell NON-zero 0x5A5A (F1: zero-expects for
     * EC26 / ED18 are primed nonzero; 0x5A5A differs from ALL expects). */
    ec[0] = ec[1] = ec[2] = ec[3] = 0x5A5A;
    *mm_u16(A_BSC_TAIL_A) = 0x5A5A;
    *mm_u16(A_BSC_TAIL_B) = 0x5A5A;

    bsc_init();

    CHECK(ec[0] == 0x000F, "S1 bsc[0] (EC20)=%04X want 000F (base revert?)",
          (unsigned)ec[0]);
    CHECK(ec[1] == 0xFFFF, "S1 bsc[1] (EC22)=%04X want FFFF", (unsigned)ec[1]);
    CHECK(ec[2] == 0xFFFF, "S1 bsc[2] (EC24)=%04X want FFFF", (unsigned)ec[2]);
    CHECK(ec[3] == 0x0000, "S1 bsc[3] (EC26)=%04X want 0000", (unsigned)ec[3]);
    CHECK(*mm_u16(A_BSC_TAIL_A) == 0x3C04,
          "S1 tail a (F70A)=%04X want 3C04", (unsigned)*mm_u16(A_BSC_TAIL_A));
    CHECK(*mm_u16(A_BSC_TAIL_B) == 0x0000,
          "S1 tail b (ED18)=%04X want 0000", (unsigned)*mm_u16(A_BSC_TAIL_B));
    /* The ED18 poll itself: always-timeout on static host memory (the
     * store above writes 0 first) — only its BOUND is enforced, by the
     * SIGALRM watchdog. Documented unobservable (header). */
}

/* ---- S2: gpio_init --------------------------------------------------- */
struct gpio_pin {
    volatile uint16_t *reg;
    uint16_t want;
};

static void s2_gpio_init(void)
{
    /* All 37 distinct PFC registers gpio_init writes, with their exact
     * ROM finals (boot.c:195-252; PMR3 at 0xF724 is written twice and
     * ends 0). The trap pair: PMR3_BASE (0xF738) gets 0xEFFF from the
     * ONLY write at boot.c:201; PMR2_BASE (0xF730) gets 0x9000 at :205. */
    static const struct gpio_pin pins[] = {
        { &PFC_PDR1,      0xFFFF }, { &PFC_PMR2,      0x0000 },
        { &PFC_PMR3,      0x0000 }, { &PFC_PMR1,      0x0000 },
        { &PFC_PMR3_BASE, 0xEFFF }, { &PFC_PMR2_1,    0x0000 },
        { &PFC_PMR2_2,    0x0000 }, { &PFC_PMR2_3,    0x0000 },
        { &PFC_PMR2_BASE, 0x9000 }, { &PFC_PMR3_1,    0x001F },
        { &PFC_PMR3_2,    0x0000 }, { &PFC_PMR4_BASE, 0x3EFF },
        { &PFC_PMR4_1,    0x0000 }, { &PFC_PMR4_2,    0x0000 },
        { &PFC_PMR4_3,    0x2000 }, { &PFC_PMR5_BASE, 0xFFFF },
        { &PFC_PMR5_1,    0x0000 }, { &PFC_PMR5_2,    0x0000 },
        { &PFC_PMR5_3,    0x8000 }, { &PFC_PMR6_BASE, 0x0000 },
        { &PFC_PMR6_1,    0x000F }, { &PFC_PMR6_2,    0x0000 },
        { &PFC_PMR7_BASE, 0x0000 }, { &PFC_PMR7_1,    0x0000 },
        { &PFC_PMR7_2,    0x0000 }, { &PFC_PMR7_3,    0x0000 },
        { &PFC_PMR8_BASE, 0x0000 }, { &PFC_PMR10_BASE,0x0000 },
        { &PFC_PMR10_1,   0x0000 }, { &PFC_PMR10_2,   0x0000 },
        { &PFC_PMR11_BASE,0x3FFF }, { &PFC_PMR11_1,   0x0000 },
        { &PFC_PMR11_2,   0x0000 }, { &PFC_PMR11_3,   0x0000 },
        { &PFC_PMR12_BASE,0x0000 }, { &PFC_PMR12_1,   0x0050 },
        { &PFC_PMR12_2,   0x3FFF },
    };
    static const size_t npins = sizeof pins / sizeof pins[0];
    /* Overrun guards: gpio_init must NOT write past PMR12_2. */
    PFC_PMR12_3 = 0x5A5A;
    PFC_PMR12_4 = 0x5A5A;

    for (size_t i = 0; i < npins; i++) {
        *pins[i].reg = 0x5A5A;   /* prime nonzero; differs from want */
    }

    gpio_init();

    for (size_t i = 0; i < npins; i++) {
        CHECK(*pins[i].reg == pins[i].want,
              "S2 gpio[%zu] @%p = %04X want %04X",
              i, (void *)pins[i].reg, (unsigned)*pins[i].reg,
              (unsigned)pins[i].want);
    }
    CHECK(PFC_PMR12_3 == 0x5A5A,
          "S2 overrun: PMR12_3 mutated to %04X want 5A5A",
          (unsigned)PFC_PMR12_3);
    CHECK(PFC_PMR12_4 == 0x5A5A,
          "S2 overrun: PMR12_4 mutated to %04X want 5A5A",
          (unsigned)PFC_PMR12_4);
}

/* ---- S3: wdt_init ---------------------------------------------------- */
static void s3_wdt_init(void)
{
    WDT_RSTCSR = 0x1234;   /* prime both NONzero, != the magics */
    WDT_TCSR   = 0x1234;

    wdt_init();

    CHECK(WDT_RSTCSR == 0x5A1F,
          "S3 RSTCSR=%04X want 5A1F (ack magic)", (unsigned)WDT_RSTCSR);
    CHECK(WDT_TCSR == 0xA53C,
          "S3 TCSR=%04X want A53C (feed)", (unsigned)WDT_TCSR);
    /* The intermediate 0x5A00 store + read-back leave no final-state
     * trace — documented unobservable (header). */
}

/* ---- S4: hw_init_1 --------------------------------------------------- */
static void s4_hw_init_1(void)
{
    /* clk primed 0xFF: status bit3 SET makes high_wait take its stuck
     * path (bound enforced by SIGALRM); low_wait must clear bit0 and
     * leave the other 7 bits alone -> 0xFE. */
    SPI_CLK_DATA_CTRL = 0xFFu;
    SPI_CONTROL = 0xFFFFu;      /* zero-expect primed nonzero */
    SPI_CONFIG  = 0xFFFFu;      /* zero-expect primed nonzero */
    *mm_u16(A_ATU_TIOR0) = 0x5A5A;  /* zero-expect primed nonzero */

    hw_init_1();

    CHECK(SPI_CLK_DATA_CTRL == 0xFEu,
          "S4 clk=%02X want FE (bit0 cleared, rest preserved)",
          (unsigned)SPI_CLK_DATA_CTRL);
    CHECK(SPI_CONTROL == 0x0000u,
          "S4 SPI_CONTROL=%04X want 0000 (dropped config?)",
          (unsigned)SPI_CONTROL);
    CHECK(SPI_CONFIG == 0x0000u,
          "S4 SPI_CONFIG=%04X want 0000 (dropped config?)",
          (unsigned)SPI_CONFIG);
    CHECK(*mm_u16(A_ATU_TIOR0) == 0x0000u,
          "S4 ATU TIOR0=%04X want 0000 (real atu_configure_io_channel(0))",
          (unsigned)*mm_u16(A_ATU_TIOR0));
}

/* ---- S5: hw_init_2 --------------------------------------------------- */
static void s5_hw_init_2(void)
{
    volatile uint8_t *eb = mm_u8(EEPROM_RAM_BUF_A);
    volatile uint8_t *sb = mm_u8(SERIAL_QUEUE_BASE);
    volatile uint8_t *marker = mm_u8(EEPROM_RAM_BUF_A_MARKER);
    int nz;

    for (int i = 0; i < 8; i++) { eb[i] = 0x5A; sb[i] = 0x5A; }  /* F1 */
    sb[8] = 0x00;                       /* sync primed 0 -> must become 0xAA */
    *marker = EEPROM_VALID_MARKER;      /* 0x55: must SURVIVE untouched */
    eb[9] = 0x66;                       /* guard right of the marker */
    sb[9] = 0x33;                       /* guard right of the sync byte */

    hw_init_2();

    nz = 0;
    for (int i = 0; i < 8; i++) { if (eb[i] != 0) nz++; if (sb[i] != 0) nz++; }
    CHECK(nz == 0, "S5 hw_init_2: %d buffer bytes not cleared", nz);
    CHECK(sb[8] == SERIAL_SYNC_READY,
          "S5 sync=%02X want AA", (unsigned)sb[8]);
    CHECK(*marker == EEPROM_VALID_MARKER,
          "S5 marker=%02X want 55 (hw_init_2 must NOT touch it)",
          (unsigned)*marker);
    CHECK(eb[9] == 0x66 && sb[9] == 0x33,
          "S5 overrun guard: eb[9]=%02X sb[9]=%02X want 66/33",
          (unsigned)eb[9], (unsigned)sb[9]);
}

/* ---- S6: hw_init_3 --------------------------------------------------- */
static void s6_hw_init_3(void)
{
    TASK_QUEUE_WRITE_IDX = 0x1234;   /* prime both NONzero (F1) */
    TASK_QUEUE_READ_IDX  = 0x5678;

    hw_init_3();

    CHECK(TASK_QUEUE_WRITE_IDX == 0 && TASK_QUEUE_READ_IDX == 0,
          "S6 hw_init_3 indices: w=%04X r=%04X want 0/0",
          (unsigned)TASK_QUEUE_WRITE_IDX, (unsigned)TASK_QUEUE_READ_IDX);
}

/* ---- S7: checkWatchdogTimer_OVRCOUNT --------------------------------- */
static void s7_ovrcount(void)
{
    int r;

    WDT_TCSR = 0x0100;    /* overflow bit set -> early return 1 */
    r = checkWatchdogTimer_OVRCOUNT(7);
    CHECK(r == 1, "S7 ovf-set(count=7)=%d want 1", r);
    WDT_TCSR = 0x0000;    /* clear -> runs all delay_loops -> 0 */
    r = checkWatchdogTimer_OVRCOUNT(3);
    CHECK(r == 0, "S7 ovf-clear(count=3)=%d want 0", r);
    r = checkWatchdogTimer_OVRCOUNT(0);
    CHECK(r == 0, "S7 count=0=%d want 0", r);
}

/* ---- S8: vector_trampoline_set_sp (-no-pie + longjmp callee) --------- */
static jmp_buf tramp_jb;

static void tramp_callee(void)
{
    longjmp(tramp_jb, 1);   /* never returns to the trampoline */
}

static void s8_trampoline(void)
{
    static uint32_t target;

    /* If the rule ever loses -no-pie, the PIE callee address truncates
     * here and this CHECK fails BEFORE the wild jump. */
    target = (uint32_t)(uintptr_t)(void *)&tramp_callee;
    CHECK((uintptr_t)(void *)&tramp_callee == (uintptr_t)target,
          "S8 callee address %p truncates to uint32 — rule needs -no-pie",
          (void *)&tramp_callee);

    if (setjmp(tramp_jb) == 0) {
        vector_trampoline_set_sp(target);   /* callee longjmps back */
        CHECK(0, "S8: vector_trampoline_set_sp returned without reaching "
                 "the callee");
    }
    /* Landing here IS the proof the callee ran through the uint32 cast:
     * the only path to setjmp!=0 is tramp_callee's longjmp. */
}

/* ---- S9: negative-space fork probe (reset_handler / Manual_Reset) ---- */
static int fault_pipe_wr = -1;

static void on_fault(int sig, siginfo_t *si, void *ctx)
{
    uintptr_t addr = (uintptr_t)si->si_addr;
    ssize_t w;
    (void)sig; (void)ctx;
    w = write(fault_pipe_wr, &addr, sizeof addr);
    (void)w;
    _exit(42);   /* faulted and reported */
}

static void child_call(void (*fn)(void))
{
    struct sigaction sa;
    memset(&sa, 0, sizeof sa);
    sa.sa_sigaction = on_fault;
    sa.sa_flags = SA_SIGINFO;
    sigemptyset(&sa.sa_mask);
    if (sigaction(SIGSEGV, &sa, NULL) != 0 ||
        sigaction(SIGBUS, &sa, NULL) != 0) {
        _exit(44);   /* probe setup failed — parent CHECK fails closed */
    }
    fn();
    _exit(43);   /* returned — the documented fault did NOT happen */
}

static int run_fault_child(void (*fn)(void), uintptr_t *fault_out)
{
    int fds[2];
    pid_t pid;
    ssize_t n;
    int st;

    *fault_out = 0;
    if (pipe(fds) != 0) { CHECK(0, "S9 pipe() failed"); return 0; }
    pid = fork();
    if (pid < 0) { close(fds[0]); close(fds[1]);
                   CHECK(0, "S9 fork() failed"); return 0; }
    if (pid == 0) {
        close(fds[0]);
        fault_pipe_wr = fds[1];
        child_call(fn);   /* does not return */
    }
    close(fds[1]);
    n = read(fds[0], fault_out, sizeof *fault_out);
    close(fds[0]);
    if (waitpid(pid, &st, 0) != pid) st = -1;
    CHECK(WIFEXITED(st) && WEXITSTATUS(st) == 42,
          "S9 child did not take the documented fault path (status=0x%x)",
          (unsigned)st);
    CHECK(n == (ssize_t)sizeof *fault_out,
          "S9 child fault address not reported (n=%ld)", (long)n);
    return n == (ssize_t)sizeof *fault_out;
}

static void call_reset(void)   { reset_handler(0, 0); }
static void call_manual(void)  { Manual_Reset(); }

static void s9_negative_space(void)
{
    uintptr_t fault = 0;

    /* (a) Direct reset_handler entry: page 0 is unmapable
     * (mmap_min_addr=65536) -> first deref ROM_DEFAULT_RV faults. */
    if (run_fault_child(call_reset, &fault)) {
        CHECK(fault == A_ROM_RV,
              "S9 reset_handler fault=0x%lx want 0x58C (documented "
              "never-entered boundary)", (unsigned long)fault);
    }

    /* (b) Full Manual_Reset: phase sentinels (primed here) must be
     * overwritten by bsc_init (phase 1) and gpio_init (phase 2) inside
     * the child — observed through the MAP_SHARED pages — before the
     * phase-3 reset_handler fault. */
    *mm_u16(A_BSC_BASE) = 0xBEEF;   /* != 0x000F */
    PFC_PDR1 = 0x0000;              /* != 0xFFFF */
    fault = 0;
    if (run_fault_child(call_manual, &fault)) {
        CHECK(fault == A_ROM_RV,
              "S9 Manual_Reset fault=0x%lx want 0x58C (phase 3 never "
              "entered)", (unsigned long)fault);
    }
    CHECK(*mm_u16(A_BSC_BASE) == 0x000F,
          "S9 Manual_Reset phase1 (bsc_init) not executed: EC20=%04X "
          "want 000F", (unsigned)*mm_u16(A_BSC_BASE));
    CHECK(PFC_PDR1 == 0xFFFF,
          "S9 Manual_Reset phase2 (gpio_init) not executed: PDR1=%04X "
          "want FFFF", (unsigned)PFC_PDR1);
}

int main(void)
{
    signal(SIGALRM, on_alarm);
    arm_watch("link_boot");

    if (mmap((void *)(uintptr_t)PG_D, PG_LEN, PROT_READ | PROT_WRITE,
             MAP_SHARED | MAP_ANONYMOUS | MAP_FIXED,
             -1, 0) != (void *)(uintptr_t)PG_D ||
        mmap((void *)(uintptr_t)PG_E, PG_LEN, PROT_READ | PROT_WRITE,
             MAP_SHARED | MAP_ANONYMOUS | MAP_FIXED,
             -1, 0) != (void *)(uintptr_t)PG_E ||
        mmap((void *)(uintptr_t)PG_F, PG_LEN, PROT_READ | PROT_WRITE,
             MAP_SHARED | MAP_ANONYMOUS | MAP_FIXED,
             -1, 0) != (void *)(uintptr_t)PG_F) {
        printf("FAIL: mmap of D/E/F pages failed\n");
        return 1;
    }

    s1_bsc_init();
    s2_gpio_init();
    s3_wdt_init();
    s4_hw_init_1();
    s5_hw_init_2();
    s6_hw_init_3();
    s7_ovrcount();
    s8_trampoline();
    s9_negative_space();

    /* reset_handler / Manual_Reset phase 3 are never entered past the
     * fork probe above (documented in the header comment). */
    alarm(0);
    if (failures) {
        printf("link_boot: %d FAIL(s)\n", failures);
    } else {
        printf("link_boot: all scenarios pass (9/9)\n");
    }
    return failures != 0;
}

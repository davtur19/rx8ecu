/* ============================================================================
 * oracle_reset_handler.c  —  host test rig for rx8_reset_handler @0x4E0
 * ============================================================================
 * Compile together with src/rx8_reset_handler.c and pipe test vectors on
 * stdin; one vector per line, whitespace-separated hex tokens:
 *
 *     rh <cold> <reason> <magic> <w7fffc> <wderef> <alt1000> <w7fff8>
 *        <wdt0> <wdt1>
 *              -> <ret> <t572> <t170> <t41c> <t3d4> <t5b0> <t5b0n>
 *                 <t8f6> <t8f6c> <t40> <t40rv> <magic_after> <dfa8> <wdtcnt>
 *
 *   cold      : r4 cold_start flag (0 = cold, else warm)
 *   reason    : r5 reset reason byte (stored to 0xFFFFDFA8 on warm start)
 *   magic     : pre-seed of [0xFFFFDFFC] (the boot magic check)
 *   w7fffc    : [0x7FFFC]  WDT status cell seed
 *   wderef    : value placed AT address w7fffc (the **0x7FFFC deref target)
 *   alt1000   : [0x1000]   alternate reset-vector cell seed
 *   w7fff8    : [0x7FFF8]  second alternate reset-vector cell seed
 *   wdt0/wdt1 : the two seeded checkWatchdog @0x5B0 returns (call 1 / call 2;
 *               calls 3.. return 0)
 *
 * The oracle mirrors the emulator-side set-up of
 * harness_reset_handler.py.  It mmap()s the pages backing the trace cells
 * (0xFFFFE000), the watchdog counter (0xFFFFD100), the boot-magic cell
 * (0xFFFFDFFC) and the reason byte (0xFFFFDFA8), and re-implements ONLY the
 * caller-side scaffolding and the stubbed callee layer:
 *    - rx_reset_watchdog / rx_reset_hw_init_1..3  the 0x572/0x170/0x41C/0x3D4
 *      SH-2 trace stubs the emulator installs (write the tag dword);
 *    - rx_reset_check_watchdog                     the stateful 0x5B0 stub:
 *      bumps the counter, traces tag + count, returns wdt0/wdt1/0;
 *    - rx_reset_warm                               the 0x8F6 stub (traces
 *      the tag and the cold_start argument);
 *    - rx_reset_boot                               the 0x40 terminal trampoline
 *      (traces tag + reset vector, returns the emulator SENT constant);
 *    - rx_reset_read_wdt_status/_alt / read_alt_rv / ram_read32
 *      the below-mmap cells 0x7FFFC/0x7FFF8/0x1000 and the sparse **deref,
 *      which the ROM touches through literals at 0x5A4/0x5A8/0x58E.
 * It contains NO copy of the reset_handler logic itself; that lives solely in
 * the reconstructed source under test (src/rx8_reset_handler.c).
 *
 * Memory map used (identical on emulator and host, matching the ROM):
 *   0xFFFFE000    trace cells (t572, t170, t41c, t3d4, t5b0, t5b0n,
 *                 t8f6, t8f6c, t40, t40rv)
 *   0xFFFFD100    watchdog call counter (start 0, +1 per checkWatchdog)
 *   0xFFFFDFFC    boot magic location (read for the cold-start check)
 *   0xFFFFDFA8    reason byte (written on warm start only)
 *   0x0007FFFC    WDT status cell        (module state, below mmap)
 *   0x0007FFF8    WDT status alt cell    (module state, below mmap)
 *   0x00001000    alternate reset vector (module state, below mmap)
 * ==========================================================================*/
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

#include "rx8_hw.h"

/* src/rx8_reset_handler.c — the function under test. */
uint32_t rx_reset_handler(int cold_start, uint8_t reason);

#define TRACE_BASE     0xFFFFE000u   /* trace cells (16 dwords)            */
#define WDT_CNT        0xFFFFD100u   /* checkWatchdog call counter         */
#define MAGIC_LOC      0xFFFFDFFCu   /* boot magic location                */
#define REASON_LOC     0xFFFFDFA8u   /* reset reason byte (warm path)      */
#define SENT           0xEEEE0000u   /* emulator terminal constant         */

/* Below-mmap ROM-literal cells (module state, seeded per vector). */
static uint32_t g_wdt0;       /* checkWatchdog return on call 1            */
static uint32_t g_wdt1;       /* checkWatchdog return on call 2            */
static uint32_t g_w7fffc;     /* [0x7FFFC]                                 */
static uint32_t g_w7fff8;     /* [0x7FFF8]                                 */
static uint32_t g_alt1000;    /* [0x1000]                                  */
static uint32_t g_deref_addr; /* address of the **0x7FFFC deref target     */
static uint32_t g_deref_val;  /* value at that address                     */

static void map_page(uintptr_t addr)
{
    long page = sysconf(_SC_PAGESIZE);
    uintptr_t base = addr & ~((uintptr_t)page - 1);
    void *p = mmap((void *)base, (size_t)page, PROT_READ | PROT_WRITE,
                   MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED, -1, 0);
    if (p == MAP_FAILED) {
        perror("mmap");
        exit(1);
    }
}

/* Big-endian byte-wise accessors (the emulator and the mmap()ed host memory
 * both lay the MSB of every 16/32-bit word first). */
static void wr8(uintptr_t a, uint8_t v) { RX8_IO8(a) = v; }

static void wr32(uintptr_t a, uint32_t v)
{
    wr8(a, (uint8_t)(v >> 24));
    wr8(a + 1, (uint8_t)(v >> 16));
    wr8(a + 2, (uint8_t)(v >> 8));
    wr8(a + 3, (uint8_t)v);
}

static uint32_t rd32(uintptr_t a)
{
    return ((uint32_t)RX8_IO8(a) << 24) | ((uint32_t)RX8_IO8(a + 1) << 16)
         | ((uint32_t)RX8_IO8(a + 2) << 8) | (uint32_t)RX8_IO8(a + 3);
}

/* ------------------------------------------------------------------ */
/*  Stubbed callee layer — mirrors the RAM-overlay stubs in the        */
/*  harness (harness_reset_handler.py), byte-for-byte behaviourally.   */
/* ------------------------------------------------------------------ */
void rx_reset_watchdog(void)              { wr32(TRACE_BASE + 0x00, 0x00000572u); }
void rx_reset_hw_init_1(void)             { wr32(TRACE_BASE + 0x10, 0x00000170u); }
void rx_reset_hw_init_2(void)             { wr32(TRACE_BASE + 0x20, 0x0000041Cu); }
void rx_reset_hw_init_3(void)             { wr32(TRACE_BASE + 0x30, 0x000003D4u); }

int rx_reset_check_watchdog(void)
{
    uint32_t n = rd32(WDT_CNT) + 1u;
    wr32(WDT_CNT, n);
    wr32(TRACE_BASE + 0x40, 0x000005B0u); /* tag                            */
    wr32(TRACE_BASE + 0x44, n);           /* call count                     */
    if (n == 1u) return (int)g_wdt0;
    if (n == 2u) return (int)g_wdt1;
    return 0;
}

void rx_reset_warm(int cold_start)
{
    wr32(TRACE_BASE + 0x50, 0x000008F6u); /* tag                            */
    wr32(TRACE_BASE + 0x54, (uint32_t)cold_start); /* r4 = cold_start      */
}

uint32_t rx_reset_boot(uint32_t rv)
{
    wr32(TRACE_BASE + 0x60, 0x00000040u); /* tag                            */
    wr32(TRACE_BASE + 0x64, rv);          /* r4 = chosen reset vector       */
    return SENT;
}

/* ------------------------------------------------------------------ */
/*  Memory model for the below-mmap ROM-literal cells.                 */
/* ------------------------------------------------------------------ */
uint32_t rx_reset_read_wdt_status(void)     { return g_w7fffc; }
uint32_t rx_reset_read_wdt_status_alt(void) { return g_w7fff8; }
uint32_t rx_reset_read_alt_rv(void)         { return g_alt1000; }

uint32_t rx_reset_ram_read32(uint32_t addr)
{
    return (addr == g_deref_addr) ? g_deref_val : 0u;
}

int main(void)
{
    char line[256];

    /* Trace cells on the 0xFFFFE000 page; the counter / magic / reason cells
     * on the 0xFFFFD000 page. */
    map_page(TRACE_BASE);
    map_page(WDT_CNT);

    while (fgets(line, sizeof line, stdin)) {
        unsigned long cold, reason, magic, w7fffc, wderef, alt1000, w7fff8;
        unsigned long wdt0, wdt1;

        if (sscanf(line, "rh %lx %lx %lx %lx %lx %lx %lx %lx %lx",
                   &cold, &reason, &magic, &w7fffc, &wderef, &alt1000,
                   &w7fff8, &wdt0, &wdt1) != 9) {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }

        g_wdt0     = (uint32_t)wdt0;
        g_wdt1     = (uint32_t)wdt1;
        g_w7fffc   = (uint32_t)w7fffc;
        g_w7fff8   = (uint32_t)w7fff8;
        g_alt1000  = (uint32_t)alt1000;
        g_deref_addr = (uint32_t)w7fffc;   /* the ROM derefs exactly [0x7FFFC] */
        g_deref_val  = (uint32_t)wderef;

        /* Clear the trace cells and the state cells; seed the magic cell and
         * leave the reason byte clear (matches the emulator-side seeding). */
        for (uintptr_t a = TRACE_BASE; a < TRACE_BASE + 0x100u; a += 4) {
            wr32(a, 0);
        }
        wr32(WDT_CNT, 0);
        wr32(MAGIC_LOC, (uint32_t)magic);
        wr8(REASON_LOC, 0);

        /* Run the reconstructed handler on the host side. */
        uint32_t ret = rx_reset_handler((int)(uint32_t)cold, (uint8_t)reason);

        /* Observable post-state — 14 tokens, big-endian numeric values,
         * identical to what the emulator-side harness reads back. */
        printf("%08X %08X %08X %08X %08X %08X %08X %08X %08X %08X %08X %08X %08X %08X\n",
               ret,
               rd32(TRACE_BASE + 0x00), rd32(TRACE_BASE + 0x10),
               rd32(TRACE_BASE + 0x20), rd32(TRACE_BASE + 0x30),
               rd32(TRACE_BASE + 0x40), rd32(TRACE_BASE + 0x44),
               rd32(TRACE_BASE + 0x50), rd32(TRACE_BASE + 0x54),
               rd32(TRACE_BASE + 0x60), rd32(TRACE_BASE + 0x64),
               rd32(MAGIC_LOC), rd32(REASON_LOC), rd32(WDT_CNT));
    }
    return 0;
}

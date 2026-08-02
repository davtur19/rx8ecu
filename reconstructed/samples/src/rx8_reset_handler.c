/*
 * =============================================================================
 * rx8_reset_handler.c  —  RX-8 PCM RESET HANDLER @ ROM 0x4E0
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x4E0  (146 bytes: 0x4E0..0x56D, plus the 0x40 terminal
 *                trampoline vector_trampoline_set_sp)
 * Status      : VERIFIED — behavioural equivalence to the ROM held by
 *               reconstructed/samples/tests/harness_reset_handler.py
 *               (host-gcc vs tools/sh2emu.py over edge + random vectors;
 *               bit-exact return value, call-trace cells and RAM
 *               side-effects; 0 mismatches).
 * Lift (truth): c/reset_handler.c  (hand-annotated Ghidra RE by equinox311,
 *               program 60E1D400).
 *
 * WHAT THIS IS
 * ------------
 * The primary reset entry point of the RTOS application.  The boot ROM /
 * vector-table redirect ends here: Manual_Reset (0x8B8) finishes the basic
 * BSC + GPIO init and jumps to 0x4E0.  reset_handler then:
 *   1. resets the watchdog timer               (0x572);
 *   2. runs the three hardware-init leaves      (0x170 / 0x41C / 0x3D4);
 *   3. detects cold vs warm start from the r4 flag and the boot magic
 *      0x5AA5A55A stored at 0xFFFFDFFC;
 *   4. recovers from a watchdog-induced reset by reading the reset-vector
 *      cells 0x7FFFC / 0x7FFF8 / 0x1000 (retry loop over checkWatchdog @0x5B0
 *      until the vector chain yields a valid entry);
 *   5. stamps the boot magic, then tail-jumps through the 0x40 trampoline
 *      (vector_trampoline_set_sp: SP <- 0xFFFFDFA0, jmp @r4) with r4 = the
 *      chosen reset vector.
 *
 * CALLING CONVENTION
 * ------------------
 *   rx_reset_handler(cold_start in r4, reason in r5):
 *     cold_start == 0  -> cold path  (magic check + possible WDT recovery)
 *     cold_start != 0  -> warm path  (store reason, default vector 0x6C8)
 *     reason            -> reset reason byte (RSTSRC), stored as a BYTE to
 *                         0xFFFFDFA8 on the warm path only.
 *   The ROM never returns (0x40 trampoline + `bra $` at 0x56E).  Here the
 *   terminal leaf is modelled as a function returning the emulator SENT value
 *   so the harness can compare the emulator r0 bit-exactly.
 *
 * ROM BODY (disassembled 60E1D400.bin @ 0x4E0; word pool @ 0x586..0x5A8):
 *
 *     add #-8,r15 ; mov.l r4,@(4,r15) ; mov.b r5,@r15   ; save args
 *     bsr 0x572 / mov #1,r14           ; resetWatchdog ; recovered=1
 *     mov.w @(0x586),r2  ; jsr @r2     ; hw init 1  (0x0170)
 *     mov.w @(0x588),r3  ; jsr @r3     ; hw init 2  (0x041C)
 *     mov.w @(0x58A),r2  ; jsr @r2     ; hw init 3  (0x03D4)
 *     mov.l @(4,r15),r3 ; tst r3,r3 ; bf 0x556    ; cold_start != 0 -> warm
 *     mov.l @(0x59C),r3 ; mov.l @(0x5A0),r1       ; MAGIC / &magic
 *     mov.l @r1,r2 ; cmp/eq r3,r2 ; bt 0x51A      ; magic match -> skip WDT
 *     bsr 0x5B0 / mov #7,r4 ; mov r0,r4 ; tst r4,r4 ; checkWatchdog()
 *     bf 0x51A ; mov #0,r14 ; mov.w @(0x58C),r13   ; w!=0: keep recovered,
 *                                                  ; else rv=0x6C8 default
 *     0x51A: mov r14,r0 ; cmp/eq #1,r0 ; bf 0x562  ; recovered==1 ?
 *     mov.l @(0x5A4),r4 ; mov.w @(0x58E),r14       ; r4=&0x7FFFC, r14=0x1000
 *     mov.l @r4,r0 ; cmp/eq #-1,r0 ; bt 0x532      ; *0x7FFFC == -1?
 *     mov.l @r4,r0 ; mov.l @r0,r0 ; cmp/eq #-1,r0  ; deref; == -1?
 *     bf 0x546                                      ; no -> alt check 0x546
 *     0x532: bsr 0x5B0 / mov #7,r4 ; mov r0,r4 ; tst r4,r4
 *     bt 0x560 ; mov.l @r14,r0 ; cmp/eq #-1,r0 ; bt 0x532  ; retry loop:
 *          wdt==0 -> rv=0x6C8 (0x560) ; *0x1000 != -1 -> rv=*0x1000
 *     bra 0x54C / mov.l @r14,r13
 *     0x546: mov.l @r14,r0 ; cmp/eq #-1,r0 ; bt 0x550
 *     bra 0x562 / mov.l @r14,r13                   ; rv = *0x1000
 *     0x550: mov.l @(0x5A8),r2 ; bra 0x562 / mov.l @r2,r13  ; rv = *0x7FFF8
 *     0x556 (warm): mov.b @r15,r1 ; mov.w @(0x590),r3 ; mov.w @(0x592),r2
 *     jsr @r2 / mov.b r1,@r3                        ; *0xFFFFDFA8 = reason
 *     0x560: mov.w @(0x58C),r13                     ; rv = 0x6C8
 *     0x562: mov.l @(0x59C),r3 ; mov.l @(0x5A0),r2 ; mov.l r3,@r2
 *                                                  ; *0xFFFFDFFC = MAGIC
 *     mov.w @(0x594),r3 ; jsr @r3 / mov r13,r4     ; trampoline(r4=rv)
 *     bra 0x56E                                    ; infinite loop (safety)
 *
 * LIFT-VS-ROM DISCREPANCIES FIXED (documented from the ROM bytes)
 * --------------------------------------------------------------
 *  1. RECOVER-LOOP CONDITION POLARITY.  c/reset_handler.c decodes the retry
 *     loop as `while(1){ w=checkWatchdog(); if (w!=0) break; alt=*0x1000;
 *     if (alt!=-1){rv=alt;break;} }` — a NON-zero result ends the loop.  The
 *     ROM bytes @0x538/0x53A do the OPPOSITE: `tst r4,r4 / bt 0x560` — a ZERO
 *     checkWatchdog result jumps straight to the DEFAULT vector (0x560).  This
 *     model keeps the ROM polarity: on w == 0 the reset vector is the default
 *     0x6C8; on w != 0 the alternate cell 0x1000 is consulted, and the loop
 *     repeats only while *0x1000 == 0xFFFFFFFF.
 *  2. REASON-STORE PLACEMENT.  The lift stores the reason byte in the
 *     `recovered == 0` branch; the ROM stores it only in the WARM-START path
 *     (0x556..0x55E, reached from `bf 0x556` when cold_start != 0).  A cold
 *     start with magic mismatch and checkWatchdog()==0 clears r14 (recovered)
 *     but does NOT store the reason byte.  This model follows the ROM bytes.
 *  3. SIGNATURE.  The lift is `noreturn void`; the 0x40 terminal leaf here
 *     returns the emulator SENT value so the harness can compare r0.
 *
 * MEMORY MODEL / STUBBED CALLEE LAYER
 * -----------------------------------
 * The deep leaves (0x572, 0x170, 0x41C, 0x3D4, 0x5B0, 0x8F6, 0x40) are not the
 * function under contract; the harness installs tiny behaviour-identical
 * RAM-overlay stubs in their place on BOTH sides (same convention as the
 * dispatcher stub in harness_os_task_scheduler.py).  They emit a structured
 * call-trace into the RX8_RESET_TRACE_BASE cells:
 *     [0xFFFFE000]=0x572  [0xFFFFE010]=0x170  [0xFFFFE020]=0x41C
 *     [0xFFFFE030]=0x3D4  [0xFFFFE040]=0x5B0  [0xFFFFE044]=<call count>
 *     [0xFFFFE050]=0x8F6  [0xFFFFE054]=<cold_start>  [0xFFFFE060]=0x40
 *     [0xFFFFE064]=<reset vector>
 * Only the wdt leaf @0x5B0 is stateful: it increments the counter cell
 * 0xFFFFD100 and returns the seeded two-step sequence (wdt0 on call 1, wdt1 on
 * call 2, 0 afterwards).  That behaviour is mirrored by rx_reset_check_watchdog().
 * The cells the ROM touches that lie BELOW mmap_min_addr ([0x7FFFC],
 * [0x7FFF8], [0x1000]) and the sparse `**(0x7FFFC)` dereference are modelled
 * as harness-provided accessors (defined in tests/oracle_reset_handler.c) —
 * the same module-state convention rx8_set_sr.c uses for SR.  The real RAM
 * cells at 0xFFFFDFFC / 0xFFFFDFA8 and the trace cells are mmap()ed memory in
 * the host rig, read/written here through byte-wise big-endian helpers.
 * =============================================================================
 */
#include <stdint.h>
#include "rx8_hw.h"

/* ------------------------------------------------------------------ */
/*  ROM constants resolved from the word/longword pool @0x586..0x5A8   */
/* ------------------------------------------------------------------ */
#define RX_RESET_MAGIC          0x5AA5A55Au
#define RX_RESET_MAGIC_LOC      0xFFFFDFFCu
#define RX_RESET_REASON_LOC     0xFFFFDFA8u
#define RX_RESET_DEFAULT_RV     0x000006C8u
#define RX_RESET_ALT_OFFSET     0x00001000u
#define RX_RESET_WDT_STATUS     0x0007FFFCu
#define RX_RESET_WDT_STATUS_ALT 0x0007FFF8u
#define RX_RESET_SENT           0xEEEE0000u   /* emulator terminal constant */

/* ------------------------------------------------------------------ */
/*  Harness-provided callee / memory layer                             */
/*  (implemented in tests/oracle_reset_handler.c — see file header)    */
/* ------------------------------------------------------------------ */
void     rx_reset_watchdog(void);         /* 0x572   trace cell 0        */
void     rx_reset_hw_init_1(void);        /* 0x170   trace cell 1        */
void     rx_reset_hw_init_2(void);        /* 0x41C   trace cell 2        */
void     rx_reset_hw_init_3(void);        /* 0x3D4   trace cell 3        */
int      rx_reset_check_watchdog(void);   /* 0x5B0   stateful leaf       */
void     rx_reset_warm(int cold_start);   /* 0x8F6   trace cell 5        */
uint32_t rx_reset_boot(uint32_t rv);      /* 0x40    terminal trampoline */
uint32_t rx_reset_read_wdt_status(void);      /* [0x7FFFC]              */
uint32_t rx_reset_read_wdt_status_alt(void);  /* [0x7FFF8]              */
uint32_t rx_reset_read_alt_rv(void);          /* [0x1000]               */
uint32_t rx_reset_ram_read32(uint32_t addr);  /* sparse read for the
                                                 **0x7FFFC dereference   */

/* ------------------------------------------------------------------ */
/*  Big-endian byte-wise accessors for the real RAM cells (the emulator */
/*  and the mmap()ed host memory both lay the MSB first).              */
/* ------------------------------------------------------------------ */
static uint32_t rx_reset_rd32(uintptr_t a)
{
    return ((uint32_t)RX8_IO8(a) << 24) | ((uint32_t)RX8_IO8(a + 1) << 16)
         | ((uint32_t)RX8_IO8(a + 2) << 8) | (uint32_t)RX8_IO8(a + 3);
}

static void rx_reset_wr32(uintptr_t a, uint32_t v)
{
    RX8_IO8(a)     = (uint8_t)(v >> 24);
    RX8_IO8(a + 1) = (uint8_t)(v >> 16);
    RX8_IO8(a + 2) = (uint8_t)(v >> 8);
    RX8_IO8(a + 3) = (uint8_t)v;
}

static void rx_reset_wr8(uintptr_t a, uint8_t v)
{
    RX8_IO8(a) = v;
}

/* ------------------------------------------------------------------ */
/*  0x532..0x544 — checkWatchdog retry loop.                           */
/*  ROM polarity (see discrepancy 1): a ZERO checkWatchdog result       */
/*  selects the DEFAULT reset vector; otherwise the alternate cell      */
/*  0x1000 is consulted and the loop repeats only while it is -1.       */
/* ------------------------------------------------------------------ */
static uint32_t rx_reset_recover_loop(void)
{
    for (;;) {
        if (rx_reset_check_watchdog() == 0) {     /* 0x538/0x53A bt 0x560 */
            return RX_RESET_DEFAULT_RV;
        }
        if (rx_reset_read_alt_rv() != 0xFFFFFFFFu) {  /* 0x53C..0x544   */
            return rx_reset_read_alt_rv();
        }
    }
}

/* ------------------------------------------------------------------ */
/*  reset_handler @ 0x4E0                                              */
/* ------------------------------------------------------------------ */
uint32_t rx_reset_handler(int cold_start, uint8_t reason)
{
    uint32_t rv;
    int recovered = 1;                        /* r14 = 1 (0x4E8 delay slot) */

    rx_reset_watchdog();                      /* bsr 0x572                  */
    rx_reset_hw_init_1();                     /* jsr 0x170                  */
    rx_reset_hw_init_2();                     /* jsr 0x41C                  */
    rx_reset_hw_init_3();                     /* jsr 0x3D4                  */

    if (cold_start == 0) {
        /* ---------------- cold path ---------------- */
        if (rx_reset_rd32(RX_RESET_MAGIC_LOC) != RX_RESET_MAGIC) {
            /* magic mismatch (0x50C): was it a watchdog reset? */
            if (rx_reset_check_watchdog() == 0) {
                recovered = 0;                /* 0x516  r14 = 0             */
            }
        }
        if (recovered == 1) {
            /* 0x520..0x530 — WDT status cell read + deref. */
            uint32_t val = rx_reset_read_wdt_status();
            if (val == 0xFFFFFFFFu) {
                rv = rx_reset_recover_loop();         /* bt 0x532          */
            } else {
                val = rx_reset_read_wdt_status();     /* 0x52A reload      */
                val = rx_reset_ram_read32(val);       /* 0x52C **0x7FFFC   */
                if (val == 0xFFFFFFFFu) {
                    rv = rx_reset_recover_loop();     /* fall to 0x532     */
                } else {
                    /* 0x546..0x554 — alternate cell, else 0x7FFF8. */
                    rv = rx_reset_read_alt_rv();
                    if (rv == 0xFFFFFFFFu) {
                        rv = rx_reset_read_wdt_status_alt();
                    }
                }
            }
        } else {
            /* genuine cold start (magic missing, wdt not to blame). */
            rv = RX_RESET_DEFAULT_RV;         /* 0x518                     */
        }
    } else {
        /* ---------------- warm path (bf 0x556) ---------------- */
        rx_reset_wr8(RX_RESET_REASON_LOC, reason);   /* 0x55E delay slot  */
        rx_reset_warm(cold_start);                    /* jsr 0x8F6         */
        rv = RX_RESET_DEFAULT_RV;                     /* 0x560             */
    }

    /* 0x562..0x566 — stamp the boot magic. */
    rx_reset_wr32(RX_RESET_MAGIC_LOC, RX_RESET_MAGIC);

    /* 0x568..0x56C — tail-jump through the 0x40 trampoline with the chosen
     * reset vector in r4 (a FULL 32-bit mov.l value — the alt paths load r13
     * with mov.l @Rn,Rn; only the default 0x6C8 comes from a sign-extended
     * mov.w).  Returns the emulator SENT constant so the harness can compare
     * r0 bit-exactly. */
    return rx_reset_boot(rv);
}

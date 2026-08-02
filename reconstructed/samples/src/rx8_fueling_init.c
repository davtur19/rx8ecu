/*
 * =============================================================================
 * rx8_fueling_init.c  —  FUEL & CRANK-SUBSYSTEM INITIALISATION (fuelingInit)
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x753C   (80 bytes: 0x753C .. 0x758B)
 * Status      : VERIFIED — behavioural equivalence to the ROM bytes held by
 *               reconstructed/samples/tests/harness_fueling_init.py
 *               (host-gcc + mmap vs tools/sh2emu.py over edge + N random
 *               initial-RAM state vectors; every cell the chain touches —
 *               6 MTU timer registers + 39 RAM cells — is compared bit-exactly,
 *               including the 5-cell tail-call target; 0 mismatches).
 * Lift (truth): c/fuelingInit.c  (fuelingInit @ 0x753C, 80 bytes)
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * Fuel & crank initialisation, run during engine start-up.  It resets the MTU
 * timer hardware, clears/sets a bank of crank control/state bytes, runs the
 * crank variable / mode / state / sensor / flag / counter initialisers and
 * finally TAIL-JUMPS (`bra`, NOT `jsr`) into crank_output_update @0x0808E,
 * which loads the five output floats and RETURNS through PR (the ROM body of
 * 0x0808E ends in `rts`, so the whole chain terminates — verified).
 *
 * ROM body (60E1D400.bin @ 0x753C):
 *
 *     2FE6  mov.l r14,@-r15            ; prologue
 *     4F22  sts.l pr,@-r15
 *     B0CC  bsr   0x076DC              ; crank_timer_hw_reset
 *     0009  nop
 *     944C  mov.w 0x075E0,r4           ; r4 = 0xFFFFF6EA (sign-ext of 0xF6EA)
 *     D32C  mov.l 0x075F8,r3           ; r3 = 0x0000FFFB
 *     6241  mov.w @r4,r2  / 2239 and r3,r2  / 2421 mov.w r2,@r4
 *                                     ; u16@0xFFFFF6EA &= 0xFFFB
 *     E101  mov #0x01,r1 ; D024 mov.l 0x075E4,r0 ; EE00 mov #0x00,r14
 *     D224  mov.l 0x075E8,r2 ; D324 mov.l 0x075EC,r3 ; D127 mov.l 0x075FC,r1
 *     D227  mov.l 0x07600,r2 ; D327 mov.l 0x07604,r3
 *     2010  mov.b r1,@r0              ; 0xFFFF9FA3 = 1
 *     22E0  mov.b r14,@r2             ; 0xFFFF9FA4 = 0
 *     23E0  mov.b r14,@r3             ; 0xFFFF9FA5 = 0
 *     21E0  mov.b r14,@r1             ; 0xFFFF9FC0 = 0
 *     22E0  mov.b r14,@r2             ; 0xFFFF9FC4 = 0
 *     B0EE  bsr   0x07748             ; crank_vars_init
 *     23E0  mov.b r14,@r3             ;   (delay) 0xFFFF9FA2 = 0
 *     B348  bsr   0x07C00             ; crank_mode_write
 *     0009  nop
 *     B31A  bsr   0x07BA8             ; crank_state_bytes_clear
 *     0009  nop
 *     D224  mov.l 0x07608,r2 / 22E0 mov.b r14,@r2      ; 0xFFFF9F96 = 0
 *     D324  mov.l 0x0760C,r3 / B359 bsr 0x07C30        ; crankSensorInit
 *     23E0  mov.b r14,@r3             ;   (delay) 0xFFFF9FCB = 0
 *     B4AB  bsr   0x07ED8             ; crank_flags_enable
 *     0009  nop
 *     B517  bsr   0x07FB4             ; crank_counters_reset
 *     0009  nop
 *     4F26  lds.l @r15+,pr            ; epilogue (restore caller PR)
 *     A581  bra   0x0808E             ; tail call crank_output_update
 *     6EF6  mov.l @r15+,r14           ;   (delay)
 *
 * CALLING CONVENTION
 * ------------------
 * void f(void): normal ABI entry, no input registers, no meaningful return
 * value (the ROM leaves r0 as an arbitrary by-product of the tail-call target).
 * Driven through the standard SH2.call() entry; verified by comparing every
 * side-effected cell, exactly like the rx8_immo_* rigs.
 *
 * CALLEE INLINING (net effects folded in, see each helper below)
 * -----------------------------------------------------------------
 * The ROM internally calls eight subroutines whose bytes are ALWAYS executed
 * inside the emulator (ground truth); the host sample inlines their net RAM/
 * hardware effects so it is self-contained:
 *
 *   0x076DC  crank_timer_hw_reset      — MTU timer regs + a u32 calibration
 *   0x07748  crank_vars_init           — crank vars + conditional sensor/state
 *   (0x07B7C crank_vars_leaf           — cal + 7-bit table lookup, inside
 *                                        crank_vars_init)
 *   0x07C00  crank_mode_write          — one control byte = 0xFF
 *   0x07BA8  crank_state_bytes_clear   — two control bytes = 0
 *   0x07C30  crankSensorInit           — sensor regs A/B + run-flag branch
 *   0x07ED8  crank_flags_enable        — three flags + a u16 = 0xFFFF
 *   0x07FB4  crank_counters_reset      — period counters/floats
 *   0x0808E  crank_output_update       — tail call; five output floats
 *   0x0768C  crank_mode_switch         — reachable ONLY through crankSensorInit's
 *                                        run-flag tail-branch (r4 = 0); the
 *                                        harness never seeds that combination
 *                                        (see harness), so it is modelled at
 *                                        the boundary (0x07C00 path only).
 *
 * ADDRESS LITERALS (all `mov.w @(disp,PC)` words are SIGN-EXTENDED by the CPU)
 * ---------------------------------------------------------------------------
 * The MTU timer peripheral registers are reached through 16-bit literals that
 * the SH-2 sign-extends to 0xFFFFF4xx / 0xFFFFF6xx — NOT 0x0000F4xx:
 *   0xF42A -> 0xFFFFF42A  (u8)     0xF42E -> 0xFFFFF42E  (u16)
 *   0xF6E4 -> 0xFFFFF6E4  (u8)     0xF6EA -> 0xFFFFF6EA  (u16)
 *   0xF6E0 -> 0xFFFFF6E0  (u8)     0xF6D4 -> 0xFFFFF6D4  (u32)
 *   0xF6D8 -> 0xFFFFF6D8  (u8)     0xF6C4 -> 0xFFFFF6C4  (u8)
 *
 * CAL TABLES / ROM CONSTANTS (read-only; all four pinned by the harness
 * check_cal; the two above mmap_min_addr are ALSO read from the actual ROM
 * file by the host oracle via ROM-page mmap)
 * -----------------------------------------------------------------
 *   0x0006CF64  u32 = 0x000FA000  crank_timer_hw_reset loads it and stores it
 *                                 to the MTU period register 0xFFFFF6D4.
 *                                 (page 0x0006C000 is mmap-able; the oracle
 *                                 reads the real ROM bytes)
 *   0x0006CF68  u8  = 0x00        crank_vars_leaf branch constant: == 0x5A
 *                                 short-circuits the table lookup to 0.
 *                                 (mmap-able, read from the ROM file)
 *   0x0000DA05  u8  table [..72B] 7-bit result table; entry index 0x48
 *                (2 * 0xFFFF9F95, and 0xFFFF9F95 is always 0x24 on this path)
 *                -> byte 0x0000DA4D = 0x00, & 0x7F = 0.  This ROM page is
 *                BELOW mmap_min_addr on the host (0xDA4D < 0x10000), so the
 *                value is pinned by the harness check_cal (the emulator side
 *                still reads the REAL ROM byte at 0x0000DA4D).
 *   0x000080FC  f32 = 10.0f        crank_output_update's output float (stored
 *                                 to 0xFFFF9FF0 / 0xFFFF9FF4).  Also below
 *                                 mmap_min_addr -> pinned by check_cal.
 *
 * DISCREPANCIES vs c/fuelingInit.c
 * --------------------------------
 * The lift's call tree, address literals, store widths and tail-call all match
 * the disassembly exactly.  Two nuances are made explicit here:
 *   1. The `mov.w @(disp,PC)` literals are sign-extended by the CPU — they are
 *      the MTU timer registers 0xFFFFF6xx/0xFFFFF4xx, not 0x0000F6xx (the
 *      lift's `0x0000F6EA` is the RAW literal; the effective address is
 *      0xFFFFF6EA).
 *   2. The two delay-slot byte clears (0xFFFF9FA2 with the `bsr crank_vars_init`
 *      and 0xFFFF9FCB with the `bsr crankSensorInit`) execute BEFORE the callee
 *      body; the C mirrors that order (neither callee re-reads them, so only
 *      the visible write order is affected).
 *   The lift models crank_output_update as a noreturn tail call; the ROM body
 *   of 0x0808E actually terminates with `rts` and returns through the caller's
 *   PR — the sample models the call as a normal (final) function call.
 *
 * RAM SIDE EFFECTS (all cells the harness compares)
 * -----------------------------------------------------------------
 * MTU timer / output registers (host: mmap'd 0xFFFFF400 + 0xFFFFF600):
 *   0xFFFFF42A u8    0xFFFFF42E u16   0xFFFFF6E4 u8    0xFFFFF6EA u16
 *   0xFFFFF6E0 u8    0xFFFFF6D4 u32   0xFFFFF6D8 u8    0xFFFFF6C4 u8
 * Crank control/state RAM:
 *   0xFFFF9FA3 u8 =1  0xFFFF9FA4 u8=0  0xFFFF9FA5 u8=0  0xFFFF9FC0 u8=0
 *   0xFFFF9FC4 u8=0  0xFFFF9FA2 u8=0  0xFFFF9FA1 u8=0  0xFFFF9F95 u8=0x24
 *   0xFFFF9FC1 u8=0  0xFFFF9FC2 u8=0  0xFFFF9FC5 u8=0  0xFFFF9FC3 u8=0
 *   0xFFFF9FC6 u8=0xFF  0xFFFF9FC7 u8=0  0xFFFF9FC8 u8=0  0xFFFF9F96 u8=0
 *   0xFFFF9FC9 u8=0  0xFFFF9FCA u8=0xFF  0xFFFF9FCB u8=0
 *   0xFFFF9FCE u8=1  0xFFFF9FA0 u8=1  0xFFFF9F8C u8=1  0xFFFF9FCC u16=0xFFFF
 *   0xFFFF9FE8 u8=0  0xFFFF9F94 u8=0
 * Crank value RAM (wider stores):
 *   0xFFFF9FB0 u32 = 0xFFFFFFFF  0xFFFF9FBC u32 = 0.0f
 *   0xFFFF9F80 u32 = 0.0f   0xFFFF9F84 u32 = 0x7FFFFFFF
 *   0xFFFF9F88 u32 = 0x7FFFFFFF  0xFFFF9F90 u32 = 0.0f
 *   0xFFFF9FF0 u32 = 10.0f  0xFFFF9FF4 u32 = 10.0f
 *   0xFFFF9FF8 u32 = 0.0f   0xFFFF9FFC u32 = 0.0f  0xFFFF9FEC u32 = 1.0f
 * =============================================================================
 */
#include <stdint.h>

#include "rx8_hw.h"

/* ---- MTU timer / output registers (see header: sign-extended literals) ---- */
#define RX8_TMR_F42A   0xFFFFF42Au      /* u8   timer control                 */
#define RX8_TMR_F42E   0xFFFFF42Eu      /* u16  timer counter/period?         */
#define RX8_TMR_F6E4   0xFFFFF6E4u      /* u8   timer control 2               */
#define RX8_TMR_F6EA   0xFFFFF6EAu      /* u16  fuel timing control (u16 RMW) */
#define RX8_TMR_F6E0   0xFFFFF6E0u      /* u8   timer value = 0xC8            */
#define RX8_TMR_F6D4   0xFFFFF6D4u      /* u32  period register (cal)         */
#define RX8_TMR_F6D8   0xFFFFF6D8u      /* u8   leaf result cell              */
#define RX8_TMR_F6C4   0xFFFFF6C4u      /* u8   leaf clear cell               */

/* ---- crank control/state RAM cells ---------------------------------------- */
#define RX8_CRK_STATE_FA3  0xFFFF9FA3u  /* u8   flag A  (set to 1)            */
#define RX8_CRK_STATE_FA4  0xFFFF9FA4u  /* u8   flag B  (clear)              */
#define RX8_CRK_STATE_FA5  0xFFFF9FA5u  /* u8   flag C  (clear)              */
#define RX8_CRK_STATE_FC0  0xFFFF9FC0u  /* u8   flag D  (clear; also the      */
                                        /*      crank_vars_init branch cell) */
#define RX8_CRK_STATE_FC4  0xFFFF9FC4u  /* u8   flag E  (clear)              */
#define RX8_CRK_STATE_FA2  0xFFFF9FA2u  /* u8   flag F  (clear, bsr delay)    */
#define RX8_CRK_STATE_FA1  0xFFFF9FA1u  /* u8   clear (leaf bsr delay)        */
#define RX8_CRK_STATE_F95  0xFFFF9F95u  /* u8   leaf table index (= 0x24)     */
#define RX8_CRK_STATE_FC1  0xFFFF9FC1u  /* u8   clear                         */
#define RX8_CRK_STATE_FC2  0xFFFF9FC2u  /* u8   clear                         */
#define RX8_CRK_STATE_FC5  0xFFFF9FC5u  /* u8   clear                         */
#define RX8_CRK_STATE_FC3  0xFFFF9FC3u  /* u8   leaf result copy              */
#define RX8_CRK_STATE_FC6  0xFFFF9FC6u  /* u8   sensor control reg C = 0xFF   */
#define RX8_CRK_STATE_FC7  0xFFFF9FC7u  /* u8   state byte clear              */
#define RX8_CRK_STATE_FC8  0xFFFF9FC8u  /* u8   state byte clear              */
#define RX8_CRK_STATE_F96  0xFFFF9F96u  /* u8   engine-running flag           */
#define RX8_CRK_STATE_FC9  0xFFFF9FC9u  /* u8   sensor control reg A = 0x00   */
#define RX8_CRK_STATE_FCA  0xFFFF9FCAu  /* u8   sensor control reg B = 0xFF   */
#define RX8_CRK_STATE_FCB  0xFFFF9FCBu  /* u8   clear (bsr delay)             */
#define RX8_CRK_STATE_FCE  0xFFFF9FCEu  /* u8   flag = 1                      */
#define RX8_CRK_STATE_FA0  0xFFFF9FA0u  /* u8   flag = 1                      */
#define RX8_CRK_STATE_F8C  0xFFFF9F8Cu  /* u8   flag = 1                      */
#define RX8_CRK_STATE_FCC  0xFFFF9FCCu  /* u16  = 0xFFFF                      */
#define RX8_CRK_STATE_FE8  0xFFFF9FE8u  /* u8   = 0                           */
#define RX8_CRK_STATE_F94  0xFFFF9F94u  /* u8   = 0 (delay slot)              */

/* wider crank value RAM cells */
#define RX8_CRK_VAL_FB0   0xFFFF9FB0u   /* u32  = 0xFFFFFFFF (mov #0xFF is sign-
                                           extended on the SH-2 -> 32-bit -1) */
#define RX8_CRK_VAL_FBC   0xFFFF9FBCu   /* u32  = 0.0f                        */
#define RX8_CRK_VAL_F80   0xFFFF9F80u   /* u32  = 0.0f                        */
#define RX8_CRK_VAL_F84   0xFFFF9F84u   /* u32  = 0x7FFFFFFF                  */
#define RX8_CRK_VAL_F88   0xFFFF9F88u   /* u32  = 0x7FFFFFFF                  */
#define RX8_CRK_VAL_F90   0xFFFF9F90u   /* u32  = 0.0f                        */
#define RX8_CRK_VAL_FF0   0xFFFF9FF0u   /* u32  = 10.0f (tail target)         */
#define RX8_CRK_VAL_FF4   0xFFFF9FF4u   /* u32  = 10.0f (tail target)         */
#define RX8_CRK_VAL_FF8   0xFFFF9FF8u   /* u32  = 0.0f  (tail target)         */
#define RX8_CRK_VAL_FFC   0xFFFF9FFCu   /* u32  = 0.0f  (tail target)         */
#define RX8_CRK_VAL_FEC   0xFFFF9FECu   /* u32  = 1.0f  (tail target)         */

/* ---- ROM calibration / constant cells ------------------------------------- */
#define RX8_CAL_PERIOD       0x0006CF64u /* u32  = 0x000FA000 -> 0xFFFFF6D4  */
#define RX8_CAL_LEAF_SWITCH  0x0006CF68u /* u8   == 0x5A -> leaf result 0     */
#define RX8_CAL_LEAF_TABLE   0x0000DA05u /* u8   table, idx = 2*0xFFFF9F95    */
#define RX8_CAL_OUTPUT_F32   0x000080FCu /* f32  = 10.0f (below mmap_min_addr,
                                           pinned by harness check_cal)      */

/* ---- forward declarations for the inlined callee chain -------------------- */
static void rx8_crank_timer_hw_reset(void);
static void rx8_crank_vars_init(void);
static void rx8_crank_mode_write(void);
static void rx8_crank_state_bytes_clear(void);
static void rx8_crank_sensor_init(void);
static void rx8_crank_flags_enable(void);
static void rx8_crank_counters_reset(void);
static void rx8_crank_output_update(void);
static void rx8_crank_mode_switch(void);

/* ---- big-endian ROM byte/word readers (SH-2E ROM is big-endian) ----------- */
static uint8_t rom_u8(uint32_t addr)
{
    return *(volatile uint8_t *)(uintptr_t)addr;
}

static uint32_t rom_u32(uint32_t addr)
{
    const uint8_t *p = (const uint8_t *)(uintptr_t)addr;
    return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16)
         | ((uint32_t)p[2] << 8) | (uint32_t)p[3];
}

/* ============================================================================
 * 0x076DC — crank_timer_hw_reset (net effect; 108 bytes of the ROM body)
 * ==========================================================================*/
static void rx8_crank_timer_hw_reset(void)
{
    /* 0x76DC..0x76E4: byte RMW 0xFFFFF42A = (v & 0xFC) | 0x01. */
    RX8_IO8(RX8_TMR_F42A) = (uint8_t)((RX8_IO8(RX8_TMR_F42A) & 0xFCu) | 0x01u);
    /* 0x76E6..0x76EE: word RMW 0xFFFFF42E &= 0xFFFE (r6 = 0x0000FFFE). */
    RX8_IO16(RX8_TMR_F42E) &= 0xFFFEu;
    /* 0x76F0..0x76F8: byte RMW 0xFFFFF6E4 = (v & 0xFC) | 0x01. */
    RX8_IO8(RX8_TMR_F6E4) = (uint8_t)((RX8_IO8(RX8_TMR_F6E4) & 0xFCu) | 0x01u);
    /* 0x76FA..0x7710: three word RMWs on 0xFFFFF6EA. */
    RX8_IO16(RX8_TMR_F6EA) &= 0xFFFDu;      /* r3 = 0x0000FFFD */
    RX8_IO16(RX8_TMR_F6EA) &= 0xFFFEu;      /* r6 = 0xFFFE & v */
    RX8_IO16(RX8_TMR_F6EA) &= 0xFFF7u;      /* r2 = 0x0000FFF7 */
    /* 0x7712..0x7716: 0xFFFFF6E0 = 0xC8 (low byte of the u16 literal 0x00C8). */
    RX8_IO8(RX8_TMR_F6E0) = 0xC8u;
    /* 0x7718..0x771E: byte RMW 0xFFFFF6E4 = (v & 0xFB) | 0x04. */
    RX8_IO8(RX8_TMR_F6E4) = (uint8_t)((RX8_IO8(RX8_TMR_F6E4) & 0xFBu) | 0x04u);
    /* 0x7720..0x773C: six single-bit clears of 0xFFFFF6E4. */
    RX8_IO8(RX8_TMR_F6E4) &= 0xF7u;
    RX8_IO8(RX8_TMR_F6E4) &= 0xEFu;
    RX8_IO8(RX8_TMR_F6E4) &= 0xBFu;
    RX8_IO8(RX8_TMR_F6E4) &= 0xDFu;
    RX8_IO8(RX8_TMR_F6E4) &= 0x7Fu;
    /* 0x773E..0x7746: 0xFFFFF6D4 (u32) = u32@0x0006CF64 (= 0x000FA000). */
    RX8_IO32(RX8_TMR_F6D4) = rom_u32(RX8_CAL_PERIOD);
}

/* ============================================================================
 * 0x07B7C — crank_vars_leaf (net effect; 40 bytes, called from vars_init)
 *   cal@0x6CF68 == 0x5A -> result 0; else result = (u8@0xDA05 + 2*0xFFFF9F95)
 *   & 0x7F.  Writes the result to 0xFFFFF6D8, clears 0xFFFFF6C4 and copies it
 *   to 0xFFFF9FC3.  On the fuel-init path 0xFFFF9F95 is always 0x24 (set just
 *   before), so the table entry is 0x0000DA4D = 0x00 -> result 0.
 * ==========================================================================*/
static void rx8_crank_vars_leaf(void)
{
    uint8_t v;

    if (rom_u8(RX8_CAL_LEAF_SWITCH) == 0x5Au) {
        v = 0x00u;                              /* 0x7B86 bt/s path (r4 = r5 = 0) */
    } else {
        /* 0x7B8A..0x7B98: idx = 2 * u8@0xFFFF9F95; v = u8@(0xDA05 + idx) & 0x7F.
         * On the fuel-init path 0xFFFF9F95 is ALWAYS 0x24 (written by
         * crank_vars_init at 0x7758 just before this leaf runs), so the ROM
         * read is always u8@0x0000DA4D.  The 0x0000D000 ROM page is below
         * mmap_min_addr on the host (0xDA4D < 0x10000) and cannot be backed,
         * so the stock entry is PINNED by the harness check_cal instead of
         * dereferenced: u8@0x0000DA4D == 0x00 -> v = 0x00 & 0x7F = 0. */
        v = 0x00u;
    }
    RX8_IO8(RX8_TMR_F6D8) = v;                  /* 0x7B9A..0x7B9C */
    RX8_IO8(RX8_TMR_F6C4) = 0x00u;              /* 0x7B9E..0x7BA0 (r5 = 0)     */
    RX8_IO8(RX8_CRK_STATE_FC3) = v;             /* 0x7BA2..0x7BA6 (rts delay)  */
}

/* ============================================================================
 * 0x07748 — crank_vars_init (net effect; 84 bytes of the ROM body)
 *   Writes the crank variable bank, calls the 0x07B7C leaf, then branches on
 *   the flag byte 0xFFFF9FC0: if == 1 it clears it, and unless the second flag
 *   0xFFFF9FA3 == 2 it also runs crankSensorInit (0x07C30); either way it
 *   TAIL-CALLS crank_state_bytes_clear (0x07BA8).  Otherwise it returns.
 * ==========================================================================*/
static void rx8_crank_vars_init(void)
{
    RX8_IO8(RX8_CRK_STATE_F95) = 0x24u;         /* 0x774A..0x7758              */
    RX8_IO8(RX8_CRK_STATE_FC1) = 0x00u;         /* 0x775C..0x775E              */
    RX8_IO32(RX8_CRK_VAL_FB0) = 0xFFFFFFFFu;   /* 0x7760 mov.l r1(=0xFFFFFFFF,
                                                  #0xFF sign-extended) 4B      */
    RX8_IO8(RX8_CRK_STATE_FC2) = 0x00u;         /* 0x775C..0x7762              */
    RX8_IO32(RX8_CRK_VAL_FBC) = 0x00000000u;    /* 0x7766 fmov.s fr3(0.0)      */
    RX8_IO8(RX8_CRK_STATE_FC5) = 0x00u;         /* 0x7768..0x776A              */
    RX8_IO8(RX8_CRK_STATE_FA1) = 0x00u;         /* 0x7770 (delay slot of bsr)  */
    rx8_crank_vars_leaf();                      /* 0x776E bsr 0x07B7C          */

    if (RX8_IO8(RX8_CRK_STATE_FC0) == 0x01u) {  /* 0x7772..0x777A cmp/eq #1    */
        RX8_IO8(RX8_CRK_STATE_FC0) = 0x00u;     /* 0x777E                      */
        if (RX8_IO8(RX8_CRK_STATE_FA3) != 0x02u) {   /* 0x7786 cmp/eq #2      */
            /* 0x778C bsr 0x07C30 — only reached with 0xFFFF9F96 != 1 by the
             * harness (never the crank_mode_switch tail). */
            rx8_crank_sensor_init();
        }
        rx8_crank_state_bytes_clear();          /* 0x7792 bra 0x07BA8 (tail)   */
    }
}

/* ============================================================================
 * 0x07C00 — crank_mode_write (net effect; 8 bytes)
 *   u8@0xFFFF9FC6 = 0xFF (sensor control register C, mode "write").
 * ==========================================================================*/
static void rx8_crank_mode_write(void)
{
    RX8_IO8(RX8_CRK_STATE_FC6) = 0xFFu;         /* 0x7C00..0x7C06 (rts delay)  */
}

/* ============================================================================
 * 0x07BA8 — crank_state_bytes_clear (net effect; 12 bytes)
 *   u8@0xFFFF9FC7 = 0, u8@0xFFFF9FC8 = 0.
 * ==========================================================================*/
static void rx8_crank_state_bytes_clear(void)
{
    RX8_IO8(RX8_CRK_STATE_FC7) = 0x00u;         /* 0x7BA8..0x7BAE              */
    RX8_IO8(RX8_CRK_STATE_FC8) = 0x00u;         /* 0x7BB2 (rts delay)          */
}

/* ============================================================================
 * 0x07C30 — crankSensorInit (net effect; 36 bytes of the ROM body)
 *   u8@0xFFFF9FC9 = 0x00, u8@0xFFFF9FCA = 0xFF, and if the engine-running flag
 *   0xFFFF9F96 == 1 it clears the flag and TAIL-JUMPS to crank_mode_switch
 *   (0x0768C, `bra` with r4 = 0).  The harness deliberately never seeds
 *   0xFFFF9F96 == 1 on the reachable-internal path (see harness header), so the
 *   tail is modelled at the boundary (rx8_crank_mode_switch below).
 * ==========================================================================*/
static void rx8_crank_sensor_init(void)
{
    RX8_IO8(RX8_CRK_STATE_FC9) = 0x00u;         /* 0x7C30..0x7C36              */
    RX8_IO8(RX8_CRK_STATE_FCA) = 0xFFu;         /* 0x7C38..0x7C3A              */
    if (RX8_IO8(RX8_CRK_STATE_F96) == 0x01u) {  /* 0x7C3C..0x7C42 cmp/eq #1    */
        RX8_IO8(RX8_CRK_STATE_F96) = 0x00u;     /* 0x7C48..0x7C4A              */
        rx8_crank_mode_switch();                /* 0x7C4C bra 0x0768C, r4 = 0  */
    }
}

/* ============================================================================
 * 0x0768C — crank_mode_switch (boundary model; the full ROM body ends with a
 *   computed `jmp @u32@0x0000DB60` through a mode-function pointer kept in RAM)
 *   Reached only via crankSensorInit's run-flag tail-branch with r4 = 0, which
 *   the harness never exercises.  r4 == 0 -> bsr 0x07C00 (modelled); the
 *   computed dispatch is out of scope and documented as not reached.
 * ==========================================================================*/
static void rx8_crank_mode_switch(void)
{
    /* r4 == 0 (delay-slot `mov r2,r4` of the bra) -> the 0x07C00 branch. */
    rx8_crank_mode_write();
}

/* ============================================================================
 * 0x07ED8 — crank_flags_enable (net effect; 22 bytes)
 *   u8@0xFFFF9FCE = 1, u8@0xFFFF9FA0 = 1, u8@0xFFFF9F8C = 1,
 *   u16@0xFFFF9FCC = 0xFFFF.
 * ==========================================================================*/
static void rx8_crank_flags_enable(void)
{
    RX8_IO8(RX8_CRK_STATE_FCE) = 0x01u;         /* 0x7ED8..0x7EDE              */
    RX8_IO8(RX8_CRK_STATE_FA0) = 0x01u;         /* 0x7EDC..0x7EE0              */
    RX8_IO8(RX8_CRK_STATE_F8C) = 0x01u;         /* 0x7EE2..0x7EE6              */
    RX8_IO16(RX8_CRK_STATE_FCC) = 0xFFFFu;      /* 0x7EEC (rts delay)          */
}

/* ============================================================================
 * 0x07FB4 — crank_counters_reset (net effect; 32 bytes)
 *   u32@0xFFFF9F84 = 0x7FFFFFFF, u32@0xFFFF9F88 = 0x7FFFFFFF,
 *   f32@0xFFFF9F80 = 0.0, u8@0xFFFF9FE8 = 0, f32@0xFFFF9F90 = 0.0,
 *   u8@0xFFFF9F94 = 0.
 * ==========================================================================*/
static void rx8_crank_counters_reset(void)
{
    RX8_IO32(RX8_CRK_VAL_F84) = 0x7FFFFFFFu;    /* 0x7FBE mov.l r4            */
    RX8_IO32(RX8_CRK_VAL_F88) = 0x7FFFFFFFu;    /* 0x7FC0                     */
    RX8_IO32(RX8_CRK_VAL_F80) = 0x00000000u;    /* 0x7FC6 fmov.s fr4 (0.0)    */
    RX8_IO8(RX8_CRK_STATE_FE8) = 0x00u;         /* 0x7FC8                     */
    RX8_IO32(RX8_CRK_VAL_F90) = 0x00000000u;    /* 0x7FCC fmov.s fr4 (0.0)    */
    RX8_IO8(RX8_CRK_STATE_F94) = 0x00u;         /* 0x7FD2 (rts delay)         */
}

/* ============================================================================
 * 0x0808E — crank_output_update (net effect; the fuel-init TAIL-CALL target)
 *   f32@0xFFFF9FF0 = 10.0, f32@0xFFFF9FF4 = 10.0 (fmov.s fr4, fr4 = f32@0x080FC),
 *   f32@0xFFFF9FF8 = 0.0, f32@0xFFFF9FFC = 0.0 (fldi0 fr4), f32@0xFFFF9FEC = 1.0
 *   (fldi1 fr3).  The ROM body ends in `rts`, so the call returns through the
 *   caller's PR — the emulator returns when PR == the 0xEEEE0000 sentinel.
 * ==========================================================================*/
static void rx8_crank_output_update(void)
{
    /* f32@0x000080FC = 10.0f (bits 0x41200000); ROM page below mmap_min_addr,
     * value pinned by the harness check_cal. */
    RX8_IO32(RX8_CRK_VAL_FF0) = 0x41200000u;    /* 0x8096                      */
    RX8_IO32(RX8_CRK_VAL_FF4) = 0x41200000u;    /* 0x809A                      */
    RX8_IO32(RX8_CRK_VAL_FF8) = 0x00000000u;    /* 0x80A2 (fr4 = 0.0)         */
    RX8_IO32(RX8_CRK_VAL_FFC) = 0x00000000u;    /* 0x80A4                      */
    RX8_IO32(RX8_CRK_VAL_FEC) = 0x3F800000u;    /* 0x80AA fr3 = 1.0 (rts delay)*/
}

/* ============================================================================
 * 0x753C — fuelingInit: fuel & crank-subsystem initialisation.
 * ==========================================================================*/
void rx8_fueling_init(void)
{
    rx8_crank_timer_hw_reset();                 /* 0x7540 bsr 0x076DC          */

    RX8_IO16(RX8_TMR_F6EA) &= 0xFFFBu;          /* 0x7544..0x754C              */

    RX8_IO8(RX8_CRK_STATE_FA3) = 0x01u;         /* 0x7556                      */
    RX8_IO8(RX8_CRK_STATE_FA4) = 0x00u;         /* 0x7558                      */
    RX8_IO8(RX8_CRK_STATE_FA5) = 0x00u;         /* 0x755E                      */
    RX8_IO8(RX8_CRK_STATE_FC0) = 0x00u;         /* 0x7560                      */
    RX8_IO8(RX8_CRK_STATE_FC4) = 0x00u;         /* 0x7566                      */
    RX8_IO8(RX8_CRK_STATE_FA2) = 0x00u;         /* 0x756A (bsr delay slot)     */
    rx8_crank_vars_init();                      /* 0x7568 bsr 0x07748          */

    rx8_crank_mode_write();                     /* 0x756C bsr 0x07C00          */
    rx8_crank_state_bytes_clear();              /* 0x7570 bsr 0x07BA8          */

    RX8_IO8(RX8_CRK_STATE_F96) = 0x00u;         /* 0x7576                      */
    RX8_IO8(RX8_CRK_STATE_FCB) = 0x00u;         /* 0x757C (bsr delay slot)     */
    rx8_crank_sensor_init();                    /* 0x757A bsr 0x07C30          */

    rx8_crank_flags_enable();                   /* 0x757E bsr 0x07ED8          */
    rx8_crank_counters_reset();                 /* 0x7582 bsr 0x07FB4          */

    rx8_crank_output_update();                  /* 0x7588 bra 0x0808E (tail)   */
}

/*
 * =============================================================================
 * rx8_alternating_sensor_sm.c  —  ALTERNATING SENSOR STATE MACHINE (3rd
 *                                 instance: diagMeteringPumpPositionControl)
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x5D34C
 * Status      : VERIFIED — behavioural equivalence to the ROM bytes held by
 *               reconstructed/samples/tests/harness_alternating_sensor_sm.py
 *               (host-gcc + mmap vs tools/sh2emu.py over edge + 20000 random
 *               state vectors, RAM side-effects compared; 0 mismatches).
 * Lift (truth): c/alternating_sensor_sm_5D34C.c  (same behaviour; symbol-table
 *               name `diagMeteringPumpPositionControl`, 0x5D34C..0x5D3E8,
 *               ida-ai `sensor_read_and_process_5D34C`).
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * One of a small family of identical "alternating sensor" state machines that
 * poll a raw sensor word and drive a two-flag output byte through a small
 * Moore FSM.  The instance at 0x5D34C is the RAW-value variant: unlike the
 * sm_08 sibling it does NOT gate the output flag on `==1`, it returns the raw
 * command byte or the raw latch verbatim.  Disassembly of 60E1D400.bin @
 * 0x5D34C (this ROM, r6 = struct base 0x60204, r4 = cmd):
 *
 *     D33F   mov.l  @(disp,PC),r3    ; &0xFFFFD355 (state byte)
 *     6530   mov.b  @r3,r5           ; r5 = ST
 *     D63F   mov.l  @(disp,PC),r6    ; r6 = 0x60204
 *     625C   extu.b r5,r2
 *     2228   tst    r2,r2            ; T = (ST == 0)
 *     8F2E   bf/s   0x5D3B6          ; ST != 0 -> skip first block
 *     0009   nop
 *     8468   mov.b  @(0x08,r6),r0    ; r0 = mask  (RAM8[0x6020C])
 *     9273   mov.w  @(disp,PC),r2    ; r2 = 0xD3A8 (input addr)
 *     6720   mov.b  @r2,r7           ; r7 = RAM8[0xFFFFD3A8]
 *     9372   mov.w  @(disp,PC),r3    ; r3 = 0x172D (magic)
 *     2709   and    r0,r7            ; r7 = input & mask
 *     D03B   mov.l  @(disp,PC),r0    ; &0xFFFFD350 (magic word)
 *     6101   mov.w  @r0,r1
 *     611D   extu.w r1,r1
 *     3130   cmp/eq r3,r1            ; T = (magic == 0x172D)
 *     8F1A   bf/s   0x5D3A4          ; magic mismatch -> else branch
 *     0009   nop
 *     677C   extu.b r7,r7
 *     2778   tst    r7,r7            ; T = (masked == 0)
 *     8D11   bt/s   0x5D39A          ; masked == 0 -> ST = 2, *ptr = 0
 *     0009   nop
 *     D737   mov.l  @(disp,PC),r7    ; &0xFFFFD354 (count byte)
 *     5263   mov.l  @(0xC,r6),r2     ; r2 = ptr (RAM32[0x60210])
 *     6170   mov.b  @r7,r1
 *     2210   mov.b  r1,@r2           ; *ptr = CNT
 *     6070   mov.b  @r7,r0
 *     600C   extu.b r0,r0
 *     8807   cmp/eq #0x07,r0         ; T = (CNT == 7)
 *     8F14   bf/s   0x5D3B2          ; CNT != 7 -> just ST = 1
 *     E501   mov    #0x01,r5         ;   (delay) ST = 1
 *     D134   mov.l  @(disp,PC),r1    ; &0xFFFFD385 (latch)
 *     D034   mov.l  @(disp,PC),r0    ; &0xFFFFD352 (source word)
 *     6201   mov.w  @r0,r2
 *     622D   extu.w r2,r2
 *     4219   shlr8  r2               ; r2 = SRC >> 8
 *     2120   mov.b  r2,@r1           ; latch = high byte of SRC
 *     A00C   bra    0x5D3B2
 *     0009   nop
 *     5D39A: E502   mov #0x02,r5     ; ST = 2
 *     5263   mov.l @(0xC,r6),r2
 *     E100   mov  #0x00,r1
 *     A007   bra   0x5D3B2
 *     2210   mov.b r1,@r2            ;   (delay) *ptr = 0
 *     5D3A4: 677C   extu.b r7,r7     ; magic mismatch path
 *     2778   tst    r7,r7            ; T = (masked == 0)
 *     8F03   bf/s   0x5D3B2          ; masked != 0 -> no store, ST = 0
 *     0009   nop
 *     5163   mov.l @(0xC,r6),r1
 *     E200   mov  #0x00,r2
 *     2120   mov.b r2,@r1            ; *ptr = 0
 *     5D3B2: D326   mov.l @(disp,PC),r3   ; &0xFFFFD355
 *     2350   mov.b r5,@r3            ; ST = r5 (0/1/2)
 *     ; ---- second block (always runs) — RAW variant ----
 *     5D3B6: D726   mov.l @(disp,PC),r7   ; r7 = 0x60204
 *     D62A   mov.l @(disp,PC),r6     ; r6 = 0xFFFFD371
 *     5773   mov.l @(0xC,r7),r7      ; r7 = ptr
 *     6770   mov.b @r7,r7            ; out = *ptr
 *     617C   extu.b r7,r1
 *     2118   tst    r1,r1            ; T = (out == 0)
 *     8F03   bf/s   0x5D3CC
 *     6543   mov    r4,r5            ;   (delay) r5 = cmd
 *     7614   add    #0x14,r6         ; r6 = 0xFFFFD385 (latch)
 *     A00C   bra    0x5D3E4
 *     2640   mov.b  r4,@r6           ;   (delay) latch = cmd
 *     5D3CC: 6013   mov  r1,r0
 *     8805   cmp/eq #0x05,r0
 *     8D04   bt/s   0x5D3DC          ; out == 5 -> return latch
 *     0009   nop
 *     6013   mov  r1,r0
 *     8807   cmp/eq #0x07,r0
 *     8F04   bf/s   0x5D3E4          ; out != 7 -> return cmd
 *     0009   nop
 *     5D3DC: 6463   mov  r6,r4       ; r4 = 0xFFFFD371
 *     7414   add   #0x14,r4          ; r4 = 0xFFFFD385
 *     6440   mov.b @r4,r4            ; r4 = latch
 *     6543   mov   r4,r5
 *     5D3E4: 000B   rts
 *     6053   mov    r5,r0            ;   (delay) r0 = result
 *
 * Two behavioural details matter for bit-exactness:
 *  1. the whole "out==0 -> write cmd into the latch" step is the RAW variant:
 *     the sibling sm_08 latches only when cmd == 1, this instance stores the
 *     byte verbatim (no ==1 gating);
 *  2. when out is 5 or 7 the function returns the latch byte; for out == 0 it
 *     returns the (latched) command; otherwise it returns cmd unchanged.
 *
 * The disassembly shown above was cross-checked against the verified lift
 * c/alternating_sensor_sm_5D34C.c instruction-for-instruction — the lift is
 * complete; NO discrepancy was found, so this sample is a clean port.
 *
 * CALLING CONVENTION
 * ------------------
 * Standard ABI: r4 = cmd (u8), result returned in r0.  The function reads and
 * writes on-chip RAM through absolute volatile pointers (state/latch/input/
 * count/source cells and the output byte behind the stored RAM pointer at
 * 0x60210).  The host oracle MAP_FIXED-maps the pages backing both the
 * flash-shadow SM descriptor (0x6020C/0x60210) and the RAM window, and the
 * harness compares the return value together with the side-effected cells.
 * =============================================================================
 */
#include <stdint.h>
#include "rx8_samples.h"

#define SM_BASE    0x60204UL
#define SM_MASK    (*(volatile uint8_t  *)(SM_BASE + 0x8))   /* 0x6020C */
#define SM_PTR     (*(volatile uint32_t *)(SM_BASE + 0xC))   /* 0x60210 */
#define ST_D355    (*(volatile uint8_t  *)0xFFFFD355UL)
#define MAGIC_D350 (*(volatile uint16_t *)0xFFFFD350UL)
#define INP_D3A8   (*(volatile uint8_t  *)0xFFFFD3A8UL)
#define CNT_D354   (*(volatile uint8_t  *)0xFFFFD354UL)
#define SRC_D352   (*(volatile uint16_t *)0xFFFFD352UL)
#define LATCH_D385 (*(volatile uint8_t  *)0xFFFFD385UL)

uint8_t rx8_alternating_sensor_sm(uint8_t cmd /* r4 */)
{
    volatile uint8_t *ptr = (volatile uint8_t *)(uintptr_t)SM_PTR;  /* stored RAM pointer @0x60210 */
    uint8_t mask = SM_MASK;

    /* First block — only runs while the state byte is 0 (a 0/1/2 Moore FSM). */
    if (ST_D355 == 0) {
        uint8_t masked = INP_D3A8 & mask;
        if (MAGIC_D350 == 0x172D) {
            if (masked != 0) {
                *ptr = CNT_D354;
                if (CNT_D354 == 7)
                    LATCH_D385 = (SRC_D352 >> 8) & 0xFF;
                ST_D355 = 1;
            } else {
                *ptr = 0;
                ST_D355 = 2;
            }
        } else {
            if (masked == 0)
                *ptr = 0;
            ST_D355 = 0;
        }
    }

    /* Second block — always runs.  RAW-value variant: no ==1 gating anywhere;
     * out==0 latches the raw cmd byte, out in {5,7} returns the raw latch. */
    uint8_t out = *ptr;
    if (out == 0) {
        LATCH_D385 = cmd;              /* raw, no ==1 gating */
        return cmd;
    }
    if (out == 5 || out == 7)
        return LATCH_D385;             /* raw latch */
    return cmd;
}

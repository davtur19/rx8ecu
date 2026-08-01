/*
 * =============================================================================
 * rx8_immo_good_state_set.c  —  IMMOBILIZER "GOOD STATE" LATCH (void leaf)
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x36544
 * Status      : VERIFIED — behavioural equivalence to the ROM bytes held by
 *               reconstructed/samples/tests/harness_immo_good_state_set.py
 *               (host-gcc vs tools/sh2emu.py over edge + 20000 random
 *               initial-RAM-state vectors; bit-exact RAM side effects,
 *               0 mismatches).
 * Lift (truth): c/ImmoGoodStateSet.c  (same address 0x36544)
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * The immobilizer state machine calls this once the key/seed exchange has
 * succeeded.  It latches the "good" state: switches the warning lamp OFF
 * (setImmoLight(1)), raises the CAN TX flag, records the good state in the
 * EEPROM working copy E2[0x1E] and primes the seed machine with the good-state
 * timers and result codes.  It is a `void f(void)` leaf with NO input registers
 * and NO meaningful return value — every one of its effects is a fixed write
 * to on-chip RAM, so verification is a pure RAM-side-effect comparison.
 *
 * CORRECTED LISTING (disassembly of 60E1D400.bin @ 0x36544)
 * ---------------------------------------------------------
 *    0x36544  4F22  sts.l  pr,@-r15               ; prologue
 *    0x36546  D318  mov.l  @(0x365A8,pc),r3       ; r3 = 0x000263C8 (setImmoLight)
 *    0x36548  430B  jsr    @r3
 *    0x3654A  E401  mov    #0x01,r4               ;  (delay) setImmoLight(1)
 *    0x3654C  9318  mov.w  @(0x36580,pc),r3       ; r3 = 0xC240  (SIGN-EXTENDED!)
 *    0x3654E  E102  mov    #0x02,r1
 *    0x36550  D016  mov.l  @(0x365AC,pc),r0       ; r0 = 0xFFFFC2F2
 *    0x36552  E400  mov    #0x00,r4
 *    0x36554  E201  mov    #0x01,r2
 *    0x36556  2320  mov.b  r2,@r3                 ; *(u8*)0xFFFFC240 = 1
 *    0x36558  2010  mov.b  r1,@r0                 ; *(u8*)0xFFFFC2F2 = 2
 *    0x3655A  D115  mov.l  @(0x365B0,pc),r1       ; r1 = 0xFFFFC29F
 *    0x3655C  9311  mov.w  @(0x36582,pc),r3       ; r3 = 0x3A98
 *    0x3655E  2120  mov.b  r2,@r1                 ; *(u8*)0xFFFFC29F = 1
 *    0x36560  D210  mov.l  @(0x365A4,pc),r2       ; r2 = 0xFFFFC282
 *    0x36562  2231  mov.w  r3,@r2                 ; *(u16*)0xFFFFC282 = 0x3A98
 *    0x36564  900E  mov.w  @(0x36584,pc),r0       ; r0 = 0x00FA
 *    0x36566  E203  mov    #0x03,r2
 *    0x36568  D307  mov.l  @(0x36588,pc),r3       ; r3 = 0xFFFFC284
 *    0x3656A  2301  mov.w  r0,@r3                 ; *(u16*)0xFFFFC284 = 0x00FA
 *    0x3656C  D108  mov.l  @(0x36590,pc),r1       ; r1 = 0xFFFFC28C
 *    0x3656E  2140  mov.b  r4,@r1                 ; *(u8*)0xFFFFC28C = 0
 *    0x36570  D008  mov.l  @(0x36594,pc),r0       ; r0 = 0xFFFFC28D
 *    0x36572  2020  mov.b  r2,@r0                 ; *(u8*)0xFFFFC28D = 3
 *    0x36574  D30F  mov.l  @(0x365B4,pc),r3       ; r3 = 0xFFFFC29A
 *    0x36576  4F26  lds.l  @r15+,pr               ; epilogue
 *    0x36578  000B  rts
 *    0x3657A  2340  mov.b  r4,@r3                 ;  (delay) *(u8*)0xFFFFC29A = 0
 *    ... literal pool @ 0x36580: C240 3A98 00FA | FFFFC284 FFFFC28C FFFFC28D
 *        @ 0x365A4: FFFFC282 000263C8 FFFFC2F2 FFFFC29F FFFFC29A
 *
 * DISCREPANCIES vs c/ImmoGoodStateSet.c (documented, corrected here)
 * ------------------------------------------------------------------
 *  1. 0x3654C loads the CAN TX address with `mov.w @(disp,pc),r3`.  mov.w
 *      SIGN-EXTENDS the 16-bit constant 0xC240 to 0xFFFFC240, so the ROM
 *      (and the emulator ground truth) writes the byte at 0xFFFFC240, NOT
 *      the 0x0000C240 of the lift's CAN_TX_DATA macro (c/eeprom_immo.h).
 *      Same pattern as the verified message_queue dispatcher epilogue
 *      (0x36AA0 `mov.w ...` -> 0xFFFFC241) and ImmoGetCANData (0xFFFFC529).
 *  2. setImmoLight (0x263C8) likewise loads the lamp register with
 *      `mov.w @(0x2644C,pc),r13` = 0xF754 SIGN-EXTENDED to 0xFFFFF754
 *      (the RX8_STATUS_WORD of rx8_hw.h), so the lamp write lands at
 *      0xFFFFF754, not the 0xF754 of the lift's IMMO_LAMP_REG.
 *  3. The lift's listing says "0x36546 jsr 0x263C8"; the real bytes put
 *      the address load at 0x36546 and the jsr at 0x36548 (same semantics).
 *
 * CALLING CONVENTION
 * ------------------
 * void f(void): entered via the normal ABI, no arguments in r4-r7/fr4-fr7,
 * no return value (r0 is left as the address 0xFFFFC28D; callers ignore it).
 * Internally it jsr's the ROM subroutine setImmoLight @0x263C8 (r4 = 1),
 * whose ONLY net RAM effect is OR-ing bits 0x40 and 0x20 into the 16-bit
 * lamp register 0xFFFFF754 (via saveSRMaskParam/reg16SetClear/restoreSR;
 * see c/setImmoLight.c).  That call is inlined below as its net effect —
 * the host oracle cannot execute the SR-mask helpers' register semantics.
 *
 * RAM SIDE EFFECTS (all fixed constants, checked against the emulator):
 *   0xFFFFC240 u8  = 1      CAN TX flag
 *   0xFFFFC2F2 u8  = 2      E2[0x1E] working copy (good state)
 *   0xFFFFC29F u8  = 1      seed machine active
 *   0xFFFFC282 u16 = 0x3A98 good-state timer
 *   0xFFFFC284 u16 = 0x00FA good-state timeout counter
 *   0xFFFFC28C u8  = 0      reserved result slot
 *   0xFFFFC28D u8  = 3      result code 3 (good)
 *   0xFFFFC29A u8  = 0      good-state flag
 *   0xFFFFF754 u16|= 0x60   immo lamp OFF (setImmoLight(1): |0x40 then |0x20)
 * =============================================================================
 */
#include <stdint.h>

/* Immobilizer good-state side-effect locations (see header for the
 * sign-extension correction of the lift's 0x0000C240 / 0xF754 addresses). */
#define IMMO_CAN_TX_DATA     (*(volatile uint8_t  *)0xFFFFC240)
#define IMMO_E2_WORK_INDEX30 (*(volatile uint8_t  *)0xFFFFC2F2)
#define IMMO_SEED_ACTIVE     (*(volatile uint8_t  *)0xFFFFC29F)
#define IMMO_TIMER           (*(volatile uint16_t *)0xFFFFC282)
#define IMMO_TIMEOUT_CTR     (*(volatile uint16_t *)0xFFFFC284)
#define IMMO_RESULT_SLOT_1   (*(volatile uint8_t  *)0xFFFFC28C)
#define IMMO_STATE_CODE      (*(volatile uint8_t  *)0xFFFFC28D)
#define IMMO_GOODSTATE_FLAG  (*(volatile uint8_t  *)0xFFFFC29A)
#define IMMO_LAMP_REG        (*(volatile uint16_t *)0xFFFFF754)

void rx8_immo_good_state_set(void)
{
    /* ROM 0x36546/0x36548: jsr setImmoLight @0x263C8 with r4 = 1.  The
     * subroutine ORs mask 0x40 then mask 0x20 into the 16-bit lamp register
     * (reg16SetClear @0x4BBC, SR-wrapped).  Inlined as its net effect. */
    IMMO_LAMP_REG |= 0x40u;
    IMMO_LAMP_REG |= 0x20u;

    IMMO_CAN_TX_DATA     = 1;       /* 0x36556  mov.b r2(1),@r3          */
    IMMO_E2_WORK_INDEX30 = 2;       /* 0x36558  mov.b r1(2),@r0          */
    IMMO_SEED_ACTIVE     = 1;       /* 0x3655E  mov.b r2(1),@r1          */
    IMMO_TIMER           = 0x3A98;  /* 0x36562  mov.w r3(0x3A98),@r2     */
    IMMO_TIMEOUT_CTR     = 0x00FA;  /* 0x3656A  mov.w r0(0x00FA),@r3     */
    IMMO_RESULT_SLOT_1   = 0;       /* 0x3656E  mov.b r4(0),@r1          */
    IMMO_STATE_CODE      = 3;       /* 0x36572  mov.b r2(3),@r0          */
    IMMO_GOODSTATE_FLAG  = 0;       /* 0x3657A  mov.b r4(0),@r3 (rts ds) */
}

/*
 * =============================================================================
 * rx8_vfad_control_35bbc.c  —  VFAD SOLENOID CONTROL (BOOST HYSTERESIS + SM)
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x35BBC  (312 bytes: 0x35BBC .. 0x35CE4, next fn @0x35CE4)
 * Status      : VERIFIED — behavioural equivalence to the ROM bytes held by
 *               reconstructed/samples/tests/harness_vfad_control_35bbc.py
 *               (host-gcc + mmap vs tools/sh2emu.py over edge + 20000 random
 *               boost/RAM pre-state vectors; RAM side-effects compared
 *               bit-exactly; 0 mismatches).
 * Lift (truth): c/vfad_control_35BBC.c  (same address; verified by
 *               c/tests/test_vfad_control_35BBC.py — 10000 random inputs,
 *               0 mismatches — and listed in c/verified_addrs.txt).
 *
 * WHAT THIS IS
 * ------------
 * Stock Variable Fresh Air Duct (VFAD) solenoid control task.  Reads the
 * boost-pressure f32, applies an on/off hysteresis command with a hold-in-band,
 * feeds the command through the "alternating sensor" debounce state machine
 * @0x5D800 (second instance, struct base 0x60254), publishes the SM result
 * into RAM[0xFFFFC234] and mirrors it onto bit 0x0400 of the hardware word
 * RAM[0xFFFFF754] via the set/clear-bits leaf @0x4BBC.
 *
 * Key ROM flow (disassembly of 60E1D400.bin @0x35BBC):
 *
 *     2fe6/2fd6/2fc6/2fb6  mov.l r14..r11,@-r15 ; 4f22 sts.l pr,@-r15
 *     7ff8                 add #-8,r15          ; scratch slots (SR game)
 *     933a mov.w @(pc),r3 ; f438 fmov.s @r3,fr4 ; fr4 = RAM f32 boost
 *     d21f mov.l 0x7A5AC,r2 ; f628 fmov.s @r2,fr6 ; fr6 = ROM f32 ON (5250.0)
 *     d11f mov.l 0x7A5B0,r1 ; f318 fmov.s @r1,fr3 ; fr3 = ROM f32 HYST (188.0)
 *     f56c fmov fr6,fr5    ; f531 fsub fr3,fr5   ; fr5 = 5250.0 - 188.0 (5062.0)
 *     f645 fcmp/gt fr4,fr6 ; 8d02 bt/s +64b0     ; T=(fr6>fr4)=(5250>boost)
 *     a004 bra +e401        ;   (delay) r4 = 1    ; NOT(5250>boost) -> cmd=1
 *     f545 fcmp/gt fr4,fr5 ; 8f01 bf/s           ; T=(5062>boost)
 *     e400 mov #0,r4                              ; 5062>boost -> cmd=0
 *     d219 mov.l 0x5D800,r2 ; 420b jsr @r2       ; r4=cmd -> SM 0x5D800
 *     2b00 mov.b r0,@r11     ; RAM[0xFFFFC234] = sm result
 *     9d25/9e25 mov.w F754,0x0400
 *     ... if (result == 1) jsr 0x4BBC(0xFFFFF754,0x0400,1)
 *     ... else               jsr 0x4BBC(0xFFFFF754,0x0400,0)
 *     ... jsr 0x2064 (SR restore from the 0x2054 scratch; not a real output)
 *     4f26 lds.l pr + pops + rts
 *
 * FP/INT EXACTNESS NOTES
 * ----------------------
 *  1. fcmp/gt operand order — the emulator (and the real FPU) evaluates
 *     `fcmp/gt FRn,FRm` as FRn > FRm; the disassembled `fcmp/gt fr4,fr6`
 *     (fr4=boost, fr6=ON) therefore means `5250.0 > boost`.  Writing the C
 *     condition as `!(ROM_ON > x)` reproduces the ROM's decision branch for
 *     EVERY input, including NaN: `5250 > NaN` is false in IEEE arithmetic,
 *     so `!(5250 > NaN)` is true and the ROM treats a NaN boost as ON
 *     (cmd=1, same as boost >= 5250).  The lift's `if (x >= 5250)` form is
 *     algebraically identical for all real inputs but silently holds the old
 *     command for NaN — that discrepancy is corrected here (see below).
 *  2. the off-threshold is computed with ONE runtime fsub: fr5 = ON - HYST
 *     = 5250.0f - 188.0f.  Both operands and the result (5062.0) are exact
 *     f32 values, so the host expression `ROM_ON - ROM_HYST` is bit-identical.
 *  3. the two callees are leaf functions that ARE exercised for real inside
 *     the emulator (jsr to the actual ROM bytes @0x5D800 and @0x4BBC).  This
 *     port inlines both, from their verified models:
 *     - alternating_sensor_sm @0x5D800: c/tests/test_alt_sensor_sm_5D800.py
 *       (20000 inputs, 0 mismatches; magic 0x17C8, base 0x60254);
 *     - setRegister_REG_BIT_VAL @0x4BBC: samples/src/rx8_set_register_reg_bit_val.c
 *       (verified via harness_set_register_reg_bit_val.py).
 *  4. the 0x2054/0x2064 pair at the end is the ROM's SR-scratch dance (stc
 *     SR/and #0xF0 -> stack, later ldc SR) used to bracket the register
 *     write; it leaves SR = SR_in & 0xF0 and touches no RAM cell the
 *     function reports.  It is intentionally NOT modelled (see the lift's
 *     header comment: "Not a real output").
 *
 * DISCREPANCY FOUND vs THE LIFT (documented per task instructions)
 * ----------------------------------------------------------------
 * c/vfad_control_35BBC.c writes:
 *     if (x >= ROM_ON) cmd = 1; else if (x < ROM_ON - ROM_HYST) cmd = 0;
 *     else cmd = RAM_CMD;
 * For a NaN boost, `x >= 5250.0f` and `x < 5062.0f` are both false, so the
 * lift falls into the "hold" branch and keeps RAM_CMD.  The ROM instead
 * takes cmd = 1 (verified on the emulator: NaN -> C234=1, F754|0x0400).
 * The reconstructed function below keeps the lift's exact semantics for every
 * non-NaN input but reproduces the ROM's NaN-as-ON behaviour via the
 * `!(ROM_ON > x)` form.  (The lift's own 10000-input emulator test drew only
 * uniform(0,12000) boosts and never hit NaN.)
 * =============================================================================
 */
#include <stdint.h>

#define RAM_BOOST   (*(volatile float    *)0xFFFFB5B8UL)  /* boost f32      */
#define RAM_CMD     (*(volatile uint8_t  *)0xFFFFC234UL)  /* VFAD command   */
#define RAM_F754    (*(volatile uint16_t *)0xFFFFF754UL)  /* hw word, bit 0x0400 */

#define ROM_ON      (*(const float *)0x0007A5ACUL)        /* 5250.0 (stock) */
#define ROM_HYST    (*(const float *)0x0007A5B0UL)        /* 188.0  (stock) */

/* alternating_sensor_sm @0x5D800 — second instance (base 0x60254, magic 0x17C8),
 * verified by c/tests/test_alt_sensor_sm_5D800.py. */
#define SM_BASE     0x60254UL
#define SM_MASK     (*(volatile uint8_t  *)(SM_BASE + 8))   /* 0x6025C mask */
#define SM_PTR      (*(volatile uint32_t *)(SM_BASE + 12))  /* 0x60260 output ptr */
#define ST_D355     (*(volatile uint8_t  *)0xFFFFD355UL)   /* state byte   */
#define MAGIC_D350  (*(volatile uint16_t *)0xFFFFD350UL)   /* magic word (0x17C8) */
#define INP_D3A8    (*(volatile uint8_t  *)0xFFFFD3A8UL)   /* sensor input byte */
#define CNT_D354    (*(volatile uint8_t  *)0xFFFFD354UL)   /* count byte   */
#define SRC_D352    (*(volatile uint16_t *)0xFFFFD352UL)   /* source word  */
#define LATCH_D38F  (*(volatile uint8_t  *)0xFFFFD38FUL)   /* output latch */

/* 0x5D800 — the alternating-sensor debounce the VFAD command runs through.
 * Port of the verified model in c/tests/test_alt_sensor_sm_5D800.py (the
 * 0x5D34C sibling is samples/src/rx8_alternating_sensor_sm.c; this instance
 * differs in struct base 0x60254, magic 0x17C8 and the latch/return logic). */
static uint8_t vfad_sm_5D800(uint8_t cmd)
{
    volatile uint8_t *ptr = (volatile uint8_t *)(uintptr_t)SM_PTR;
    uint8_t mask = SM_MASK;
    uint8_t out;

    /* First block — only runs while the state byte is 0 (0/1/2 Moore FSM). */
    if (ST_D355 == 0) {
        uint8_t masked = INP_D3A8 & mask;
        if (MAGIC_D350 == 0x17C8) {
            if (masked != 0) {
                *ptr = CNT_D354;
                if (CNT_D354 == 7)
                    LATCH_D38F = (SRC_D352 >> 8) & 0xFF;
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

    /* Second block — always runs: out==0 latches (cmd==1) and returns cmd;
     * out in {5,7} returns (latch==1); anything else returns cmd. */
    out = *ptr;
    if (out == 0) {
        LATCH_D38F = (cmd == 1) ? 1 : 0;
        return cmd;
    }
    if (out == 5 || out == 7)
        return (LATCH_D38F == 1) ? 1 : 0;
    return cmd;
}

/* 0x35BBC — VFAD solenoid control: boost-pressure hysteresis command fed
 * through the alternating-sensor SM, published to RAM and mirrored onto
 * bit 0x0400 of the hardware word 0xFFFFF754. */
void rx8_vfad_control_35bbc(void)
{
    float x = RAM_BOOST;
    uint8_t cmd, out;

    /* Hysteresis with hold-in-band.  `!(ROM_ON > x)` (not `x >= ROM_ON`)
     * matches the ROM's fcmp/gt branch exactly, including NaN -> cmd = 1. */
    if (!(ROM_ON > x))                          /* boost >= 5250 (or NaN) */
        cmd = 1;
    else if (!(ROM_ON - ROM_HYST > x))          /* 5062 <= boost < 5250  */
        cmd = RAM_CMD;                          /* hold in band          */
    else                                        /* boost < 5062          */
        cmd = 0;

    out = vfad_sm_5D800(cmd);
    RAM_CMD = out;

    /* setRegister_REG_BIT_VAL @0x4BBC (inlined; see rx8_set_register_reg_bit_val.c):
     * set/clear bit 0x0400 of 0xFFFFF754 according to (out == 1). */
    {
        uint16_t tmp = RAM_F754;
        if (out == 1)
            tmp |= 0x0400;
        else
            tmp &= ~0x0400;
        RAM_F754 = tmp;
    }
}

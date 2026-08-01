/*
 * =============================================================================
 * rx8_ssv_control.c  —  SECONDARY SHUTTER VALVE (SSV) CONTROL TASK
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x225C8  (size 312 bytes incl. the 0x226C2..0x226FC literal
 *               pool; body ends with `rts` at 0x226BE-0x226C0)
 * Status      : VERIFIED — behavioural equivalence to the ROM held by
 *               reconstructed/samples/tests/harness_ssv_control.py
 *               (host-gcc + mmap vs tools/sh2emu.py over edge + 20000 random
 *               pre-states; every RAM side-effect compared byte-for-byte).
 * Lift (truth): c/ssvControl.c  (same address; c/tests/test_ssv_control.py
 *               verified it over 12000 finite random temperatures).  ONE
 *               discrepancy vs that lift was found and is corrected here —
 *               see "NAN / INF TEMPERATURE" below.
 *
 * WHAT THIS IS
 * ------------
 * The periodic SSV task.  A temperature-hysteresis block (on >= 200 C,
 * off < 197 C, hold in the 3-degree band) produces a 1/0 command byte; a
 * transition counter is reloaded (188) when the mode drops from 1 to 0 and
 * otherwise counts down; a gating decision combines the cal flag, a status
 * byte and the (mode, counter, command) triple into an `enable` bit; the
 * enable bit drives the alternating-sensor state machine leaf @0x5D3E8 whose
 * result is published to a status-word bit.  Called with no arguments from
 * the task layer (`jsr` with r15 pointing at the caller's frame); it returns
 * nothing (the only exit is a plain `rts`).  ROM path (60E1D400.bin @0x225C8):
 *
 *     mov.l  r14,@-r15 ; mov #0x01,r6 ; mov.l @lit,r4  ; save regs; r6 = 1
 *     mov.l  r13,@-r15 ; mov.l r12,@-r15 ; mov.l r11,@-r15 ; sts.l pr,@-r15
 *     add    #0xF8,r15
 *     mov.w  @lit,r3   ; mov.b @r3,r11       ; r11 = mode   (RAM8[0xFFFFAAE0])
 *     mov.w  @lit,r2   ; fmov.s @r2,fr4      ; fr4 = temp   (RAM32[0xFFFFAA10])
 *     mov.l  @lit,r1   ; fmov.s @r1,fr6      ; fr6 = 200.0  (ROM f32 @0x72F74)
 *     mova   0x226D4,r0 ; fmov fr6,fr5 ; fmov.s @r0,fr3  ; fr3 = -3.0 (ROM)
 *     fadd   fr3,fr5                        ; fr5 = 200.0 + (-3.0) = 197.0
 *     fcmp/gt fr4,fr6 ; bt/s 0x225F6         ; T = (200.0 > temp); temp<200 ->
 *       mov #0x00,r5                         ;   (delay) r5 = 0
 *     bra    0x225FE ; mov.b r6,@r4          ; cmd = 1     [temp >= 200 OR NaN]
 *     fcmp/gt fr4,fr5 ; bf/s 0x225FE         ; T = (197.0 > temp); temp>=197 ->
 *       nop
 *     mov.b  r5,@r4                          ; cmd = 0     [temp < 197]
 *     ; ---- counter (RAM16[0xFFFFB322]) ----
 *     extu.b r11,r2 ; tst r2,r2 ; bf/s 0x2261C       ; mode != 0 -> countdown
 *     mov.l  @lit,r4                                  ; r4 = &0xFFFFB322
 *     mov.l  @lit,r3 ; mov.b @r3,r0 ; extu.b r0,r0
 *     cmp/eq #0x01,r0 ; bf/s 0x2261C                  ; prev mode != 1 -> countdown
 *     mov.l  @lit,r2 ; mov.w @r2,r3                   ; r3 = 188 (ROM u16 @0x72F72)
 *     bra    0x2262E ; mov.w r3,@r4                   ; counter = 188
 *     ; 0x2261C countdown path:
 *     mov.w  @r4,r0 ; extu.w r0,r0 ; cmp/pl r0 ; bf/s 0x2262E  ; counter == 0 skip
 *     mov.l  @lit,r3                                   ; r3 = 0xFFFF
 *     mov.w  @r4,r2 ; add r3,r2 ; mov.w r2,@r4         ; counter -= 1
 *     ; ---- enable gating ----
 *     mov.l  @lit,r3 ; mov.b @r3,r0 ; extu.b r0,r0
 *     cmp/eq #0x01,r0 ; bt/s 0x22664                   ; cal flag == 1 -> enable
 *     mov.w  @lit,r2 ; mov.b @r2,r0 ; extu.b r0,r0
 *     cmp/eq #0x01,r0 ; bt/s 0x22664                   ; status == 1 -> enable
 *     extu.b r11,r0 ; tst r0,r0 ; bf/s 0x22668         ; mode != 0 -> no enable
 *     mov.l  @lit,r0 ; mov.w @r0,r1 ; extu.w r1,r1
 *     cmp/pl r1 ; bf/s 0x22668                         ; counter == 0 -> no enable
 *     mov.l  @lit,r3 ; mov.b @r3,r1 ; tst r1,r1
 *     bf/s   0x22668                                   ; cmd != 0 -> no enable
 *     ; 0x22664: bra 0x2266A ; mov r6,r4  -> r4 = 1   (enable on)
 *     ; 0x22668: mov r5,r4            -> r4 = 0       (enable off)
 *     ; ---- alternating_sensor_sm_08 @0x5D3E8 ----
 *     mov.l  @lit,r2 ; jsr @r2 ; nop                  ; r0 = sm_08(enable)
 *     mov.w  @lit,r3 ; mov.b r0,@r3                   ; RAM8[0xFFFFB320] = r0
 *     mov.l  @lit,r12 ; extu.b r0,r0                  ; r12 = 0x4BBC (bit RMW)
 *     mov.w  @lit,r13 ; cmp/eq #0x01,r0               ; r13 = 0xFFFFF754
 *     mov.w  @lit,r14 ; bf/s 0x22698                  ; r14 = 0x80
 *       nop
 *     ; out == 1: setSR_PARAM(r15+8, 0xE0) ; 0x4BBC(0xFFFFF754, 0x80, 1)
 *     mov r15,r4 ; mov.l @lit,r1 ; mov.w @lit,r5 ; jsr @r1 ; add #0x04,r4
 *     mov #0x01,r6 ; mov r14,r5 ; jsr @r12 ; mov r13,r4
 *     bra 0x226AA
 *     ; 0x22698 out != 1: setSR_PARAM(r15, 0xE0) ; 0x4BBC(0xFFFFF754, 0x80, 0)
 *     mov.w @lit,r5 ; mov.l @lit,r1 ; jsr @r1 ; mov r15,r4
 *     mov #0x00,r6 ; mov r14,r5 ; jsr @r12 ; mov r13,r4
 *     mov.l  @r15,r4                                ; r4 = saved SR (stack local)
 *     ; 0x226AA: mov.l @lit,r3 ; jsr @r3 ; nop     ; loadStatusRegister_ADDR(r4)
 *     mov.l  @lit,r2 ; mov.b r11,@r2                ; RAM8[0xFFFFB325] = mode
 *     add #0x08,r15 ; lds.l @r15+,pr ; mov.l @r15+,r11 ...
 *     rts
 *
 * CALLING CONVENTION & SUBROUTINES
 * --------------------------------
 * void ssvControl(void) — entered with a normal `jsr`; no ABI args, no return
 * value.  It internally `jsr`s four leaves, all executed for REAL by the
 * emulator in the harness: alternating_sensor_sm_08 @0x5D3E8 (tiny state
 * machine, verified separately by c/tests/test_alt_sensor_sm.py), the 16-bit
 * register bit-set/clear setRegister_REG_BIT_VAL @0x4BBC (verified by
 * c/tests/test_setRegister_REG_BIT_VAL.py), and the pure-SR wrappers
 * setSR_PARAM @0x2054 / loadStatusRegister_ADDR @0x2064.  The latter two only
 * save/restore the SR interrupt-mask through stack locals — they have ZERO
 * RAM side-effects, so this single-file sample inlines the two tiny leaves
 * (0x5D3E8 and 0x4BBC) and omits the SR juggling (noted in the code).
 *
 * NAN / INF TEMPERATURE  (discrepancy vs c/ssvControl.c — corrected here)
 * ----------------------
 * The lift reads the hysteresis as `if (t >= on) cmd = 1; else if (t < off)
 * cmd = 0;` — for NaN/inf that HOLDS the previous command.  The actual ROM
 * tests `fcmp/gt` (200.0 > t) and branches when TRUE; when the compare is
 * FALSE (t >= 200 OR NaN — and also +inf, since 200.0 > +inf is false) the
 * fall-through stores cmd = 1.  `!(200.0f > t)` reproduces that exactly
 * (true for NaN, unlike `t >= 200.0f`).  -inf and every huge-negative float
 * take the `off > t` arm (cmd = 0).  The harness drives NaN/±inf/denormal
 * and nextafter boundary vectors to pin this down.
 *
 * CALIBRATION CONSTANTS (ROM)
 * ---------------------------
 *   0x72F70 u8   cal flag          (= 0 in stock ROM)
 *   0x72F72 u16  counter reload    (= 188)
 *   0x72F74 f32  on-threshold      (= 200.0)
 *   0x226D4 f32  hysteresis delta  (= -3.0, so the off threshold is 197.0)
 * The host oracle mmap()s the actual ROM pages at the same virtual addresses
 * (file offset == virtual address), so both sides read identical bytes.
 * =============================================================================
 */
#include <stdint.h>
#include "rx8_samples.h"
#include "rx8_hw.h"

/* ---- SSV task cells (c/ssvControl.c, docs/notes/FINDINGS.md) -------------- */
#define RX8_SSV_TEMP_ADDR   0xFFFFAA10u   /* f32 temperature for the band      */
#define RX8_SSV_MODE_ADDR   0xFFFFAAE0u   /* u8 mode byte                      */
#define RX8_SSV_CMD_ADDR    0xFFFFB324u   /* u8 SSV command (1 open / 0 closed)*/
#define RX8_SSV_CNT_ADDR    0xFFFFB322u   /* u16 transition counter            */
#define RX8_SSV_OUT_ADDR    0xFFFFB320u   /* u8 alternating-sensor SM result   */
#define RX8_SSV_PREV_ADDR   0xFFFFB325u   /* u8 previous mode (state store)    */
#define RX8_SSV_STATUS_ADDR 0xFFFFBF39u   /* u8 status byte (==1 forces enable)*/
#define RX8_SSV_TEMP        (*(volatile float  *)RX8_SSV_TEMP_ADDR)

/* ---- calibration constants read from the ROM (host: mapped pages) --------- */
#define ROM_SSV_CAL_FLAG   (*(const uint8_t  *)0x00072F70u)   /* 0       */
#define ROM_SSV_RELOAD     (*(const uint16_t *)0x00072F72u)   /* 188     */
#define ROM_SSV_ON         (*(const float    *)0x00072F74u)   /* 200.0   */
#define ROM_SSV_HYSTERESIS (*(const float    *)0x000226D4u)   /* -3.0    */

/* ---- alternating-sensor SM descriptor + cells (0x5D3E8 leaf) -------------- */
#define RX8_SM_MASK_ADDR   0x6021Cu        /* u8 sensor mask   (base+8)  */
#define RX8_SM_PTR_ADDR    0x60220u        /* u32 output ptr   (base+0xC)*/
#define RX8_SM_ST_ADDR     0xFFFFD355u     /* u8 state byte               */
#define RX8_SM_MAGIC_ADDR  0xFFFFD350u     /* u16 magic word (0xE926)     */
#define RX8_SM_SRC_ADDR    0xFFFFD352u     /* u16 source word             */
#define RX8_SM_CNT_ADDR    0xFFFFD354u     /* u8 count byte               */
#define RX8_SM_INP_ADDR    0xFFFFD3A8u     /* u8 sensor input byte        */
#define RX8_SM_LATCH_ADDR  0xFFFFD387u     /* u8 output latch             */

/* alternating_sensor_sm_08 @0x5D3E8 — tiny leaf (verified separately by
 * c/tests/test_alt_sensor_sm.py, 20000 inputs).  Inlined here so the sample
 * stays single-file; the harness still runs the REAL ROM bytes of the leaf.
 * `cmd` = enable bit (r4).  RAM side-effects: state, latch, output byte. */
static uint8_t ssv_sm_08(uint8_t cmd)
{
    uint8_t mask = RX8_IO8(RX8_SM_MASK_ADDR);
    volatile uint8_t *ptr =
        (volatile uint8_t *)(uintptr_t)RX8_IO32(RX8_SM_PTR_ADDR);

    /* First block — runs only while the state byte is 0. */
    if (RX8_IO8(RX8_SM_ST_ADDR) == 0) {
        uint8_t masked = RX8_IO8(RX8_SM_INP_ADDR) & mask;
        if (RX8_IO16(RX8_SM_MAGIC_ADDR) == 0xE926u) {
            if (masked != 0) {
                *ptr = RX8_IO8(RX8_SM_CNT_ADDR);
                if (RX8_IO8(RX8_SM_CNT_ADDR) == 7)
                    RX8_IO8(RX8_SM_LATCH_ADDR) =
                        (uint8_t)(RX8_IO16(RX8_SM_SRC_ADDR) >> 8);
                RX8_IO8(RX8_SM_ST_ADDR) = 1;
            } else {
                *ptr = 0;
                RX8_IO8(RX8_SM_ST_ADDR) = 2;
            }
        } else {
            if (masked == 0)
                *ptr = 0;
            RX8_IO8(RX8_SM_ST_ADDR) = 0;
        }
    }

    /* Second block — always runs.  out==0 latches (cmd == 1) and returns cmd;
     * out in {5,7} returns the latched flag; otherwise cmd unchanged. */
    uint8_t out = *ptr;
    if (out == 0) {
        RX8_IO8(RX8_SM_LATCH_ADDR) = (cmd == 1) ? 1 : 0;
        return cmd;
    }
    if (out == 5 || out == 7)
        return (RX8_IO8(RX8_SM_LATCH_ADDR) == 1) ? 1 : 0;
    return cmd;
}

/* setRegister_REG_BIT_VAL @0x4BBC — tiny 16-bit RMW leaf (verified by
 * c/tests/test_setRegister_REG_BIT_VAL.py).  Inlined for the same reason. */
static void ssv_reg_bit_val(uint16_t *reg, uint16_t mask, int enable)
{
    uint16_t v = *reg;
    v = enable ? (uint16_t)(v | mask) : (uint16_t)(v & (uint16_t)~mask);
    *reg = v;
}

/* 0x225C8 — SSV control task (void, no ABI args / no return value). */
void rx8_ssv_control(void)
{
    uint8_t mode = RX8_IO8(RX8_SSV_MODE_ADDR);

    /* 1. temperature hysteresis (0x225DC..0x225FC).  `!(on > t)` reproduces
     * the ROM's fcmp/gt + bt/s structure EXACTLY, including NaN / +inf which
     * take the command = 1 arm (see header).  The off threshold is the ROM's
     * runtime fadd on + hysteresis: 200.0 + (-3.0) = 197.0 exactly. */
    float t   = RX8_SSV_TEMP;
    float on  = ROM_SSV_ON;
    float off = on + ROM_SSV_HYSTERESIS;
    if (!(on > t)) {
        RX8_IO8(RX8_SSV_CMD_ADDR) = 1;      /* temp >= 200  (or NaN/+) */
    } else if (off > t) {
        RX8_IO8(RX8_SSV_CMD_ADDR) = 0;      /* temp < 197               */
    }
    /* else: hold the previous command in the band [197, 200) */

    /* 2. transition counter (0x225FE..0x2262C): reload 188 when the mode
     * drops 1 -> 0, otherwise count down while > 0. */
    if (mode == 0 && RX8_IO8(RX8_SSV_PREV_ADDR) == 1) {
        RX8_IO16(RX8_SSV_CNT_ADDR) = ROM_SSV_RELOAD;
    } else {
        uint16_t cnt = RX8_IO16(RX8_SSV_CNT_ADDR);
        if (cnt > 0)
            RX8_IO16(RX8_SSV_CNT_ADDR) = (uint16_t)(cnt - 1);
    }

    /* 3. enable gating (0x2262E..0x22668): the cal flag (0 in stock ROM),
     * the status byte, or (mode==0 && counter>0 && command==0).  The counter
     * and command reads are the POST-update values, as in the ROM. */
    uint8_t enable =
        (ROM_SSV_CAL_FLAG == 1) ||
        (RX8_IO8(RX8_SSV_STATUS_ADDR) == 1) ||
        (mode == 0 && RX8_IO16(RX8_SSV_CNT_ADDR) > 0 &&
         RX8_IO8(RX8_SSV_CMD_ADDR) == 0) ? 1u : 0u;

    /* 4. sensor state machine -> output byte (0x2266A..0x22672). */
    uint8_t out = ssv_sm_08(enable);
    RX8_IO8(RX8_SSV_OUT_ADDR) = out;

    /* 5. status word bit 0x80 = (out == 1) (0x22674..0x226A6).  The ROM
     * brackets each 0x4BBC call with setSR_PARAM @0x2054 /
     * loadStatusRegister_ADDR @0x2064 — pure SR save/restore through stack
     * locals with no RAM effect, omitted here (noted in the header). */
    ssv_reg_bit_val((uint16_t *)(uintptr_t)0xFFFFF754u, 0x80u, out == 1);

    /* 6. state store (0x226B0..0x226B2). */
    RX8_IO8(RX8_SSV_PREV_ADDR) = mode;
}

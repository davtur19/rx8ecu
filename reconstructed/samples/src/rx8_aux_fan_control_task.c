/*
 * =============================================================================
 * rx8_aux_fan_control_task.c  —  AUXILIARY (BOOST-PRESSURE) FAN CONTROL TASK
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x1AED2  |  Size: 48 bytes (0x1AED2..0x1AF02)
 * Status      : VERIFIED — behavioural equivalence to the ROM bytes held by
 *               reconstructed/samples/tests/harness_aux_fan_control_task.py
 *               (host-gcc vs tools/sh2emu.py over edge + N random vectors;
 *               bit-exact on every RAM side-effect cell, 0 mismatches).
 * Lift (truth): c/aux_fan_control_task.c  (listed in c/verified_addrs.txt;
 *               verified there via c/tests/test_aux_fan_control_task.py,
 *               6000 random runs vs the same emulator).
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * The OS task that drives the auxiliary (boost-pressure) cooling fan.  It runs
 * a small boost-sensor pipeline — a low-pass filter on the boost sensor, a
 * scaled first-difference, a second low-pass on that error, a float
 * register/global shuffle and a pressure hysteresis that decides whether the
 * fan flag is on or off — and, when that flag changes, publishes the new flag
 * plus a "request update" latch (0xFF / 0 / 0) to the fan subsystem.  The whole
 * chain is wrapped in a getSR(0x10)/setSR critical section that has no
 * observable RAM effect and is therefore not modelled here (same choice as the
 * lift).
 *
 * ROM PATH (SH-2 big-endian; the 48 bytes at 0x1AED2 are a dispatch stub)
 * ------------------------------------------------------------------------
 *     0x1AED2: 4F22  sts.l pr,@-r15
 *     0x1AED4: D352  mov.l @(0x1B020),r3       ; -> getSR (0x3920)
 *     0x1AED6: 7FFC  add  #0xFC,r15
 *     0x1AED8: 430B  jsr  @r3                  ; getSR(0x10)      (delay: mov #0x10,r4)
 *     0x1AEDC: D36C  mov.l @(0x1B090),r3       ; -> 0x32F42 (boost filter wrapper)
 *     0x1AEE0: 2F02  mov.l r0,@r15             ; save SR mask on the stack
 *     0x1AEE2: D26C  mov.l @(0x1B094),r2       ; -> 0x2DD6E (boost_delta_control)
 *     0x1AEE4: 420B  jsr  @r2                  ; (delay: nop)
 *     0x1AEE8: D36B  mov.l @(0x1B098),r3       ; -> 0x2DD88 (boost_error_abs_calc)
 *     0x1AEEA: 430B  jsr  @r3                  ; (delay: nop)
 *     0x1AEEE: D26B  mov.l @(0x1B09C),r2       ; -> 0x344FE (float register/global swap)
 *     0x1AEF0: 420B  jsr  @r2                  ; (delay: nop)
 *     0x1AEF4: D36A  mov.l @(0x1B0A0),r3       ; -> 0x3488C (pressure hysteresis)
 *     0x1AEF6: 430B  jsr  @r3                  ; (delay: nop)
 *     0x1AEFA: 64F6  mov.l @r15+,r4            ; r4 = saved SR mask
 *     0x1AEFC: D363  mov.l @(0x1B08C),r3       ; -> setSR (0x3934)
 *     0x1AEFE: 432B  jmp  @r3                  ; tail-call setSR(saved SR)
 *     0x1AF00: 4F26  lds.l @r15+,pr            ;   (delay slot) restore pr
 *
 * Each callee is a verified leaf of its own; the C below inlines their
 * semantics in the same execution order.  Details that matter for
 * bit-exactness:
 *
 *   * 0x32F42 boost wrapper:  fr7=1e-5@0x32F64, fr6=0.7@0x78CFC,
 *     fr5=RAM[0xFFFFBC1C], then jsr 0x23B0 (the verified first-order
 *     filter — `fmaf`, single rounding) on fr4=RAM[0xFFFFC008]; result
 *     stored back to RAM[0xFFFFC008].
 *   * 0x2DD6E delta control:  RAM[0xFFFFBD3C] = (RAM[0xFFFFC008] -
 *     RAM[0xFFFFBD40]) * 15.625@0x2DDB0  (two separate roundings: one fsub,
 *     one fmul), then RAM[0xFFFFBD40] = RAM[0xFFFFC008].
 *   * 0x2DD88 error wrapper:  filter(RAM[0xFFFFBD3C], RAM[0xFFFFBD38],
 *     0.5@0x76B30, 1e-5@0x2DDB8) -> RAM[0xFFFFBD38].
 *   * 0x344FE swap:  C0D8<-C104  C0DC<-C108  C0E0<-C10C  C108<-C12C
 *     C104<-B5B8  C10C<-ADC0  (plain f32 copies).
 *   * 0x3488C hysteresis + 0xC2E6 flag transition (see below).
 *
 * Build note: the inlined filter uses fmaf() (single-rounding fmac), which
 * needs `-lm` at link time — the same requirement as the standalone
 * rx8_first_order_filter.c sample.
 *
 * NaN / fcmp DISCREPANCY vs THE LIFT
 * ----------------------------------
 * The ROM hysteresis compares with SH-2 `fcmp/gt` (strict `>`), which is
 * FALSE for NaN operands.  The first decision is therefore `if (7000 > p) skip
 * else on`, i.e. a NaN pressure input falls through the "on" arm.  The lift's
 * `p >= 7000` is false for NaN and would wrongly HOLD instead.  This sample
 * keeps the ROM's branch structure (`!(7000 > p)` / `6500 > p`), so NaN trips
 * the flag ON exactly like the hardware; for all finite inputs it is
 * identical to the lift.  (The emulator-based lift test used only finite
 * uniform(-1000,1000) floats, so it never exercised NaN.)
 * =============================================================================
 */
#include <math.h>
#include <stdint.h>

/* ---------------------------------------------------------------------------
 * firstOrderFilter — ROM leaf @0x23B0, inlined verbatim from the verified
 * reconstructed sample rx8_first_order_filter.c (lift c/firstOrderFilter.c).
 * The ROM chain here jsr's it twice (via the 0x32F42 and 0x2DD88 wrappers);
 * inlining a known tiny leaf is the sanctioned modelling choice and keeps
 * this sample self-contained.  Signature: fr4=sig, fr5=sigprev, fr6=ff,
 * fr7=min; result in fr0.  Uses fmaf() to reproduce the single-rounding
 * `fmac` of the SH-2E FPU.
 * ------------------------------------------------------------------------- */
static float boost_first_order_filter(float sig, float sigprev, float ff,
                                      float min)
{
    /* Bootstrap: non-finite sigprev (exponent field all ones) -> pass sig. */
    if (!isfinite(sigprev))
        return sig;
    /* filtered = (1 - ff) * (sigprev - sig) + sig  (fused single rounding). */
    float filtered = fmaf(1.0f - ff, sigprev - sig, sig);
    /* Deadband: strictly-smaller change snaps the output back to sig. */
    return (min > fabsf(sig - filtered)) ? sig : filtered;
}

/* --- RAM cells the task reads and writes (SH-2 absolute addresses) ------- */
#define RAM_BOOST_IN     (*(volatile float *)0xFFFFC008) /* filtered boost   */
#define RAM_FILT_PREV    (*(volatile float *)0xFFFFBC1C) /* filter history   */
#define RAM_DELTA_PREV   (*(volatile float *)0xFFFFBD40) /* last sample      */
#define RAM_DELTA        (*(volatile float *)0xFFFFBD3C) /* scaled delta     */
#define RAM_ERR_PREV     (*(volatile float *)0xFFFFBD38) /* error filter     */
#define RAM_BOOST_P      (*(volatile float *)0xFFFFB5B8) /* pressure input   */

#define RAM_C104         (*(volatile float *)0xFFFFC104)
#define RAM_C108         (*(volatile float *)0xFFFFC108)
#define RAM_C10C         (*(volatile float *)0xFFFFC10C)
#define RAM_C0D8         (*(volatile float *)0xFFFFC0D8)
#define RAM_C0DC         (*(volatile float *)0xFFFFC0DC)
#define RAM_C0E0         (*(volatile float *)0xFFFFC0E0)
#define RAM_C12C         (*(volatile float *)0xFFFFC12C)
#define RAM_ADC0         (*(volatile float *)0xFFFFADC0)

#define RAM_BOOST_FLAG   (*(volatile uint8_t *)0xFFFFA38C) /* fan flag (u8)  */
#define RAM_A384         (*(volatile uint8_t *)0xFFFFA384) /* update latch   */
#define RAM_A385         (*(volatile uint8_t *)0xFFFFA385)
#define RAM_A324         (*(volatile uint8_t *)0xFFFFA324)

/* --- calibration constants read from the ROM ----------------------------- */
#define ROM_FF_FILTER    (*(const float *)0x78CFC) /* 0.7   boost filter     */
#define ROM_FF_ERROR     (*(const float *)0x76B30) /* 0.5   error filter     */
#define ROM_EPS          (*(const float *)0x32F64) /* 1e-5  deadband (also
                                                      @0x2DDB8, same value)  */
#define ROM_DELTA_SCALE  (*(const float *)0x2DDB0) /* 15.625                */
#define ROM_P_ON         (*(const float *)0x7A18C) /* 7000                  */
#define ROM_P_HY         (*(const float *)0x7A190) /* 500                   */

/* 0xC2E6 — publish a flag change.  Side effects happen ONLY when the value
 * actually changes (mov.b compare at 0xC2F6-0xC2FC); otherwise the function
 * is a no-op (the ROM still does the getSR/setSR bookkeeping, which has no
 * observable RAM effect).  The writes are A384=0xFF, A385=0, A324=0,
 * A38C=flag, in that order. */
static void flag_transition(uint8_t flag)
{
    if (RAM_BOOST_FLAG != flag) {
        RAM_A384 = 0xFF;
        RAM_A385 = 0;
        RAM_A324 = 0;
        RAM_BOOST_FLAG = flag;
    }
}

/* aux_fan_control_task @ 0x1AED2 */
void rx8_aux_fan_control_task(void)
{
    /* 0x32F42 — boost low-pass wrapper:
     *   RAM[0xFFFFC008] = firstOrderFilter(RAM[0xFFFFC008],
     *                       RAM[0xFFFFBC1C], 0.7, 1e-5) */
    RAM_BOOST_IN = boost_first_order_filter(RAM_BOOST_IN, RAM_FILT_PREV,
                                            ROM_FF_FILTER, ROM_EPS);

    /* 0x2DD6E — delta control: scaled first difference (fsub then fmul,
     * each one rounding — do NOT let the compiler fold them into an fma). */
    RAM_DELTA = (RAM_BOOST_IN - RAM_DELTA_PREV) * ROM_DELTA_SCALE;
    RAM_DELTA_PREV = RAM_BOOST_IN;

    /* 0x2DD88 — error filter wrapper:
     *   RAM[0xFFFFBD38] = firstOrderFilter(RAM[0xFFFFBD3C],
     *                       RAM[0xFFFFBD38], 0.5, 1e-5) */
    RAM_ERR_PREV = boost_first_order_filter(RAM_DELTA, RAM_ERR_PREV,
                                            ROM_FF_ERROR, ROM_EPS);

    /* 0x344FE — float register/global swap (six f32 copies). */
    RAM_C0D8 = RAM_C104;
    RAM_C0DC = RAM_C108;
    RAM_C0E0 = RAM_C10C;
    RAM_C108 = RAM_C12C;
    RAM_C104 = RAM_BOOST_P;
    RAM_C10C = RAM_ADC0;

    /* 0x3488C — pressure hysteresis, then 0xC2E6 on a change:
     *   fcmp/gt: !(7000 > p)  -> ON
     *   fcmp/gt:  6500 > p    -> OFF
     *   otherwise              -> hold.  NaN trips ON (fcmp is false). */
    float p = RAM_BOOST_P;
    if (!(ROM_P_ON > p))
        flag_transition(1);
    else if (ROM_P_ON - ROM_P_HY > p)
        flag_transition(0);
}

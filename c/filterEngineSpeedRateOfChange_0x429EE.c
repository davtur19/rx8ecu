/* filterEngineSpeedRateOfChange_0x429EE.c
 *
 * ROM: 60E0FC00 | Address: 0x429EE | Size: 0x164 (356) bytes per CSV range
 * 0x429EE..0x42B52.  Standalone prologue (mov.l r14/r13/r12/r11/r10,@-r15)
 * @0x429EE, rts+delay @0x42B4E/0x42B50, epilogue pops @0x42B46..0x42B50.
 * No sub-calls.  The code/mov.w/mov.l literal pool @0x42A3C..0x42B7A sits
 * inside the range.  The next function 0x42B52 starts exactly at the CSV end
 * (`fldi0 fr3 ; mov.w 0x42B5A,r3 ; rts` - a tiny zero-C914 stub).  CSV range
 * CORRECT, no phantom rows.
 *
 * ENTRY VERIFICATION: 0x429EE matches the CSV entry.  Valid entry: the ONLY
 * 32-bit ROM reference to 0x429EE is the function-pointer slot @0x1448C in
 * the engineControlCalculateTiming dispatcher (0x141FC) literal pool
 * (callgraph: 0x141FC -> 0x429EE filterEngineSpeedRateOfChange).  Preceding
 * function 0x429BC (getEngineSpeedRateOfChange) ends rts+delay @0x429EA/
 * 0x429EC, no fall-through.  CSV address IS the real entry point.
 *
 * SEMANTICS: magnitude-gated history filter over a sliding window of raw
 * rate-of-change samples.  The output is the current raw sample when the
 * input magnitude is small, and an increasingly older lagged sample as the
 * input magnitude grows; the history is then shifted and the current raw
 * sample pushed on the front.  This bounds/smooths the output slew as a
 * function of the input rate-of-change signal.
 *
 * Inputs:
 *   in  = f32@FFFFC908   (input rate, this call)
 *   cur = f32@FFFFC8F4   (current raw rate, written just before by the sibling
 *                         getEngineSpeedRateOfChange @0x429BC)
 * History (raw-rate samples):
 *   H[i] = f32@(0xFFFFC96C + 4*i) for i=0..9, H[10] = f32@FFFFC990
 *
 * Output selection (all fc-cmp/gt = FRn>FRm, so a NaN input clears T and
 * falls through to the oldest sample):
 *   in < 2.5            -> out = cur         (1 sample, current raw)
 *   2.5  <= in < 3.5    -> out = H[0]
 *   3.5  <= in < 4.5    -> out = H[1]
 *   4.5  <= in < 5.5    -> out = H[2]
 *   5.5  <= in < 6.5    -> out = H[3]
 *   6.5  <= in < 7.5    -> out = H[4]
 *   7.5  <= in < 8.5    -> out = H[5]
 *   8.5  <= in < 9.5    -> out = H[6]
 *   9.5  <= in < 10.5   -> out = H[7]
 *   10.5 <= in < 11.5   -> out = H[8]
 *   in >= 11.5          -> out = H[10] (oldest)
 *   f32@FFFFC8F0 = out
 * Band constants [2.5,3.5,4.5,5.5,6.5,7.5,8.5,9.5,10.5,11.5] are the ROM
 * mova f32 literals 0x40200000,0x40600000,0x40900000,0x40B00000,0x40D00000,
 * 0x40F00000,0x41080000,0x41180000,0x41280000,0x41380000 at 0x42AA0..0x42B74
 * and 0x42B5C.
 *
 * History shift (oldest-first; each step's source is the slot immediately
 * newer, so reads always see the pre-update value):
 *   H[10]=H[9]; H[9]=H[8]; ... ; H[1]=H[0]; H[0]=cur
 *
 * RAM r/w: reads C908(f32), C8F4(f32), C96C..C990(f32); writes C8F0(f32),
 * C96C..C990(f32).  No sub-calls.
 *
 * VERIFIED against the SH-2 emulator (tools/sh2emu.py,
 * roms/stock/60E0FC00.bin) in c/tests/test_filterEngineSpeedRateOfChange_0x429EE.py
 * - 0 mismatches over 5 seeds x 100000 iterations (byte-exact full post-call
 * RAM overlay + r0).
 */
#include <stdint.h>

/* ---- RAM globals (mov.w literals sign-extend to 0xFFFFxxxx) ---- */
#define IN_C908  (*(volatile float *)0xFFFFC908)  /* f32 input rate this call  */
#define CUR_C8F4 (*(volatile float *)0xFFFFC8F4)  /* f32 current raw rate      */
#define OUT_C8F0 (*(volatile float *)0xFFFFC8F0)  /* f32 filtered output       */
#define H_C96C   (*(volatile float *)0xFFFFC96C)  /* H[0] newest history slot  */
#define H_C970   (*(volatile float *)0xFFFFC970)  /* H[1]                      */
#define H_C974   (*(volatile float *)0xFFFFC974)  /* H[2]                      */
#define H_C978   (*(volatile float *)0xFFFFC978)  /* H[3]                      */
#define H_C97C   (*(volatile float *)0xFFFFC97C)  /* H[4]                      */
#define H_C980   (*(volatile float *)0xFFFFC980)  /* H[5]                      */
#define H_C984   (*(volatile float *)0xFFFFC984)  /* H[6]                      */
#define H_C988   (*(volatile float *)0xFFFFC988)  /* H[7]                      */
#define H_C98C   (*(volatile float *)0xFFFFC98C)  /* H[8]                      */
#define H_C990   (*(volatile float *)0xFFFFC990)  /* H[9] oldest history slot  */

void filterEngineSpeedRateOfChange_0x429EE(void)
{
    float cur = CUR_C8F4;                   /* fr-current, captured from C8F4   */
    float in  = IN_C908;
    float out;

    if (2.5f > in)                  out = cur;             /* fr5 path           */
    else if (3.5f > in)             out = H_C96C;
    else if (4.5f > in)             out = H_C970;
    else if (5.5f > in)             out = H_C974;
    else if (6.5f > in)             out = H_C978;
    else if (7.5f > in)             out = H_C97C;
    else if (8.5f > in)             out = H_C980;
    else if (9.5f > in)             out = H_C984;
    else if (10.5f > in)            out = H_C988;
    else if (11.5f > in)            out = H_C98C;
    else                            out = H_C990;

    OUT_C8F0 = out;

    /* shift register, oldest target first (source is next-newer slot) */
    H_C990 = H_C98C;
    H_C98C = H_C988;
    H_C988 = H_C984;
    H_C984 = H_C980;
    H_C980 = H_C97C;
    H_C97C = H_C978;
    H_C978 = H_C974;
    H_C974 = H_C970;
    H_C970 = H_C96C;
    H_C96C = cur;                           /* push current raw sample */
}
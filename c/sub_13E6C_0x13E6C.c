/* sub_13E6C_0x13E6C.c
 *
 * ROM: 60E1D400 | Address: 0x13E6C | Size: 0x66 (102) bytes per CSV range
 * 0x13E6C..0x13ED2.  Code ends at the `rts` @0x13ECE (delay nop @0x13ED0);
 * the literal pool for this function sits @0x13F1E..0x13F3C (mov.w/mov.l
 * PC-relative loads at 0x13E70/0x13E72/0x13E76/0x13E78/0x13E84/0x13E86/
 * 0x13E88/0x13E8C/0x13E9C/0x13EB0/0x13EB6/0x13EB8/0x13EC0/0x13EC4).  The next
 * function 0x13ED2 (clamp_correction helper per the ignition pipeline) starts
 * at the CSV end address, so the range is clean.
 *
 * Entry  : 0x13E6C — matches the symbols CSV row (0x013E6C,0x013ED2).  Valid
 *           prologue (sts.l pr,@-r15 / add #0xFC,r15) and rts+delay @0x13ECE/
 *           0x13ED0.  No branch enters the body from mid-function.  It is a
 *           plain subroutine (no function-pointer dispatch slot): the only
 *           ROM references are FLOW references — `bsr 0x13E6C` from
 *           updateKnockMaxRAM (0x13B90) @0x13BBA and from the ignition phase
 *           helper calc_ignition_all_rotors (0x13C2C context).  The CSV
 *           address IS the real entry point.
 *
 * NAME DISCREPANCY (documented, decision): the symbols CSV row named this
 * entry `calc_fuel_pump_control_output` (ida-ai).  The real semantics — a
 * saturating clamp helper whose lower bound comes from a 1D table lookup on
 * the RPM@0xFFFFB5B8 axis, used as the final knock/ignition "correction
 * clamp" by updateKnockMaxRAM and calc_ignition_all_rotors — has NOTHING to
 * do with the fuel pump.  The fuel-pump name family is already used by real
 * fuel-pump functions elsewhere in this bank (calc_fuel_pump_pwm_output
 * 0x011EEA, calc_fuel_pump_duty_trim 0x0135F6, fuel_pump_speed_controller
 * 0x01B5A8, fuel_pump_control_3EFEA, ...).  DECISION: rename to sub_13E6C
 * (as the two verified callers updateKnockMaxRAM.c and calc_ignition_all_
 * rotors.c already refer to it), keeping the clamp semantics documented in
 * this header.  Both symbols CSVs are renamed accordingly (source -> c-lift).
 *
 * Range  : 0x13E6C .. 0x13ED2
 *
 * Literal pool (values verified against roms/stock/60E1D400.bin):
 *   0x13F1E 0xB5B8        (mov.w -> f32 lookup axis/RPM @0xFFFFB5B8)
 *   0x13F20 0xBB55        (mov.w -> u8 status byte @0xFFFFBB55)
 *   0x13F22 0xB5A4        (mov.w -> u8 status byte @0xFFFFB5A4)
 *   0x13F24 0xBCA9        (mov.w -> u8 status byte @0xFFFFBCA9)
 *   0x13F28 0x00079838    (u8 table-select threshold = 5)
 *   0x13F2C 0x0006B678    (1D descriptor A  — 4-pt u8 table)
 *   0x13F30 0x0006B664    (1D descriptor B  — 5-pt u8 table)
 *   0x13F34 0x00002068    (table1D_lookup leaf, c/lib/f_2068)
 *   0x13F38 0x00079878    (f32 0.0  — clamp upper bound)
 *   0x13F3C 0x00002404    (saturate/clamp leaf 0x2404, c/lib/f_2404.c)
 *
 * Semantics (instruction-for-instruction, see disasm):
 *   fr4@entry = v (the correction / signal to clamp).
 *   fr4saved   = v  (fmov.s fr4,@r15 @0x13E72)
 *   fr4        = f32@0xFFFFB5B8            ; lookup axis (RPM)
 *   status  = u8@0xFFFFB5A4
 *   selected table desc:
 *     if status == 1  &&  (u32)s8(u8@BCA9) >= (u32)s8(u8@0x79838)
 *                                         -> r4 = 0x6B678   (delay mov.b loads
 *                                            r4 = s8 u8@BB55 on that path)
 *     else if status != 0                 -> r4 = 0x6B664
 *     else if (u8@BB55 > 5) || (u8@BB55 == 0) -> r4 = 0x6B664
 *     else                                -> r4 = 0x6B678
 *   lower = table1D_lookup(desc, f32@B5B8) ; jsr 0x2068
 *   upper = f32@0x00079878 (0.0f)
 *   out   = clamp(v, lower, upper)             ; jsr 0x2404
 *   return fr0 = out
 *
 * VERIFIED against the SH-2 emulator (tools/sh2emu.py) in
 * c/tests/test_sub_13E6C_0x13E6C.py — 0 mismatches over 5 seeds x 100000
 * (byte-exact full post-call RAM overlay + fr0 compared).
 */
#include <stdint.h>

/* 1D table descriptor layout (see c/calc_ignition_all_rotors_13C2C.c). */
typedef struct {
    uint16_t     count;
    uint8_t      type;
    uint8_t      _pad;
    const void  *axis_x;
    const void  *values;
    /* scale and offset follow only if type != 0 */
} Table1D;

/* 0x002068 — table1D_lookup (generic 1D table lookup). r4=descriptor, fr4=x. */
extern float table1D_lookup(const Table1D *desc, float x);

/* ---- RAM globals (mov.w sign-extends to 0xFFFFxxxx) ---- */
#define RAM_AXIS_B5B8 (*(volatile float  *)0xFFFFB5B8)  /* f32 lookup axis (RPM) */
#define RAM_ST_B5A4   (*(volatile uint8_t*)0xFFFFB5A4)  /* u8 table-select status */
#define RAM_ST_BB55   (*(volatile uint8_t*)0xFFFFBB55)  /* u8 table-select status */
#define RAM_ST_BCA9   (*(volatile uint8_t*)0xFFFFBCA9)  /* u8 table-select status */

/* ROM constants */
#define CAL_THRESH    (*(volatile uint8_t*)0x00079838)  /* u8 5  (table-select thr) */
#define CAL_UPPER     (*(volatile float  *)0x00079878)  /* f32 0.0 (clamp upper)    */
#define DESC_A        ((const Table1D *)0x0006B678)
#define DESC_B        ((const Table1D *)0x0006B664)

/* c/2Lookup.c clamp leaf (0x2404): fr4=sig, fr5=lower, fr6=upper. */
static float clamp_sat(float sig, float lower, float upper)
{
    if (sig < lower) return lower;
    if (sig > upper) return upper;
    return sig;
}

float sub_13E6C(float v)
{
    const Table1D *desc;
    uint8_t status = RAM_ST_B5A4;                 /* u8@B5A4 */
    uint8_t bca9   = RAM_ST_BCA9;                 /* u8@BCA9 */
    uint8_t bb55   = RAM_ST_BB55;                 /* u8@BB55 */
    uint8_t thr    = CAL_THRESH;                  /* u8@0x79838 = 5 */

    /* cmp/hs on sign-extended s8 (mov.b) then unsigned u32 compare. */
    if (status == 1 &&
        ((uint32_t)(int32_t)(int8_t)bca9) >= ((uint32_t)(int32_t)(int8_t)thr))
        desc = DESC_A;
    else if (status != 0)
        desc = DESC_B;
    else if (bb55 > thr || bb55 == 0)
        desc = DESC_B;
    else
        desc = DESC_A;

    float rpm   = RAM_AXIS_B5B8;                  /* fr4 @0xFFFFB5B8 */
    float lower = table1D_lookup(desc, rpm);      /* jsr @0x2068 */
    float upper = CAL_UPPER;                      /* f32@0x79878 = 0.0 */

    return clamp_sat(v, lower, upper);            /* jsr @0x2404 */
}
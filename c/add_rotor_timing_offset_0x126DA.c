/* add_rotor_timing_offset_0x126DA.c
 *
 * ROM: 60E1D400 | Address: 0x126DA | Size: 16 bytes (0x126DA..0x126EA)
 *
 * Entry  : 0x126DA — matches the symbols CSV row (0x0126DA,0x0126EA).
 *           Tiny leaf (uses only r1/r2/r3 + fr2/fr3), terminated by `rts` +
 *           delay-slot store (0x126E6/0x126E8).  The ONLY ROM reference to
 *           0x126DA is the function-pointer slot @0x14860 in the dispatcher
 *           literal pool (engineControlCalculateTiming 0x14584) — the dispatch
 *           slot right after calc_rotor_B_pressure_load (0x127DE @0x1485C).
 *           No branches enter the body from mid-function; calc_rotor_A_pressure_load
 *           (0x126EA) starts right at 0x126EA, and the preceding A function
 *           ends with `rts` @0x126D6.  The CSV address IS the real entry point.
 * Range  : 0x126DA .. 0x126EA   (calc_rotor_A_pressure_load 0x126EA at the end).
 *
 * Literal pool (values verified against roms/stock/60E1D400.bin):
 *   0x1274C -> 0xFFFFA664   (mov.l f32 input)     read
 *   0x12750 -> 0xFFFFA65C   (mov.l f32 input)     read
 *   0x1271C -> 0xA648       (mov.w, sign-extended to 0xFFFFA648)  write
 *
 * Semantics (instruction-for-instruction, see disasm):
 *   fr3 = f32@0xFFFFA664;            ; fmov.s @r2,fr3
 *   fr2 = f32@0xFFFFA65C;            ; fmov.s @r1,fr2
 *   fr2 = fr2 + fr3;                 ; fadd fr3,fr2 (single-rounded ts())
 *   f32@0xFFFFA648 = fr2;            ; fmov.s fr2,@r3 (rts delay slot @0x126E8)
 *
 * The two inputs are the calc_rotor_B_pressure_load output (f32@A65C) added to
 * the rotor-A knock flag output (f32@A664, see write_rotor_A_knock_flag_0x128FE);
 * the result feeds the f32@A648 timing-offset used by the rotor timing chain.
 * Pure f32 add, no branches, no sub-calls, no NaN special-casing (NaNs propagate
 * via IEEE fadd exactly as the emulator does).
 *
 * VERIFIED against the SH-2 emulator (tools/sh2emu.py) in
 * c/tests/test_add_rotor_timing_offset_0x126DA.py — 0 mismatches over
 * 5 seeds x 100000 iterations (byte-exact full post-call RAM overlay).
 */
#include <stdint.h>

/* ---- RAM globals (mov.l / mov.w literals; mov.w sign-extends to 0xFFFFxxxx) ---- */
#define IN_A664 (*(volatile float *)0xFFFFA664)  /* f32 rotor-A knock-flag output */
#define IN_A65C (*(volatile float *)0xFFFFA65C)  /* f32 rotor-B pressure-load output */
#define OUT_A648 (*(volatile float *)0xFFFFA648) /* f32 rotor timing-offset output */

void add_rotor_timing_offset_0x126DA(void)
{
    float a = IN_A664;      /* fmov.s @r2,fr3 @0x126DE */
    float b = IN_A65C;      /* fmov.s @r1,fr2 @0x126E0 */
    float s = a + b;        /* fadd fr3,fr2 @0x126E2 (single-rounded) */
    OUT_A648 = s;           /* fmov.s fr2,@r3 (delay @0x126E8) */
}
/* add_fuel_pressure_correction_0x126CA.c
 *
 * ROM: 60E1D400 | Address: 0x126CA | Size: 16 bytes (0x126CA..0x126DA)
 *
 * Entry  : 0x126CA — matches the symbols CSV row (0x0126CA,0x0126DA).
 *           Tiny leaf (no stack frame — uses only r1/r2/r3 + fr2/fr3, no
 *           non-volatile regs), terminated by `rts` + delay-slot store
 *           (0x126D6/0x126D8).  The ONLY ROM reference to 0x126CA is the
 *           function-pointer slot @0x1484C in the dispatcher literal pool
 *           (engineControlCalculateTiming 0x14584) — the dispatch slot right
 *           after calc_rotor_A_pressure_load (0x126EA @0x14848).  No branches
 *           enter the body from mid-function; the preceding function ends with
 *           `rts` @0x126C6 so there is no fall-through into 0x126CA.  The CSV
 *           address IS the real entry point.
 * Range  : 0x126CA .. 0x126DA   (add_rotor_timing_offset 0x126DA starts at the
 *           CSV end; calc_rotor_A_pressure_load 0x126EA follows).
 *
 * Literal pool (values verified against roms/stock/60E1D400.bin):
 *   0x12744 -> 0xFFFFA654   (mov.l f32 input)     read
 *   0x12748 -> 0xFFFFA64C   (mov.l f32 input)     read
 *   0x12720 -> 0xA640       (mov.w, sign-extended to 0xFFFFA640)  write
 *
 * Semantics (instruction-for-instruction, see disasm):
 *   fr3 = f32@0xFFFFA654;            ; fmov.s @r2,fr3
 *   fr2 = f32@0xFFFFA64C;            ; fmov.s @r1,fr2
 *   fr2 = fr2 + fr3;                 ; fadd fr3,fr2 (single-rounded ts())
 *   f32@0xFFFFA640 = fr2;            ; fmov.s fr2,@r3 (rts delay slot @0x126D8)
 *
 * The two inputs are the calc_rotor_A_pressure_load output (f32@A64C) added to
 * the knock-detect flag output (f32@A654, see write_knock_detected_flag_0x128C4);
 * the result feeds the intake-pressure correction reference f32@A640 (see
 * calc_intake_pressure_pid_output_0x1252C).  Pure f32 add, no branches, no
 * sub-calls, no NaN special-casing (NaNs propagate via IEEE fadd exactly as the
 * emulator does).
 *
 * VERIFIED against the SH-2 emulator (tools/sh2emu.py) in
 * c/tests/test_add_fuel_pressure_correction_0x126CA.py — 0 mismatches over
 * 5 seeds x 100000 iterations (byte-exact full post-call RAM overlay).
 */
#include <stdint.h>

/* ---- RAM globals (mov.l / mov.w literals; mov.w sign-extends to 0xFFFFxxxx) ---- */
#define IN_A654 (*(volatile float *)0xFFFFA654)  /* f32 rotor knock-detect flag output */
#define IN_A64C (*(volatile float *)0xFFFFA64C)  /* f32 rotor-A pressure-load output */
#define OUT_A640 (*(volatile float *)0xFFFFA640) /* f32 fuel-pressure correction output */

void add_fuel_pressure_correction_0x126CA(void)
{
    float a = IN_A654;      /* fmov.s @r2,fr3 @0x126CE */
    float b = IN_A64C;      /* fmov.s @r1,fr2 @0x126D0 */
    float s = a + b;        /* fadd fr3,fr2 @0x126D2 (single-rounded) */
    OUT_A640 = s;           /* fmov.s fr2,@r3 (delay @0x126D8) */
}
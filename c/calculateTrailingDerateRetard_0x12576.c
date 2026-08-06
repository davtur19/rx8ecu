/* calculateTrailingDerateRetard_0x12576.c
 *
 * ROM: 60E0FC00 | Address: 0x12576 | Size: 0x3A (58) bytes per CSV range
 * 0x12576..0x125B0.  Code runs to the `rts` @0x125AC (delay fmov.s @r15+,fr12
 * @0x125AE); the next function (defaultTimingMinMax) starts at 0x125B0.  The
 * CSV range is CORRECT (code to 0x125AE, next function exactly at 0x125B0) —
 * no correction needed.
 *
 * ENTRY VERIFICATION: 0x12576 matches the symbols CSV start.  Valid entry:
 * opens with the same prologue as the leading twin (`fmov.s fr12,@-r15 ;
 * sts.l pr,@-r15`).  The preceding function calculateLeadingDerateRetard
 * (0x1253C) ends with `rts` @0x12572 (delay @0x12574), so no fall-through
 * into us; no incoming branches into the middle (whole-ROM scan found none —
 * the only brute hits were data-pool false positives @0x1172A/@0x1173E).
 * Called via the function-pointer slot @0x144D0 of the
 * engineControlCalculateTiming dispatcher (0x141FC) dispatch table — the slot
 * between calculateTrailingTimingDerateCompensated @0x144CC and
 * calculateTrailingTimingBaseFinal @0x144D4.  The ROM literal @0x144D0 is the
 * ONLY 32-bit reference to 0x12576 in the binary.  The CSV address IS the
 * real entry point.
 *
 * SEMANTICS: byte-for-byte the structural twin of calculateLeadingDerateRetard
 * (0x1253C) with +4-shifted RAM addresses.  The body is transcribed from the
 * actual disassembly (NOT copied from the leading twin):
 *
 *   x  = f32@A728 - f32@A6A0                   ; fsub fr3,fr2
 *   x  = x - saturateLow_0x23E4(f32@A754, f32@C8A4)   ; jsr @0x23E4 (leaf)
 *   x  = x + f32@A5E8                          ; fadd fr3,fr12
 *   x  = x + f32@B2E8                          ; fadd fr2,fr12
 *   x  = x - f32@A664                          ; fsub fr1,fr12
 *   f32@A654 = x
 *
 * saturateLow @0x23E4 = (fr4 > fr5) ? fr4 : fr5 (max; NaN sig -> lower).
 * r0 is not touched by this function or by the 0x23E4 leaf, so r0 on return
 * is the value it held at entry (0 in the isolated-call harness).
 *
 * TWIN COMPARISON (leading 0x1253C vs trailing 0x12576) — exact differences,
 * verified byte-by-byte:
 *   diff minuend base   f32@FFFFA69C           f32@FFFFA6A0  (+4)
 *   diff minuend        f32@FFFFA724           f32@FFFFA728  (+4)
 *   leaf lower/limit    f32@FFFFC8A0           f32@FFFFC8A4  (+4)
 *   leaf sig            f32@FFFFA750           f32@FFFFA754  (+4)
 *   addend 1            f32@FFFFA5E4           f32@FFFFA5E8  (+4)
 *   addend 2            f32@FFFFB2E4           f32@FFFFB2E8  (+4)
 *   subtrahend          f32@FFFFA660           f32@FFFFA664  (+4)
 *   output              f32@FFFFA644           f32@FFFFA654  (+0x10)
 *   shared: helper 0x23E4 (saturateLow, mov.l @0x12634), the mov.w pool
 *   region @0x12608..0x12622, prologue, epilogue, r0 result (untouched).
 *
 * LITERAL POOL (values verified against roms/stock/60E0FC00.bin):
 *   mov.w 0x12616=0xA6A0, 0x12618=0xA728, 0x1261A=0xC8A4, 0x1261C=0xA754,
 *   0x1261E=0xA5E8, 0x12620=0xB2E8, 0x12622=0xA664 (own; the first 7 mov.w
 *   literals @0x12608..0x12614 belong to the leading twin)
 *   mov.l 0x12634=0x000023E4 (saturateLow, shared), 0x1263C=0xFFFFA654 (out)
 * RAM r/w: reads A6A0, A728, C8A4, A754, A5E8, B2E8, A664; writes A654.
 * ROM read: the literal pool above.  No other sub-calls.
 * Sub-calls: saturateLow @0x23E4 (x1, verified in c/math_primitives.c).
 *
 * VERIFIED against the SH-2 emulator (tools/sh2emu.py, 60E0FC00.bin) in
 * c/tests/test_calculateTrailingDerateRetard_0x12576.py — 0 mismatches over
 * 5 seeds x 100000 iterations (byte-exact full post-call RAM overlay + r0).
 */
#include <stdint.h>
#include <math.h>

/* ---- RAM globals (mov.w literals sign-extend to 0xFFFFxxxx) ---- */
#define RAM_A6A0  (*(volatile float *)0xFFFFA6A0)  /* f32 diff minuend base   */
#define RAM_A728  (*(volatile float *)0xFFFFA728)  /* f32 diff minuend        */
#define RAM_C8A4  (*(volatile float *)0xFFFFC8A4)  /* f32 leaf lower/limit    */
#define RAM_A754  (*(volatile float *)0xFFFFA754)  /* f32 leaf sig            */
#define RAM_A5E8  (*(volatile float *)0xFFFFA5E8)  /* f32 addend 1            */
#define RAM_B2E8  (*(volatile float *)0xFFFFB2E8)  /* f32 addend 2            */
#define RAM_A664  (*(volatile float *)0xFFFFA664)  /* f32 subtrahend          */
#define OUT_A654  (*(volatile float *)0xFFFFA654)  /* f32 trailing derate-ret */

/* ---- External helper (in ROM, verified separately) ---- */
extern float saturateLow(float sig, float lower);  /* @0x23E4 max(sig, lower); NaN sig -> lower */

void calculateTrailingDerateRetard_0x12576(void)
{
    float x;

    /* x = f32@A728 - f32@A6A0   (fsub fr3,fr2 ; fr2=A728, fr3=A6A0) */
    x = RAM_A728 - RAM_A6A0;

    /* x -= saturateLow(f32@A754, f32@C8A4)  (jsr @0x23E4 -> fr0, fsub fr0,fr12) */
    x = x - saturateLow(RAM_A754, RAM_C8A4);

    /* x += f32@A5E8 ; x += f32@B2E8 ; x -= f32@A664 */
    x = x + RAM_A5E8;
    x = x + RAM_B2E8;
    x = x - RAM_A664;

    /* publish f32@A654 */
    OUT_A654 = x;
}
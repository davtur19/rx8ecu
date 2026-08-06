/* calc_rotor_A_pressure_load_0x126EA.c
 *
 * ROM: 60E1D400 | Address: 0x126EA | Size: 0xF4 (244) bytes per CSV range
 * 0x126EA..0x127DE.  64 code instrs (0x126EA..0x127DC, rts+delay at
 * 0x127DA/0x127DC) + interleaved mov.w literal pools @0x1270C..0x12724
 * (jumped over by bra 0x1276C@0x12708) and @0x1283A..0x1284A (accessed by
 * mov.w 0x12770/0x127A6/0x127A8/0x127B0/0x127B8/0x127BC/0x127C4), plus
 * mov.l literals @0x12754/0x12758 (first block) and @0x1284C..0x1286A
 * (read by mov.l 0x1275C/0x1276C/0x1277C/0x12786/0x12788/0x12798/0x1279C/
 * 0x127D0).  The 0x1283A..0x1286A pool is SHARED with the rotor-B twin
 * 0x127DE and sits inside the range the CSV attributes to this function.
 *
 * Entry  : 0x126EA — matches the symbols CSV row.  Valid standalone prologue
 *           (mov.l r14,@-r15 ; fmov.s fr15,@-r15 ; sts.l pr,@-r15), rts+delay
 *           at 0x127DA/0x127DC.  The ONLY ROM reference to 0x126EA is the
 *           function-pointer slot @0x14848 inside the dispatcher
 *           engineControlCalculateTiming (0x14584) literal pool — dispatch
 *           slot for calc_rotor_A_pressure_load (c/engineControlCalculateTiming.c
 *           line 265).  No code branches into the body from mid-function, so
 *           the CSV address IS the real entry point.
 * Range  : 0x126EA .. 0x127DE  (rotor-B twin @0x127DE starts right at the CSV end)
 *
 * Literal pool (values verified against roms/stock/60E1D400.bin):
 *   0x1270C=0xB5B8, 0x12722=0xA7BC     (mov.w RAM addrs, sign-extended)
 *   0x12754 -> 0x0006E3F4   (f32 10000.0 — high-threshold offset)
 *   0x12758 -> 0xFFFFA66C   (u8 flag, read+write)
 *   0x1283A=0xAADA          (mov.w u8 rotor gate)
 *   0x1283C=0xA718, 0x1283E=0xA5F4, 0x12840=0xCB0C,
 *   0x12842=0xA5EC, 0x12844=0xA790, 0x12846=0xA788  (mov.w RAM lerp addrs)
 *   0x1284C -> 0x0006E3F8   (f32 100.0 — band width)
 *   0x12850 -> 0xFFFFA650   (f32 intermediate filter output)
 *   0x12854 -> 0xFFFFA66C   (u8 flag again)
 *   0x12858 -> 0x0006E3DC   (f32 0.05 — gate decay step)
 *   0x1285C -> 0x000023E4   (helper = max(fr4,fr5))
 *   0x12860 -> 0x0006E3E0   (f32 1.0 — gate-else addend)
 *   0x12864 -> 0x000023F4   (helper = min(fr4,fr5))
 *   0x12868 -> 0xFFFFA64C   (f32 rotor-A pressure-load output)
 *
 * Semantics (instruction-for-instruction, see disasm):
 *   fr4 = f32@0xFFFFB5B8;                  ; raw input
 *   fr5 = f32@0xFFFFA7BC + 10000.0f;       ; high threshold
 *   u8@0xFFFFA66C = (fr4 >= fr5) ? 1       ; fcmp/gt fr4,fr5 -> T=(fr5>fr4),
 *                  : (fr4 < fr5-100.0f) ? 0 ; bt/s on T==1 ; bf/s on T==0
 *                  : (unchanged);            ; hysteresis band [low, high)
 *   x = f32@0xFFFFA650;
 *   if (u8@0xFFFFAADA == 1 && u8@0xFFFFA66C == 0)
 *       x = max(0x23E4)(x - 0.05f, 0.0f);  ; gate active: ramp toward 0
 *   else
 *       x = min(0x23F4)(1.0f + x, 1.0f);   ; else: ramp toward 1.0
 *   f32@0xFFFFA650 = x;
 *   S = f32@CB0C + f32@A718 + f32@A5F4;    ; (A718+A5F4)+CB0C, single-rounded
 *   f32@0xFFFFA64C = (1-x)*S + x*f32@A5EC + f32@A790 - f32@A788;
 *       ; computed as fmac((1-x), S, x*A5EC) then +A790 then -A788
 *
 *   NaN semantics (matches the emulator byte-for-byte):
 *     fcmp/gt clears T on NaN.  First check is `bt/s` (branch on T==1), so a
 *     NaN fr4 or NaN fr5 makes T=0 -> falls through to store 1.  Second check
 *     is `bf/s` (branch on T==0), so NaN -> flag retains (dead for real
 *     inputs: reaching the second check needs fr4>fr5 -> fr4>fr5-100 always).
 *     The 0x23E4/0x23F4 leaves are pure fcmp — NaN fr4 reads as "the other
 *     operand wins".
 *
 *   Structure is the twin of calc_rotor_B_pressure_load_0x127DE — the ONLY
 *   differences are the RAM addresses for the flag byte (A66C vs A66D), the
 *   intermediate filter (A650 vs A660), the lerp inputs (A718/A5F4/CB0C/
 *   A5EC/A790/A788 vs A71C/A5F8/CB10/A5F0/A794/A78C), the final output
 *   (A64C vs A65C) and the ROM constant addresses for the decay/add steps
 *   (6E3DC/6E3E0 vs 6E410/6E414 — both 0.05f and 1.0f).  The raw input
 *   (B5B8), threshold base (A7BC), threshold consts (6E3F4/6E3F8) and gate
 *   (AADA) are identical.
 *
 * VERIFIED against the SH-2 emulator (tools/sh2emu.py) in
 * c/tests/test_calc_rotor_A_pressure_load_0x126EA.py — 0 mismatches over
 * 5 seeds x default iterations (full post-call RAM overlay, byte-exact).
 */

#include <stdint.h>

/* 0x23E4 — max leaf: r0/fr0 = larger of fr4, fr5 (NaN fr4 -> fr5).
 * 0x23F4 — min leaf: r0/fr0 = smaller of fr4, fr5 (NaN fr4 -> fr5). */
extern float fmax_0x23E4(float a, float b);
extern float fmin_0x23F4(float a, float b);

/* ---- RAM globals (mov.w literals sign-extend to 0xFFFFxxxx) ---- */
#define T_B5B8   (*(volatile float   *)0xFFFFB5B8)  /* f32 raw input */
#define T_A7BC   (*(volatile float   *)0xFFFFA7BC)  /* f32 threshold base */
#define G_AADA   (*(volatile uint8_t *)0xFFFFAADA)  /* u8 rotor gate (==1) */
#define FLAG     (*(volatile uint8_t *)0xFFFFA66C)  /* u8 flag (read+write) */
#define MID_A650 (*(volatile float   *)0xFFFFA650)  /* f32 intermediate filter */
#define S_1_A718 (*(volatile float   *)0xFFFFA718)  /* f32 lerp S term 1 */
#define S_2_A5F4 (*(volatile float   *)0xFFFFA5F4)  /* f32 lerp S term 2 */
#define S_3_CB0C (*(volatile float   *)0xFFFFCB0C)  /* f32 lerp S term 3 */
#define T_A5EC   (*(volatile float   *)0xFFFFA5EC)  /* f32 lerp x term */
#define U_A790   (*(volatile float   *)0xFFFFA790)  /* f32 lerp addend */
#define V_A788   (*(volatile float   *)0xFFFFA788)  /* f32 lerp subtrahend */
#define OUT_A64C (*(volatile float   *)0xFFFFA64C)  /* f32 rotor-A pressure load */

/* ROM constants */
#define ROM_F3F4 (*(volatile float *)0x0006E3F4)  /* f32 10000.0 (high offset) */
#define ROM_F3F8 (*(volatile float *)0x0006E3F8)  /* f32 100.0 (band width) */
#define ROM_F3DC (*(volatile float *)0x0006E3DC)  /* f32 0.05 (gate decay step) */
#define ROM_F3E0 (*(volatile float *)0x0006E3E0)  /* f32 1.0 (gate-else addend) */

void calc_rotor_A_pressure_load_0x126EA(void)
{
    float fr4 = T_B5B8;                  /* fmov.s @r2,fr4 @0x126F2 */
    float fr5 = T_A7BC + ROM_F3F4;       /* fadd fr3,fr5 @0x126FE -> high */

    /* 0x12700..0x1276A: flag hysteresis on u8@A66C.  fcmp/gt fr4,fr5 sets
     * T=(fr5>fr4); `bt/s 0x1275C` branches on T==1 (fr5>fr4, i.e. fr4<high)
     * to the second check; the fall-through stores 1.  Second check recomputes
     * low=high-100 and `bf/s 0x1276C` branches on T==0 (fr4>=low, retain);
     * the fall-through stores 0.  So: fr4>=high -> 1, fr4<low -> 0,
     * low<=fr4<high -> retain.  NaN -> both T=0 -> flag=1. */
    if (fr5 > fr4) {                     /* bt/s taken (fr4 < high) */
        float low = fr5 - ROM_F3F8;      /* fsub fr2,fr5 @0x12760 */
        if (low > fr4) {                 /* bf/s NOT taken (fr4 < low) */
            FLAG = 0;                    /* mov.b r0,@r4 @0x1276A */
        }
        /* else bf/s taken @0x12764: flag byte keeps its pre-call value */
    } else {
        FLAG = 1;                        /* mov.b r1,@r4 (bra delay @0x1270A) */
    }

    /* 0x1276C..0x127A4: rate-limit the intermediate value f32@A650. */
    {
        float x = MID_A650;              /* fmov.s @r14,fr4 (delay @0x1277A) */
        float v;
        if (G_AADA == 1 && FLAG == 0) {  /* cmp/eq #1 ; tst ; bf/s x2 */
            /* jsr @0x23E4 = max(fr4,fr5) with fr4=x-0.05, fr5=0.0 */
            v = fmax_0x23E4(x - ROM_F3DC, 0.0f);   /* fsub @0x1278C, fldi0 */
        } else {
            /* jsr @0x23F4 = min(fr4,fr5) with fr4=1.0+x, fr5=1.0 */
            v = fmin_0x23F4(ROM_F3E0 + x, 1.0f);   /* fadd @0x1279E, fmov fr15,fr5 */
        }
        MID_A650 = v;                    /* fmov.s fr0,@r14 @0x127A4 */
    }

    /* 0x127A6..0x127D4: per-rotor pressure-load lerp into f32@A64C.
     *   S = (A718+A5F4)+CB0C ;  x = A650
     *   out = fmac((1-x), S, x*A5EC) + A790 - A788
     * fmac is fused: fr2 = ts(fr0*fr3 + fr2) with single rounding. */
    {
        float x = MID_A650;              /* fmov.s @r14,fr2 @0x127B4 */
        float S = (S_1_A718 + S_2_A5F4) + S_3_CB0C;  /* fadd x2 @0x127AE/0x127B6 */
        float comp = 1.0f - x;           /* fsub fr2,fr15 @0x127BA */
        float acc = x * T_A5EC;          /* fmul fr0,fr2 @0x127C2 */
        acc = comp * S + acc;            /* fmac fr0,fr3,fr2 @0x127CA (fused) */
        acc = acc + U_A790;              /* fadd fr3,fr2 @0x127CE */
        acc = acc - V_A788;              /* fsub fr1,fr2 @0x127D2 */
        OUT_A64C = acc;                  /* fmov.s fr2,@r3 @0x127D4 */
    }
}

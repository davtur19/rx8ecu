/* calc_rotor_B_pressure_load_0x127DE.c
 *
 * ROM: 60E1D400 | Address: 0x127DE | Size: 0xE6 (230) bytes per CSV range
 * 0x127DE..0x128C4.  60 code instrs (0x127DE..0x128C2, rts+delay at
 * 0x128C0/0x128C2) + interleaved mov.w literal pool @0x1283A..0x1284A
 * (SHARED with the rotor-A twin 0x126EA; read by mov.w 0x127E4/0x127EC/
 * 0x12814) and @0x12984..0x1298E (read by mov.w 0x1288C/0x12890/0x12894/
 * 0x1289C/0x128A0/0x128A8 — physically inside the NEXT CSV range that the
 * catalog attributes to calc_combustion_chamber_temp 0x12938, which jumps
 * over it), plus mov.l literals @0x1286C..0x12878 (first block) and
 * @0x129B0..0x129B8 (read by mov.l 0x1287C/0x12880/0x128B4).
 *
 * Entry  : 0x127DE — matches the symbols CSV row.  Valid standalone prologue
 *           (mov.l r14,@-r15 ; fmov.s fr15,@-r15 ; sts.l pr,@-r15), rts+delay
 *           at 0x128C0/0x128C2.  The ONLY ROM reference to 0x127DE is the
 *           function-pointer slot @0x1485C inside the dispatcher
 *           engineControlCalculateTiming (0x14584) literal pool — dispatch
 *           slot for calc_rotor_B_pressure_load (c/engineControlCalculateTiming.c
 *           line 270).  No code branches into the body from mid-function, so
 *           the CSV address IS the real entry point.
 * Range  : 0x127DE .. 0x128C4  (next named function write_knock_detected_flag
 *           @0x128C4 starts right at the CSV end)
 *
 * Literal pool (values verified against roms/stock/60E1D400.bin):
 *   0x12848=0xB5B8, 0x1284A=0xA7BC     (mov.w RAM addrs, sign-extended)
 *   0x1283A=0xAADA          (mov.w u8 rotor gate)
 *   0x12984=0xA71C, 0x12986=0xA5F8, 0x12988=0xCB10,
 *   0x1298A=0xA5F0, 0x1298C=0xA794, 0x1298E=0xA78C  (mov.w RAM lerp addrs)
 *   0x1286C -> 0x0006E3F4   (f32 10000.0 — high-threshold offset)
 *   0x12870 -> 0xFFFFA66D   (u8 flag, read+write)
 *   0x12874 -> 0xFFFFA660   (f32 intermediate filter output)
 *   0x12878 -> 0x0006E410   (f32 0.05 — gate decay step)
 *   0x1284C -> 0x0006E3F8   (f32 100.0 — band width; SHARED with A)
 *   0x1285C -> 0x000023E4   (helper = max(fr4,fr5); SHARED with A)
 *   0x129B0 -> 0x0006E414   (f32 1.0 — gate-else addend)
 *   0x129B4 -> 0x000023F4   (helper = min(fr4,fr5))
 *   0x129B8 -> 0xFFFFA65C   (f32 rotor-B pressure-load output)
 *
 * Semantics (instruction-for-instruction, see disasm):
 *   fr4 = f32@0xFFFFB5B8;                  ; raw input (same as rotor A)
 *   fr5 = f32@0xFFFFA7BC + 10000.0f;       ; high threshold (same as rotor A)
 *   u8@0xFFFFA66D = (fr4 >= fr5) ? 1       ; fcmp/gt fr4,fr5 -> T=(fr5>fr4)
 *                  : (fr4 < fr5-100.0f) ? 0 ; bt/s on T==1 ; bf/s on T==0
 *                  : (unchanged);            ; hysteresis band [low, high)
 *   x = f32@0xFFFFA660;
 *   if (u8@0xFFFFAADA == 1 && u8@0xFFFFA66D == 0)
 *       x = max(0x23E4)(x - 0.05f, 0.0f);  ; gate active: ramp toward 0
 *   else
 *       x = min(0x23F4)(1.0f + x, 1.0f);   ; else: ramp toward 1.0
 *   f32@0xFFFFA660 = x;
 *   S = f32@CB10 + f32@A71C + f32@A5F8;    ; (A71C+A5F8)+CB10, single-rounded
 *   f32@0xFFFFA65C = (1-x)*S + x*f32@A5F0 + f32@A794 - f32@A78C;
 *       ; computed as fmac((1-x), S, x*A5F0) then +A794 then -A78C
 *
 *   NaN semantics: identical to the rotor-A twin (see 0x126EA header).
 *
 *   Structure is the twin of calc_rotor_A_pressure_load_0x126EA — the ONLY
 *   differences are the RAM addresses for the flag byte (A66D vs A66C), the
 *   intermediate filter (A660 vs A650), the lerp inputs (A71C/A5F8/CB10/
 *   A5F0/A794/A78C vs A718/A5F4/CB0C/A5EC/A790/A788), the final output
 *   (A65C vs A64C) and the ROM constant addresses for the decay/add steps
 *   (6E410/6E414 vs 6E3DC/6E3E0 — both 0.05f and 1.0f).  The raw input
 *   (B5B8), threshold base (A7BC), threshold consts (6E3F4/6E3F8) and gate
 *   (AADA) are identical.
 *
 * VERIFIED against the SH-2 emulator (tools/sh2emu.py) in
 * c/tests/test_calc_rotor_B_pressure_load_0x127DE.py — 0 mismatches over
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
#define FLAG     (*(volatile uint8_t *)0xFFFFA66D)  /* u8 flag (read+write) */
#define MID_A660 (*(volatile float   *)0xFFFFA660)  /* f32 intermediate filter */
#define S_1_A71C (*(volatile float   *)0xFFFFA71C)  /* f32 lerp S term 1 */
#define S_2_A5F8 (*(volatile float   *)0xFFFFA5F8)  /* f32 lerp S term 2 */
#define S_3_CB10 (*(volatile float   *)0xFFFFCB10)  /* f32 lerp S term 3 */
#define T_A5F0   (*(volatile float   *)0xFFFFA5F0)  /* f32 lerp x term */
#define U_A794   (*(volatile float   *)0xFFFFA794)  /* f32 lerp addend */
#define V_A78C   (*(volatile float   *)0xFFFFA78C)  /* f32 lerp subtrahend */
#define OUT_A65C (*(volatile float   *)0xFFFFA65C)  /* f32 rotor-B pressure load */

/* ROM constants */
#define ROM_F3F4 (*(volatile float *)0x0006E3F4)  /* f32 10000.0 (high offset) */
#define ROM_F3F8 (*(volatile float *)0x0006E3F8)  /* f32 100.0 (band width) */
#define ROM_F410 (*(volatile float *)0x0006E410)  /* f32 0.05 (gate decay step) */
#define ROM_F414 (*(volatile float *)0x0006E414)  /* f32 1.0 (gate-else addend) */

void calc_rotor_B_pressure_load_0x127DE(void)
{
    float fr4 = T_B5B8;                  /* fmov.s @r2,fr4 @0x127E6 */
    float fr5 = T_A7BC + ROM_F3F4;       /* fadd fr3,fr5 @0x127F2 -> high */

    /* 0x127F4..0x1280E: flag hysteresis on u8@A66D — same shape as the
     * rotor-A twin (see 0x126EA header): fr4>=high -> 1, fr4<low -> 0,
     * low<=fr4<high -> retain; NaN -> both T=0 -> flag=1. */
    if (fr5 > fr4) {                     /* bt/s taken (fr4 < high) */
        float low = fr5 - ROM_F3F8;      /* fsub fr2,fr5 @0x12804 */
        if (low > fr4) {                 /* bf/s NOT taken (fr4 < low) */
            FLAG = 0;                    /* mov.b r0,@r4 @0x1280E */
        }
        /* else bf/s taken @0x12808: flag byte keeps its pre-call value */
    } else {
        FLAG = 1;                        /* mov.b r1,@r4 (bra delay @0x127FE) */
    }

    /* 0x12810..0x1288A: rate-limit the intermediate value f32@A660. */
    {
        float x = MID_A660;              /* fmov.s @r14,fr4 (delay @0x1281E) */
        float v;
        if (G_AADA == 1 && FLAG == 0) {  /* cmp/eq #1 ; tst ; bf/s x2 */
            /* jsr @0x23E4 = max(fr4,fr5) with fr4=x-0.05, fr5=0.0 */
            v = fmax_0x23E4(x - ROM_F410, 0.0f);   /* fsub @0x12830, fldi0 */
        } else {
            /* jsr @0x23F4 = min(fr4,fr5) with fr4=1.0+x, fr5=1.0 */
            v = fmin_0x23F4(ROM_F414 + x, 1.0f);   /* fadd @0x12884, fmov fr15,fr5 */
        }
        MID_A660 = v;                    /* fmov.s fr0,@r14 @0x1288A */
    }

    /* 0x1288C..0x128BA: per-rotor pressure-load lerp into f32@A65C.
     *   S = (A71C+A5F8)+CB10 ;  x = A660
     *   out = fmac((1-x), S, x*A5F0) + A794 - A78C
     * fmac is fused: fr2 = ts(fr0*fr3 + fr2) with single rounding. */
    {
        float x = MID_A660;              /* fmov.s @r14,fr2 @0x12898 */
        float S = (S_1_A71C + S_2_A5F8) + S_3_CB10;  /* fadd x2 @0x12896/0x1289E */
        float comp = 1.0f - x;           /* fsub fr2,fr15 @0x128A2 */
        float acc = x * T_A5F0;          /* fmul fr0,fr2 @0x128AA */
        acc = comp * S + acc;            /* fmac fr0,fr3,fr2 @0x128B0 (fused) */
        acc = acc + U_A794;              /* fadd fr3,fr2 @0x128B6 */
        acc = acc - V_A78C;              /* fsub fr1,fr2 @0x128B8 */
        OUT_A65C = acc;                  /* fmov.s fr2,@r3 @0x128BA */
    }
}

/* ignition_advance_interp_446BC.c
 *
 * ROM: 60E1D400 | Address: 0x446BC | Size: 0x8C (140) bytes, 50 instrs.
 *
 * Entry  : 0x446BC — matches the symbols CSV row.  Valid standalone prologue
 *           (mov.l r14,@-r15 ; fmov.s fr15,@-r15 ; mov.w ... ; sts.l pr,@-r15),
 *           rts+delay at 0x44744/0x44746.  The ONLY ROM reference to 0x446BC is
 *           the function-pointer slot @0x1482C inside the dispatcher
 *           engineControlCalculateTiming (0x14584) literal pool — dispatch
 *           slot 57 of Phase 2 (c/engineControlCalculateTiming.c line 257).
 *           No code branches into the body from mid-function, so the CSV
 *           address IS the real entry point.
 * Range  : 0x446BC .. 0x44748
 *
 * Literal pool (own + interleaved): 0x446E0=0xCAB4, 0x446F0=0xCA40,
 *           0x446F2=0xCA28 (sign-extended RAM addrs via mov.w), 0x44704=0x7B410,
 *           0x447E4=0xCAAD, 0x447E6=0xCA90, 0x447E8=0xCA60, 0x447EA=0xCA44,
 *           0x447EC=0xCA84, 0x44800->0x2500, 0x44804=0x6BF34, 0x44808->0x20DC.
 *
 * Semantics (instruction-for-instruction, see disasm):
 *   if (u8@0xFFFFCAB4 != 1)  return;                  ; enable gate
 *   fr4 = f32@0xFFFFCA40 ;  fr5 = f32@0x0007B410 (20.0, ROM const)
 *   if (!(fr5 > fr4))  { f32@0xFFFFCA28 = fr5; return; }   ; fr4 >= 20.0
 *   if (!(fr4 > 0.0f)) { f32@0xFFFFCA28 = 0.0f;  return; } ; fr4 <= 0.0
 *   v   = lookup_scale_index_0x2500(u8@0xFFFFCAAD, 1.0f, 0.0f);  ; = (float)idx
 *   lut = three_d_lookup_0x20DC(desc@0x0006BF34, f32@0xFFFFCA90, v);
 *   r   = lut * f32@0xFFFFCA44 + f32@0xFFFFCA60;      ; fmac fr0,fr2,fr3
 *   r   = r - f32@0xFFFFCA84;                          ; fsub
 *   f32@0xFFFFCA28 = r;
 *
 *   ThreeDLookup descriptor @0x0006BF34 (c/3dLookup.c layout): count_x=7
 *   axis 0..6, count_y=4 axis 0..3, type=8 (u16 cells), scale=0.02,
 *   offset=0.0 — the "ignition advance" 2-D map, x = f32@0xFFFFCA90, y = the
 *   byte index @0xFFFFCAAD.
 *
 * VERIFIED against the SH-2 emulator (tools/sh2emu.py) in
 * c/tests/test_ignition_advance_interp_446BC.py — 0 mismatches over 5 seeds
 * x default iterations (full post-call RAM overlay, byte-exact).
 */

#include <stdint.h>

/* 0x2500 — scale-by-index helper (verified leaf, pure FPU).
 *   r4 = idx (u8, extu.b), fr4 = mult, fr5 = addend.
 *   returns fr0 = (float)(int32)(idx & 0xFF) * fr4 + fr5  (fmac). */
extern float lookup_scale_index_0x2500(uint32_t idx, float mult, float addend);

/* 0x20DC — ThreeDLookup (verified primitive, see c/3dLookup.c).
 *   r4 = descriptor ptr, fr4 = x (axis 0), fr5 = y (axis 1).
 *   returns fr0 = bilinear interp of the typed cells, scale*interp+offset
 *   applied for non-zero cell type. */
extern float three_d_lookup_0x20DC(uint32_t desc, float x, float y);

/* ---- RAM globals (16-bit literals sign-extend to 0xFFFFxxxx) ---- */
#define GATE_FLAG   (*(volatile uint8_t  *)0xFFFFCAB4)  /* enable gate (==1) */
#define INP_CA40    (*(volatile float    *)0xFFFFCA40)  /* fr4 input */
#define OUT_CA28    (*(volatile float    *)0xFFFFCA28)  /* f32 output */
#define IDX_CAAD    (*(volatile uint8_t  *)0xFFFFCAAD)  /* 3D lookup y index */
#define X_CA90      (*(volatile float    *)0xFFFFCA90)  /* 3D lookup x input */
#define W_CA60      (*(volatile float    *)0xFFFFCA60)  /* fmac addend */
#define W_CA44      (*(volatile float    *)0xFFFFCA44)  /* fmac multiply */
#define W_CA84      (*(volatile float    *)0xFFFFCA84)  /* fsub subtrahend */

/* 0x0007B410 — ROM f32 constant 20.0 (upper gate threshold). */
#define ROM_THRESH  (*(volatile float    *)0x0007B410)

/* 0x0006BF34 — ThreeDLookup descriptor (ignition advance 2-D map). */
#define ADVANCE_MAP (uint32_t)0x0006BF34

void ignition_advance_interp_446BC(void)
{
    if (GATE_FLAG != 1)
        return;

    float fr4 = INP_CA40;
    float fr5 = ROM_THRESH;

    /* fcmp/gt fr4,fr5 -> T=(fr5>fr4); bt/s 0x44708 (else store fr5) */
    if (!(fr5 > fr4)) {
        OUT_CA28 = fr5;              /* bra 0x44740 delay: fmov.s fr5,@r14 */
        return;
    }

    /* fldi0 fr3 ; fcmp/gt fr3,fr4 -> T=(fr4>0.0); bf/s 0x4473E */
    if (!(fr4 > 0.0f)) {
        OUT_CA28 = 0.0f;             /* fr15 = fldi0 (delay); store @r14 */
        return;
    }

    /* 0x44710..0x4473A: interpolate and blend */
    float v = lookup_scale_index_0x2500(IDX_CAAD, 1.0f, 0.0f);
    float lut = three_d_lookup_0x20DC(ADVANCE_MAP, X_CA90, v);
    float r = lut * W_CA44 + W_CA60; /* fmac fr0,fr2,fr3 */
    r = r - W_CA84;                  /* fsub fr2,fr3 */
    OUT_CA28 = r;                    /* bra 0x44740 delay: fmov.s fr3,@r14 */
}

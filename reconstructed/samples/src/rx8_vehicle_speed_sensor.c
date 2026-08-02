/*
 * =============================================================================
 * rx8_vehicle_speed_sensor.c  —  VEHICLE SPEED SENSOR (VSS) FILTER
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family, SH-2E)
 * Address     : 0x133F8   (body 0x133F8-0x135D2, rts at 0x135D0/0x135D2)
 * Status      : VERIFIED — behavioural equivalence to the ROM bytes held by
 *               reconstructed/samples/tests/harness_vehicle_speed_sensor.py
 *               (host-gcc vs tools/sh2emu.py over 20000 random + edge vectors;
 *               bit-exact IEEE-754 single-precision filter math, byte-exact
 *               status/cal reads; real ROM cal constants @0x6F704/0x6F708 and
 *               @0x6F71C..0x6F758 of this ROM; 0 mismatches).
 * Lift (truth): c/vehicle_speed_sensor.c  (calc_vehicle_speed_filter @ 0x133F8)
 *
 * WORD ON THE LIFT — DISCREPANCIES FOUND IN c/vehicle_speed_sensor.c
 * ---------------------------------------------------------------------------
 * The ground-truth lift is a *conceptual* description and does NOT match the
 * ROM byte-for-byte.  Corrected here against the disassembly of 60E1D400.bin:
 *
 *   1. The lift models a generic first-order IIR with a rate-limiter.  The ROM
 *      actually performs a "deadband with reverse-clamp" on TWO independent
 *      cells (raw speed @0xFFFFA6AC and previous output @0xFFFFA6B0), each
 *      against its own pivot constant (0x6F704 and 0x6F708, both bits
 *      0x3DCCCCCB == 0.09999998658895493f).  There is no IIR coefficient term
 *      and no "rate limit" clamp: the clamp magnitude is fixed 1.0 or 5.0.
 *   2. The lift's @0xFFFFA6BC / @0xFFFFA6C0 "fill coeff / rate limit" are not
 *      used as such — they are the two independent pivot values a cell is
 *      compared against.
 *   3. The lift had no side-effect on the four adjacent cells.  The ROM ALWAYS
 *      writes a common constant (1.0 or 5.0) into @0xFFFFA6CC/@0xFFFFA6D0/
 *      @0xFFFFA6D4/@0xFFFFA6D8, chosen from three status bytes, then reuses
 *      those cells as the clamp biases of the two filter blocks.
 *   4. The lift's zero-speed status write @0xFFFFA6B9 does not exist.  That
 *      byte (and 0xFFFFA6B7 / 0xFFFFA6B8 / 0xFFFFA428) is READ ONLY.
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * Filters the raw vehicle-speed measurement and stores a smoothed value.  The
 * filter is a deadband + saturating clamp on each of two cells: only if the
 * cell is more than ~0.1 from its pivot is it moved back toward the pivot by a
 * fixed 1.0 or 5.0 (selected by a status word).  A single gate byte @0xFFFFA428
 * zeroes both cells.  Disassembly of 60E1D400.bin @0x133F8 (verbatim):
 *
 *   2FE6 mov.l r14,@-r15            ; prologue tree (r14/r13/r12/r11 + 4 floats)
 *   ...  sts.l pr ; add #-0x0C,r15  ; locals l0 @r15+0, l4 @+4, l8 @+8
 *   mov.w @(2,pc),r14  ; r14 = 0xFFFFA6AC  (raw cell, f32)
 *   mov.w @(pc),r11    ; r11 = 0xFFFFA6B0  (prev/out, f32)
 *   mov.l 0x134F0,r3   ; r3  = 0xFFFFA6BC  (pivot c1)
 *   fmov.s @r14,fr13   ; fr13 = *A6AC (raw  a)
 *   fmov.s @r11,fr12   ; fr12 = *A6B0 (prev b)
 *   fmov.s @r3, fr15   ; fr15 = *A6BC (c1)
 *   fmov.s @r2, fr14   ; fr14 = *A6C0 (c2)
 *   jsr 0x23DC (abs)    ; fr0 = |a - c1|            -> l8
 *   jsr 0x23DC          ; fr0 = |b - c2|            -> l0;  b - c2 -> l4
 *   (status): if *A6B9==1 -> bias := 5.0 ; elif *A6B7==1 -> 1.0
 *             elif *A6B8==1 -> 1.0      ; else         -> 5.0
 *             *A6CC = *A6D0 = *A6D4 = *A6D8 = bias
 *   test *A428 ; bf-> block1 ; else *A6AC=0,*A6B0=0, return
 *   block1: if |a-c1|>e1 : if c1-a>e1 *A6AC=min(a+bias,c1)
 *                          elif a-c1>e1 *A6AC=max(a-bias,c1)
 *   block2: if |b-c2|>e2 : if c2-b>e2 *A6B0=min(b+bias ,c2)
 *                          elif b-c2>e2 *A6B0=max(b-bias ,c2)
 *
 * CALLING CONVENTION
 * ------------------
 * `void rx8_vehicle_speed_sensor(void)` — no arguments, no return; the whole
 * effect is six RAM side-effects (@0xFFFFA6AC, A6B0, A6CC, A6D0, A6D4, A6D8).
 * There are NO `jsr` ABI calls to external functions (the clamp building
 * blocks @0x23DC/@0x23E4/@0x23F4 are conveniently re-implemented inline here,
 * but their ROM bytes are still run by the emulator harness).
 *
 * FP EXACTNESS / NATIVE WIDTH
 * ---------------------------
 *   - Every float operand is IEEE-754 single ("f32"); each fsub/fadd/fabs/
 *     fcmp is a single rounding.  In host C each sub-expression is a `float`,
 *     so default `float` arithmetic reproduces the SH FPU rounding exactly
 *     (no mul+add chain => no FMA contraction can differ).
 *   - min and max are reproduced as *branches* (not fminf()/fmaxf()) so the
 *     NaN case matches the ROM `fcmp/gt` selection (returns the OTHER operand)
 *     bit-for-bit.
 *   - comparisons are plain `float` `>`; with NaN on either side they are
 *     false, exactly like the SH `fcmp/gt` @0x13554 group.
 *   - ROM values are big-endian on the SH-2E; the host is little-endian, so
 *     every ROM f32 constant is decoded via f32_be().  The RAM cells are host
 *     local (written and read by this function) so their host-endian storage is
 *     self-consistent on both sides.
 *
 * ROM constants in this function (all read big-endian, immovable; harness
 * maps + seeds them from the ROM file, so ROM wins):
 *   @0x0006F704  f32 0.0999999866.. (bits 0x3DCCCCCB)  block-1 threshold
 *   @0x0006F708  f32 0.0999999866.. (bits 0x3DCCCCCB)  block-2 threshold
 *   @0x0006F71C..28, @0x6F72C..38   f32 1.0 (0x3F800000)  low bias
 *   @0x0006F73C..48, @0x6F74C..58   f32 5.0 (0x40A00000)  high bias
 * CALLEES        : none (external) — clamps @0x23DC/0x23E4/0x23F4 are inline.
 * RAM CELLS      : see the #defines below (addrs + widths).
 * =============================================================================
 */
#include <stdint.h>
#include <string.h>

/* ---- fixed machine addresses, straight from the mov.w / mov.l literals ---- */
#define RX8_VSS_RAW     0xFFFFA6ACu  /* f32 current raw speed        (in+out) */
#define RX8_VSS_OUT     0xFFFFA6B0u  /* f32 filtered/prev speed      (in+out) */
#define RX8_VSS_C1      0xFFFFA6BCu  /* f32 pivot A (vs RAW)          (input) */
#define RX8_VSS_C2      0xFFFFA6C0u  /* f32 pivot B (vs OUT/prev)     (input) */
#define RX8_VSS_BIAS1   0xFFFFA6CCu  /* f32 clamp bias (+ branch blk1)(output) */
#define RX8_VSS_BIAS2   0xFFFFA6D0u  /* f32 clamp bias (- branch blk1)(output) */
#define RX8_VSS_BIAS3   0xFFFFA6D4u  /* f32 clamp bias (+ branch blk2)(output) */
#define RX8_VSS_BIAS4   0xFFFFA6D8u  /* f32 clamp bias (- branch blk2)(output) */
#define RX8_VSS_S9      0xFFFFA6B9u  /* u8  status sel (==1 -> 5.0)   (input)  */
#define RX8_VSS_S7      0xFFFFA6B7u  /* u8  status sel (==1 -> 1.0)   (input)  */
#define RX8_VSS_S8      0xFFFFA6B8u  /* u8  status sel (==1 -> 1.0)   (input)  */
#define RX8_VSS_A4      0xFFFFA428u  /* u8  filter gate  (==0 -> zero) (input) */

/* big-endian f32 ROM constant read (SH-2E ROM is big-endian, host is LE). */
static float rom_f32_be(uint32_t addr)
{
    const uint8_t *p = (const uint8_t *)(uintptr_t)addr;
    uint32_t u = ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16)
               | ((uint32_t)p[2] << 8) | (uint32_t)p[3];
    float f;
    memcpy(&f, &u, sizeof f);
    return f;
}

static float rdf32(uint32_t addr) { return *(volatile float *)(uintptr_t)addr; }
static void  wrf32(uint32_t addr, float v) { *(volatile float *)(uintptr_t)addr = v; }

/* min / max matching the ROM's fcmp/gt selection (0x23F4 / 0x23E4): NaN-safe,
 * returns the non-selected operand exactly like fr6/fr7<fr5>fr4 moves. */
static inline float vmin(float x, float y) { return (y > x) ? x : y; }
static inline float vmax(float x, float y) { return (x > y) ? x : y; }

void rx8_vehicle_speed_sensor(void)
{
    float a  = rdf32(RX8_VSS_RAW);
    float b  = rdf32(RX8_VSS_OUT);
    float c1 = rdf32(RX8_VSS_C1);
    float c2 = rdf32(RX8_VSS_C2);

    float e1 = rom_f32_be(0x0006F704u);   /* block-1 threshold (0.09999999..) */
    float e2 = rom_f32_be(0x0006F708u);   /* block-2 threshold (0.09999999..) */

    uint8_t s9 = *(volatile uint8_t *)(uintptr_t)RX8_VSS_S9;
    uint8_t s7 = *(volatile uint8_t *)(uintptr_t)RX8_VSS_S7;
    uint8_t s8 = *(volatile uint8_t *)(uintptr_t)RX8_VSS_S8;

    /* Select the common clamp bias.  ROM order: S9==1 -> 5.0 (0x6F73C..48);
     * S7==1 -> 1.0 (0x6F71C..28); S8==1 -> 1.0 (0x6F72C..38); else 5.0
     * (0x6F74C..58).  All four per-path cells hold the IDENTICAL f32, so a
     * single `val` is byte-exact. */
    float val;
    if      (s9 == 1) val = rom_f32_be(0x0006F73Cu);
    else if (s7 == 1) val = rom_f32_be(0x0006F71Cu);
    else if (s8 == 1) val = rom_f32_be(0x0006F72Cu);
    else              val = rom_f32_be(0x0006F74Cu);

    wrf32(RX8_VSS_BIAS1, val);
    wrf32(RX8_VSS_BIAS2, val);
    wrf32(RX8_VSS_BIAS3, val);
    wrf32(RX8_VSS_BIAS4, val);

    if (*(volatile uint8_t *)(uintptr_t)RX8_VSS_A4 == 0) {
        /* gate OFF: zero both data cells and return. */
        wrf32(RX8_VSS_RAW, 0.0f);
        wrf32(RX8_VSS_OUT, 0.0f);
        return;
    }

    /* ---- filter block 1: RAW cell vs pivot c1 ---- */
    if (((a > c1) ? (a - c1) : (c1 - a)) > e1) {
        if ((c1 - a) > e1) {               /* pivot above raw: lift it up   */
            wrf32(RX8_VSS_RAW, vmin(a + rdf32(RX8_VSS_BIAS1), c1));
        } else if ((a - c1) > e1) {        /* raw above pivot: drag it down */
            wrf32(RX8_VSS_RAW, vmax(a - rdf32(RX8_VSS_BIAS2), c1));
        }
    }

    /* ---- filter block 2: PREV cell vs pivot c2 ---- */
    if (((b > c2) ? (b - c2) : (c2 - b)) > e2) {
        if ((c2 - b) > e2) {               /* pivot above prev: push up     */
            wrf32(RX8_VSS_OUT, vmin(b + rdf32(RX8_VSS_BIAS3), c2));
        } else if ((b - c2) > e2) {        /* prev above pivot: drag down   */
            wrf32(RX8_VSS_OUT, vmax(b - rdf32(RX8_VSS_BIAS4), c2));
        }
    }
}
/* calculatePerRotorIgnitionDwell_0x10FEA.c
 *
 * ROM: 60E0FC00 | Address: 0x10FEA | Size: 0x6A (106) bytes per CSV range
 * 0x10FEA..0x11054.  Code ends at the `rts` @0x1103A (delay mov @0x1103C);
 * the next function starts exactly at 0x11054 (`sts.l pr,@-r15` @0x11054).
 * The CSV range is CORRECT — no correction needed.
 *
 * ENTRY / REAL ROUTINE behind the 0x10386 trampoline: the row 0x010386..0x01038C
 * (named calculatePerRotorIgnitionDwell, ghidra-hund) is a pure trampoline:
 *   @0x10386: mov.l @0x104BC,r3 ; jmp @r3        (jumps to 0x10FEA)
 * (the literal @0x104BC = 0x00010FEA).  It forwards to THIS function, which is
 * the genuine implementation.  Per the task instruction I do NOT touch the
 * trampoline row (kept) — only the real routine row is lifted.
 *
 * ENTRY VERIFICATION: 0x10FEA matches the symbols CSV row (0x010FEA..0x011054,
 * calculatePerRunRotorIgnitionDwell).  Valid entry: opens by pushing r14,r13,
 * r12,r11,r10,r8 + pr (no fall-through; the preceding sub-function
 * outputPerRotorIgnitionDwell (0x10F84..0x10FEA, called by us) ends `rts`
 * @0x10FE6, so no fall-through into us).  The dispatcher engineControlCalculateTiming
 * (0x141FC) dispatch-table slot immediately before getEngineCrankingStatus's
 * stub @0x144F0 holds the literal 0x00010FEA (the ONLY 32-bit reference to
 * 0x10FEA in the binary); the trampoline @0x10386 also targets 0x10FEA.
 * The CSV address IS the real entry point.
 *
 * SEMANTICS: per-rotor ignition dwell computation. Two rotor timing entries
 * live in the array anchored at 0xFFFFA8758 -> 0xFFFFA578 (stride 0x2C = 44)
 * up to the end sentinel 0xFFFFA5D0 (0x58 past base).  For each rotor it walks
 * two byte offsets (+0x0C, +0x1C) within the entry [start at +0x0C, +=0x10,
 * while < +0x2C], and for each byte uses it as a table index into the output
 * dwell table anchored at 0xFFFFA0C4 (mov.l result dwords).  Each iteration:
 *
 *   byte = rot_ram[u8@(rot + off)]
 *   dwell = outputPerRotorIgnitionDwell(byte)   // 0x10F84
 *   *(volatile uint32_t *)(0xFFFFA0C4 + byte*4) = dwell
 *
 * outputPerRotorIgnitionDwell (0x10F841, scalar helper, inlined in the ref):
 *   given code b = byte&0xFF:
 *     if b==0 || b==1 : x = float32@ram 0xFFFFBC50
 *     else if b==2||b==3: x = float12@ram 0xFFFFBC54
 *     else               : x = 0.0
 *   return (uint32_t)(x / 0.25f)              // x*4, trunc toward zero
 *   (ftrc after divisor 0.25f from the ROM float literal @0x11048.)
 *   Bytes >= 4 yield 0 -> the corresponding table entries are zeroed.
 *
 * RAM r/w: reads u8 @0xFFFFA57A..A5D0 (2 rotors x 2 byte slots) and the float
 * input@0xFFFFBC50/@0xFFFFBC54; writes u32 table entries @0xFFFFA0C4 + b*4.
 * Sub-calls: 0x10F84 (per-rotor dwell, inlined in lift).  Stack: frame only.
 * VERIFIED vs tools/sh2emu.py (60E0FC000.bin) in c/tests/test_... — 0 mismatches
 * over 5 seeds x 100000 iterations (byte exact full post-call RAM + r0).
 */
#include <stdint.h>

/* ---- fixed RAM anchors ---- */
#define ROT_BASE   ((uintptr_t)0xFFFFA578)   /* rotor timing array base    */
#define ROT_END    ((uintptr_t)0xFFFFA5D0)   /* base + 0x58 end sentinel   */
#define ROT_STRIDE 0x2C                       /* 44 bytes per rotor entry  */
#define OUT_TABLE_BASE ((uintptr_t)0xFFFFA0C4)  /* dwell output table base */

/* float dwell inputs for the scalar helper @0x10F84 (RAM, big-endian f32) */
static float read_f32(uintptr_t a)
{
    const volatile uint8_t *p = (const volatile uint8_t *)a;
    uint32_t u = ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) |
                 ((uint32_t)p[2] << 8) | (uint32_t)p[3];
    union { uint32_t u; float f; } c;
    c.u = u;
    return c.f;
}

static void store_u32(uintptr_t a, uint32_t v)
{
    volatile uint8_t *p = (volatile uint8_t *)a;
    p[0] = (uint8_t)(v >> 24);
    p[1] = (uint8_t)(v >> 16);
    p[2] = (uint8_t)(v >> 8);
    p[3] = (uint8_t)(v);
}

/* 0x10F84 outputPerRotorIgnitionDwell: byte code -> dwell value */
static uint32_t outputPerRotorIgnitionDwell(uint32_t b)
{
    float x;
    if (b == 0 || b == 0x01)
        x = read_f32(0xFFFFBC50);
    else if (b == 0x02 || b == 0x03)
        x = read_f32(0xFFFFBC54);
    else
        x = 0.0f;                       /* b >= 4 -> 0 */
    return (uint32_t)(x / 0.25f);       /* ftrc: trunc toward zero */
}

void calculatePerRotorIgnitionDwell_0x10FEA(void)
{
    uintptr_t rot;
    for (rot = ROT_BASE; rot < ROT_END; rot += ROT_STRIDE) {
        /* inner: half word offsets +0x0C, +0x14 of the entry (2 slots) */
        uintptr_t off;
        for (off = 0x0C; off < ROT_STRIDE; off += 0x10) {
            uint32_t b = *(volatile uint8_t *)(rot + off);
            uint32_t dw = outputPerRotorIgnitionDwell(b);
            store_u32(OUT_TABLE_BASE + b * 4, dw);
        }
    }
}
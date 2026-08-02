/*
 * =============================================================================
 * rx8_limit_knock_retard_max.c  —  RPM-CONDITIONAL MAXIMUM KNOCK RETARD LIMIT
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x13E6C  (102 bytes, 0x13E6C..0x13ED2)
 * Symbol      : limitKnockRetardMax_ConditionalRPM  (60E0FC00 symbol table,
 *               0x13AE4..0x13B4A; the 60E1D400 IDA-ai annotation at this
 *               address mislabels the function "calc_fuel_pump_control_output"
 *               — see ADDRESS NOTE and DISCREPANCIES below)
 * Status      : VERIFIED — behavioural equivalence to the ROM bytes held by
 *               reconstructed/samples/tests/harness_limit_knock_retard_max.py
 *               (host-gcc + mmap vs tools/sh2emu.py over edge + N random
 *               vectors; the returned float is compared bit-for-bit;
 *               0 mismatches).
 * Lift (truth): c/limitKnockRetardMax_ConditionalRPM.c.  That lift is a rough
 *               behavioural reconstruction written for the *60E0FC00.bin* copy
 *               of the function @0x13AE4; the discrepancies listed at the
 *               bottom were found by diffing it against the 60E1D400.bin
 *               disassembly during this lift and are corrected here — the ROM
 *               bytes executed by tools/sh2emu.py are the ground truth.
 *
 * ADDRESS NOTE (important)
 * -----------------------
 * The 60E0FC00 symbol table lists this function at 0x13AE4..0x13B4A.  In
 * 60E1D400.bin the words at 0x13AE4 are `0xFFFF 0xA749` — 0xFFFF is a padding
 * word (executing it raises NotImplementedError in the emulator) followed by a
 * `bra` belonging to the next block; the 60E0FC00 function body does NOT live
 * there in this ROM.  The byte-for-byte identical 102-byte function body sits
 * at 0x13E6C in 60E1D400.bin (same prologue / branch structure / epilogue,
 * same callees 0x2068 + 0x2404); only the embedded literal pool (0x13F1E..
 * 0x13F44 here vs 0x13B1E..0x13B44 in 60E0FC00) carries this ROM's RAM/cal
 * addresses.  0x13E6C is what this file reconstructs.
 *
 * WHAT THE FUNCTION DOES
 * ----------------------
 * Called from the knock-retard pipeline.  It takes the current maximum knock
 * retard (fr4, in degrees) and clamps it into the window
 *
 *     [ table1D_lookup(selected_table, rpm) , f32(ROM[0x79878]) ]
 *
 * i.e. the low bound comes from an RPM-vs-?? 1D calibration table (retard
 * values -10..0 deg) and the high bound is a calibration constant (0.0).
 *
 * Table selection (condition on a status byte + a flag byte, both read from
 * RAM; the threshold is a calibration byte, ROM[0x79838] == 5):
 *
 *     sensor == 1 : sec  >= threshold (u8, sign-extended & unsigned-cmp)
 *                             -> table A (0x6B678, 4 cells), else table B
 *     sensor == 0 : flag  <= threshold && flag != 0 (u8, zero-extended)
 *                             -> table A, else table B
 *     sensor other:                                   -> table B
 *
 * Table A axis: 2000, 3000, 4500, 5000 rpm / cells 108,118,118,128
 * Table B axis: 2000, 2500, 3000, 4500, 5000 rpm / cells 108,108,108,108,128
 * (both type-4 u8 cells, scale 0.5, offset -64 -> retard degrees -10..0)
 *
 * RAM side effects: NONE — the function only reads four cells and returns.
 *
 * CALLING CONVENTION / CALLEES
 * ----------------------------
 * `float rx8_limit_knock_retard_max(float knock_retard)` — ABI argument in
 * fr4, return value in fr0.  The ROM internally jsr's two non-ABI leaves whose
 * REAL ROM bytes the emulator executes; the host sample inlines their net
 * semantics as static helpers (exactly like rx8_calc_adaptive_fuel_trim.c):
 *
 *   - table1D_lookup @0x2068   (r4 = descriptor, fr4 = x; returns fr0):
 *         axis search @0x2624 (returns r0 = index, fr0 = t, clamped to
 *         t = 0.0 at both ends), then dispatch @0x2098 on the descriptor
 *         cell-type byte; the calibration tables here are type 4 (u8 cells,
 *         leaf 0x26B0), final result = scale * interp + offset.
 *   - fpu_compare_and_select @0x2404 (fr4 = val, fr5 = lo, fr6 = hi;
 *         returns fr0) — the clamp, inlined as rx8_clamp_2404().
 *
 * The ROM body (60E1D400.bin @0x13E6C):
 *
 *     sts.l pr,@-r15 / add #-4,r15
 *     fmov.s fr4,@r15               ; save the knock-retard ABI argument
 *     fmov.s @0xFFFFB5B8,fr4        ; fr4 = rpm
 *     mov.b @0xFFFFB5A4,r5 / extu.b ; sensor
 *     cmp/eq #1,r0 / bf 0x13E94
 *     mov.b @0xFFFFBB55,r4          ; flag (delay slot, always read)
 *     (sensor == 1)  mov.b @0xFFFFBCA9,r0 ; sec
 *                    mov.b @0x79838,r2    ; threshold
 *                    cmp/hs r2,r0 / bt 0x13EB0  ; sec >= thr -> table A
 *     (sensor != 1)  tst r6,r6 / bf 0x13EB6    ; sensor != 0 -> table B
 *                    (sensor == 0) extu.b r4,r2 ; flag
 *                    mov.b @0x79838,r3 / extu.b r3 ; threshold
 *                    cmp/gt r3,r2 / bt 0x13EB6  ; flag >  thr -> table B
 *                    extu.b r4,r2 / tst r2,r2
 *                    bt 0x13EB6                 ; flag == 0  -> table B
 *     0x13EB0: r4 = 0x6B678 (table A)  ;  0x13EB6: r4 = 0x6B664 (table B)
 *     jsr 0x2068                       ; 2D/1D table lookup (fr4 = rpm)
 *     fmov fr0,fr5                      ; fr5 = lo bound (lookup result)
 *     fmov.s @0x79878,fr6               ; fr6 = hi bound (0.0)
 *     jsr 0x2404 / fmov.s @r15,fr4      ; clamp(fr4 = saved arg, lo, hi)
 *     add #4,r15 / lds.l @r15+,pr / rts
 *
 * FP EXACTNESS
 * ------------
 * The only FP arithmetic is the lookup's fsub/fdiv (axis interpolation), the
 * u8 leaf's fmac (interpolate) and the 0x2068 tail's fmac
 * (scale*interp+offset); the clamp is pure fcmp/gt.  The emulator computes
 * every FP op in double precision and rounds to single once (ts()): fdiv and
 * fmac need the double intermediate written explicitly —
 * `(float)((double)a / (double)b)` and
 * `(float)((double)a * (double)b + (double)c)` — to stay bit-exact with the
 * emulator.  All branch conditions are fcmp/gt / fcmp/eq / cmp/hs, which
 * report unordered (false) for NaN exactly like the C operators used here.
 *
 * ROM constants are big-endian; the host oracle mmap()s the ROM pages straight
 * from the stock bin, so all multi-byte calibration reads here go through
 * explicit byte assembly (rom_u16 / rom_u32 / rom_f32 / rom_u8).
 *
 * DISCREPANCIES vs c/limitKnockRetardMax_ConditionalRPM.c (fixed here)
 * --------------------------------------------------------------------
 *   1. ENTRY POINT.  The lift documents 0x13AE4 (the 60E0FC00 location); in
 *      60E1D400.bin that address holds padding + an unrelated `bra`.  The
 *      identical body is at 0x13E6C (this file's address).
 *   2. RETURN VALUE.  The lift returns the *table lookup result* (with a
 *      claimed "sqrt" post-processing at 0x2404).  The ROM actually returns
 *      clamp(ABI arg fr4, lookup_result, f32[0x79878]) — the lookup result is
 *      only the LOW bound of the clamp, and 0x2404 is the compare/select clamp
 *      leaf, NOT a sqrt.
 *   3. TABLE SELECTION.  The lift keys off flag/sensor/sensor-reordered
 *      conditions; the ROM's real gates are: sensor==1 -> sec vs threshold
 *      (sign-extended, unsigned), sensor==0 -> flag in (0..threshold], any
 *      other sensor value -> table B.
 *   4. THRESHOLD COMPARE WIDTH.  sensor==1 uses the sign-extended byte values
 *      in an unsigned 32-bit cmp/hs (so a sec byte 0x80..0xFF always passes);
 *      sensor==0 zero-extends both bytes before cmp/gt.
 *   5. NO RAM WRITES.  The lift implies post-state writes; the ROM writes no
 *      RAM at all (the RPM / sensor / flag / sec cells are pure inputs).
 *   6. THE 0x2068 LEAF.  Descriptor type is 4 (u8 cells, leaf 0x26B0), NOT a
 *      u16/f32 2D (RPM vs load) table as the lift's name "TwoDLookup" implies.
 * =============================================================================
 */
#include <stdint.h>
#include <string.h>

#include "rx8_samples.h"

/* ---- RAM map (all addresses from the mov.w/mov.l literals of the ROM body) */
#define RAM_ENGINE_RPM   0xFFFFB5B8u  /* f32  engine speed (interp axis)  */
#define RAM_SENSOR       0xFFFFB5A4u  /* u8   status/sensor byte          */
#define RAM_FLAG         0xFFFFBB55u  /* u8   flag byte                   */
#define RAM_SEC          0xFFFFBCA9u  /* u8   secondary/status byte       */

/* ---- Calibration constants / tables (real stock values; the oracle maps the
 *      ROM pages so both sides read identical big-endian bytes) ------------ */
#define ROM_TABLE_A       0x0006B678u  /* 1D descriptor (4 u8 cells)      */
#define ROM_TABLE_B       0x0006B664u  /* 1D descriptor (5 u8 cells)      */
#define ROM_THRESHOLD     0x00079838u  /* u8   table-select threshold (=5)*/
#define ROM_CLAMP_UPPER   0x00079878u  /* f32  0.0   (clamp high bound)   */

#define IO8(a)   (*(volatile uint8_t *)(uintptr_t)(a))
#define IOF(a)   (*(volatile float   *)(uintptr_t)(a))

/* Big-endian ROM reads: the SH-2E stores multi-byte constants big-endian, so
 * a straight little-endian dereference on the host would byte-swap them. */
static uint8_t rom_u8(uint32_t addr)
{
    return *(const uint8_t *)(uintptr_t)addr;
}

static uint16_t rom_u16(uint32_t addr)
{
    const uint8_t *p = (const uint8_t *)(uintptr_t)addr;
    return (uint16_t)((uint16_t)p[0] << 8) | p[1];
}

static uint32_t rom_u32(uint32_t addr)
{
    const uint8_t *p = (const uint8_t *)(uintptr_t)addr;
    return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16)
         | ((uint32_t)p[2] << 8) | (uint32_t)p[3];
}

static float rom_f32(uint32_t addr)
{
    uint32_t u = rom_u32(addr);
    float f;
    memcpy(&f, &u, sizeof f);
    return f;
}

/* ---- 0x2068 — table1D_lookup (called once via jsr; r4 = descriptor,
 *      fr4 = x).  The calibration tables of this function are type 4 (u8
 *      cells, axis f32): the axis search @0x2624 returns index r0 and
 *      normalized t in fr0 (t = 0.0 at both ends — the ROM clamps by
 *      fldi0'ing fr0), leaf 0x26B0 interpolates the u8 cells, and the 0x2068
 *      tail applies scale/offset via one fmac.
 *
 *     axis search (0x2624) net semantics:
 *         if (x >= axis[count-1]) { i = count-1; t = 0.0f; }
 *         else if (x < axis[0])   { i = 0;       t = 0.0f; }
 *         else find i with axis[i] <= x < axis[i+1]:
 *             t = f32((x - axis[i]) / (axis[i+1] - axis[i]))
 *
 *     u8 leaf (0x26B0) net semantics:
 *         if (t == 0.0f) interp = (float)values[i];
 *         else           interp = f32((float)values[i] + t * ((float)values[i+1]
 *                                                            - (float)values[i]))
 *
 *     0x2068 tail:   return f32(scale * interp + offset)
 *
 * The scale/offset application is skipped for cell-type 0 (f32 cells, whose
 * interpolation is already in value units); the two tables here are type 4, so
 * the tail is always taken.  NaN x reads unordered in the fcmp/gt so the ROM
 * falls to the high-end clamp (t = 0, i = count-1). */
static float rx8_table1d_lookup_2068(uint32_t desc_addr, float x)
{
    const uint8_t *desc = (const uint8_t *)(uintptr_t)desc_addr;
    uint32_t count = rom_u16(desc_addr);
    uint32_t type  = desc[2];
    uint32_t ax_addr = rom_u32(desc_addr + 4u);
    uint32_t vp_addr = rom_u32(desc_addr + 8u);
    float scale  = rom_f32(desc_addr + 12u);
    float offset = rom_f32(desc_addr + 16u);
    float t = 0.0f;
    uint32_t i;

    if (count == 0u) {
        return 0.0f;                            /* (defensive; ROM tables n/a) */
    }

    if (!(x < rom_f32(ax_addr + 4u * (count - 1u)))) {
        i = count - 1u;                         /* x >= last  -> clamp high */
    } else if (x < rom_f32(ax_addr)) {
        i = 0u;                                 /* x < first  -> clamp low  */
    } else {
        for (i = 0u; i + 1u < count; i++) {
            if (x < rom_f32(ax_addr + 4u * (i + 1u))) {
                break;
            }
        }
        {
            float x0 = rom_f32(ax_addr + 4u * i);
            float x1 = rom_f32(ax_addr + 4u * (i + 1u));
            float d0 = x - x0;                  /* fsub (exact)              */
            float d1 = x1 - x0;                 /* fsub (exact)              */
            t = (float)((double)d0 / (double)d1);   /* fdiv, emulator-exact  */
        }
    }

    if (type != 4u) {
        /* Only the u8-cell form is used by these tables; other cell types
         * dispatch to different ROM leaves (0x2098). */
        return 0.0f;
    }
    {
        float y0 = (float)*(const uint8_t *)(uintptr_t)(vp_addr + i);
        float interp;

        if (t == 0.0f) {                        /* fcmp/eq, incl. -0.0      */
            interp = y0;
        } else {
            float y1 = (float)*(const uint8_t *)(uintptr_t)(vp_addr + i + 1u);
            float diff = y1 - y0;               /* exact (u8 cells)          */
            interp = (float)((double)y0 + (double)t * (double)diff); /* fmac */
        }
        return (float)((double)scale * (double)interp + (double)offset); /* fmac */
    }
}

/* ---- 0x2404 — fpu_compare_and_select (clamp leaf, called once via jsr).
 *
 * ROM:
 *     fcmp/gt fr5,fr4     ; T = (val > lo)
 *     bt     0x240E
 *     bra    0x241A / fmov fr5,fr7   ; val <= lo  -> result = lo
 *     fcmp/gt fr4,fr6     ; T = (hi > val)
 *     bt     0x2418 / fmov fr4,fr7   ; hi  > val  -> result = val
 *     bra    0x241A / fmov fr6,fr7   ; val >= hi  -> result = hi
 *     rts    / fmov fr7,fr0
 *
 * I.e. clamp(val, lo, hi); with a NaN `val` both fcmp/gt are unordered so the
 * result is `lo`, matching the C comparisons below. */
static float rx8_clamp_2404(float val, float lo, float hi)
{
    if (val > lo) {
        if (hi > val) {
            return val;
        }
        return hi;
    }
    return lo;
}

/* ---- 0x13E6C — RPM-conditional maximum knock retard limit.
 *
 *      return clamp(knock_retard,
 *                   table1D_lookup(table_select(sensor, flag, sec), rpm),
 *                   f32[0x79878]);
 *
 *      table_select:  sensor==1 -> (sec >= thr) ? A : B   (sign-extended cmp)
 *                     sensor==0 -> (flag <= thr && flag != 0) ? A : B
 *                     else      -> B                        (zero-extended)
 *      thr = u8 ROM[0x79838] = 5.                                            */
float rx8_limit_knock_retard_max(float knock_retard)
{
    float    rpm;
    uint8_t  sensor, flag, sec;
    uint32_t desc_addr;
    float    lo, hi;

    rpm    = IOF(RAM_ENGINE_RPM);
    sensor = IO8(RAM_SENSOR);
    flag   = IO8(RAM_FLAG);
    sec    = IO8(RAM_SEC);

    if (sensor == 1u) {
        /* ROM 0x13E8E `cmp/hs r2,r0` compares the two mov.b SIGN-extended
         * byte values as unsigned 32-bit, so a sec byte >= 0x80 always
         * passes the threshold regardless of its numeric value. */
        int32_t sec_s = (int32_t)(int8_t)sec;
        int32_t thr_s = (int32_t)(int8_t)rom_u8(ROM_THRESHOLD);
        desc_addr = ((uint32_t)sec_s >= (uint32_t)thr_s)
                        ? ROM_TABLE_A : ROM_TABLE_B;
    } else if (sensor == 0u) {
        /* flag and threshold are zero-extended (extu.b) before the unsigned
         * cmp/gt; table A only inside (0, threshold]. */
        if ((uint32_t)flag > (uint32_t)rom_u8(ROM_THRESHOLD) || flag == 0u) {
            desc_addr = ROM_TABLE_B;
        } else {
            desc_addr = ROM_TABLE_A;
        }
    } else {
        desc_addr = ROM_TABLE_B;
    }

    lo = rx8_table1d_lookup_2068(desc_addr, rpm);
    hi = rom_f32(ROM_CLAMP_UPPER);
    return rx8_clamp_2404(knock_retard, lo, hi);
}

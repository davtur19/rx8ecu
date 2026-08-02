/*
 * =============================================================================
 * rx8_calc_adaptive_fuel_trim.c  —  ADAPTIVE FUEL TRIM CALCULATION
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x1379C  (228 bytes, 0x1379C..0x1387E)
 * Status      : VERIFIED — behavioural equivalence to the ROM bytes held by
 *               reconstructed/samples/tests/harness_calc_adaptive_fuel_trim.py
 *               (host-gcc + mmap vs tools/sh2emu.py over edge + N random
 *               vectors; every side-effected RAM cell compared bit-for-bit;
 *               0 mismatches).
 * Lift (truth): c/calc_adaptive_fuel_trim.c (same address).  The lift is a
 *               BEHAVIOURAL reconstruction written before the RAM cell map was
 *               resolved; the discrepancies listed at the bottom were found by
 *               diffing it against the 60E1D400.bin disassembly during this
 *               lift and are corrected here — the ROM bytes executed by
 *               tools/sh2emu.py are the ground truth.
 *
 * WHAT THE FUNCTION DOES
 * ----------------------
 * Long-term ("adaptive") fuel trim.  Called from engineControlCalculateTiming
 * Phase 2.  The ROM body (60E1D400.bin @0x1379C, prologue pushes r14/r13/
 * fr15/fr14/pr):
 *
 *     fmov.s @0xFFFFB5B8,fr15      ; rpm
 *     fmov.s @0xFFFFC12C,fr14      ; coolant temp
 *     fmov.s @0xFFFFB5C4,fr3       ; lambda feedback
 *     fsub   fr3,fr2               ; fr2 = rpm - lambda        (error)
 *     fmov.s fr2,@0xFFFFA728       ; RAM[0xA728] = error
 *     mov.b  @0xFFFFB5A4,r3 / tst r3,r3 ; enable flag
 *     bf     sel_enabled           ; enable != 0 -> select by 0xFFFFB5AA
 *     mov.b  @0xFFFFB5AC,r3 / tst r3,r3 ; enable == 0 -> select by 0xFFFFB5AC
 *     (0 -> desc 0x6A868, else -> desc 0x6A87C)
 *     jsr    @0x00002068           ; table1D_lookup(desc, fr4 = error)
 *     fmov.s fr0,@0xFFFFA720       ; RAM[0xA720] = trim         (always)
 *     mov.b  @0xFFFFAADA,r0 / cmp/eq #1   ; closed-loop flag
 *     bf     f15_zero              ; closed_loop != 1 -> fr15 = 0.0
 *     fmov.s @0x72C60,fr3          ; fr3 = 1500.0
 *     fcmp/gt fr15,fr3 / bf f15_zero      ; rpm >= 1500.0 -> fr15 = 0.0
 *     fmov.s @0x72C64,fr2          ; fr2 = 0.009765625
 *     fmov.s @0xFFFFC084,fr1       ; fr1 = coolant_status (float)
 *     fcmp/gt fr1,fr2 / bt trim_ok        ; 0.009765625 > coolst -> use trim
 *     mov.w  @0xFFFFA424,r0        ; rpm_raw (u16)
 *     mov.w  @0x72C5C,r3           ; 375
 *     cmp/hs r3,r0 / bf f15_zero   ; rpm_raw < 375 -> fr15 = 0.0
 *   trim_ok:
 *     fmov.s @0xFFFFA720,fr15      ; fr15 = trim
 *   f15_zero:
 *     fldi0 fr15                   ; fr15 = 0.0
 *     fmov.s @0x72C68,fr5          ; fr5 = 0.6
 *     mova   0x138B8,r0            ; fr3 = -0.045
 *     fadd   fr3,fr4               ; fr4 = 0.6 + (-0.045, 0xBD3851EB)
 *                                    ;     = 0.555... (hysteresis lo)
 *     fcmp/gt fr14,fr5 / bt hyst   ; coolant >= 0.6 -> status = 1
 *     mov.b  #1,@0xFFFFA730
 *     bra    done
 *   hyst:
 *     fcmp/gt fr14,fr4 / bf done   ; coolant < 0.555 -> status = 0
 *     mov.b  #0,@0xFFFFA730        ; else (0.555..0.6): status unchanged
 *   done:
 *     mov.b  @0xFFFFA730,r0 / cmp/eq #1 / bf skip_clamp
 *     jsr    @0x00002404           ; clamp(fr15, -2.8, 0.7) via leaf 0x2404
 *     fmov.s fr15,@0xFFFFA718      ; RAM[0xA718] = fr15 (final)
 *
 * Net behaviour (fr15 is the "leading" value stored to RAM[0xFFFFA718]):
 *
 *     error = f32(rpm - lambda)
 *     RAM[0xFFFFA728] = error
 *     desc  = (enable == 0) ? (select == 0 ? 0x6A868 : 0x6A87C)
 *                           : (flag   == 1 ? 0x6A868 : 0x6A87C)
 *     trim  = table1D_lookup(desc, error)          (u8 cells, scale 0.25,
 *                                                   offset -32.0, axis -100..100)
 *     RAM[0xFFFFA720] = trim
 *
 *     if (closed_loop == 1 && rpm < 1500.0f &&
 *         (0.009765625f > coolant_status || rpm_raw >= 375))
 *         f15 = trim;
 *     else
 *         f15 = 0.0f;
 *
 *     if (coolant >= 0.6f)      status = 1;
 *     else if (coolant < f32(0.6f + -0.045f)) status = 0;
 *     else                      status = status_prev;      (hysteresis band)
 *     RAM[0xFFFFA730] = status;
 *
 *     if (status == 1) f15 = clamp(f15, -2.8f, 0.7f);
 *     RAM[0xFFFFA718] = f15;
 *
 * RAM side effects (all cells the harness compares):
 *   written: 0xFFFFA728 f32 error  (rpm - lambda)
 *            0xFFFFA720 f32 trim   (table lookup result)
 *            0xFFFFA730 u8  closed-loop / coolant-hysteresis status
 *            0xFFFFA718 f32 final  (gated + clamped value)
 *   read:    0xFFFFB5B8 f32 rpm
 *            0xFFFFB5C4 f32 lambda
 *            0xFFFFC12C f32 coolant temperature
 *            0xFFFFB5A4 u8  adaptive-trim enable flag
 *            0xFFFFB5AC u8  table-select flag      (enable == 0 path)
 *            0xFFFFB5AA u8  table-select flag      (enable != 0 path)
 *            0xFFFFAADA u8  closed-loop flag
 *            0xFFFFC084 f32 coolant status (vs 0.009765625)
 *            0xFFFFA424 u16 engine RPM (raw, vs 375)
 *            0xFFFFA730 u8  status pre-state        (hysteresis band only)
 *
 * CALLING CONVENTION / CALLEES
 * ----------------------------
 * `void rx8_calc_adaptive_fuel_trim(void)` — no ABI arguments, no meaningful
 * return value; the whole effect is the RAM side effects above.  The ROM
 * internally jsr's THREE non-ABI leaves whose REAL ROM bytes the emulator
 * executes; the host sample inlines their net semantics as static helpers
 * (exactly like rx8_calc_idle_speed_target.c inlines its leaves):
 *
 *   - table1D_lookup @0x2068   (r4 = descriptor, fr4 = x; returns fr0):
 *         axis search @0x2624 (returns r0 = index, fr0 = t, clamped to
 *         t = 0.0 at both ends), then dispatch @0x2098 on the descriptor
 *         cell-type byte; the calibration tables here are type 4 (u8 cells,
 *         leaf 0x26B0), final result = scale * interp + offset.
 *   - axis search @0x2624      (fr0 = x, r1 = axis, r0 = count)
 *   - u8 interpolate leaf @0x26B0 (r0 = index, r1 = values, fr0 = t)
 *   - fpu_compare_and_select @0x2404 (fr4 = val, fr5 = lo, fr6 = hi;
 *         returns fr0) — the clamp, inlined as rx8_clamp_2404().
 *
 * FP EXACTNESS
 * ------------
 * The FP arithmetic is: one fsub (error = rpm - lambda), the lookup's fsub/fdiv
 * (axis interpolation) and two fmac (leaf interpolate, scale*interp+offset),
 * one fadd (0.6 + -0.045), and pure comparisons everywhere else.  The
 * emulator computes every FP op in double precision and rounds to single once
 * (ts()): for fadd/fsub/fmul that equals a native C `float` op (the exact
 * result of two singles fits a double), but fdiv and fmac need the double
 * intermediate written explicitly — `(float)((double)a / (double)b)` and
 * `(float)((double)a * (double)b + (double)c)` — to stay bit-exact with the
 * emulator.  All branch conditions are fcmp/gt / fcmp/eq / cmp/hs, which
 * report unordered (false) for NaN exactly like the C operators used here.
 *
 * ROM constants are big-endian; the host oracle mmap()s the ROM pages straight
 * from the stock bin, so all multi-byte calibration reads here go through
 * explicit byte assembly (rom_u16 / rom_u32 / rom_f32) exactly as
 * rx8_calc_idle_speed_target.c does — identical value on both sides.
 *
 * DISCREPANCIES vs c/calc_adaptive_fuel_trim.c (fixed here)
 * --------------------------------------------------------
 *   1. ERROR INPUT.  The lift's Phase 1 uses a placeholder reference
 *      ("address unknown"); the ROM computes the error directly as
 *      `rpm - lambda` (fsub of RAM[0xFFFFB5B8] and RAM[0xFFFFB5C4]).
 *   2. TABLE SELECTION.  The lift selects by table_select first and enables
 *      second, inverted vs the ROM: enable==0 selects by RAM[0xFFFFB5AC]
 *      (0 -> primary, else -> secondary); enable!=0 selects by RAM[0xFFFFB5AA]
 *      (==1 -> primary, else -> secondary).
 *   3. NO INTEGRATOR.  The lift's Phase 3 describes a "leaky integrator with
 *      gain 0.009766"; the ROM performs no accumulation at all — fr15 is a
 *      straight pass-through of the lookup result or 0.0 under the gate:
 *      closed_loop==1, rpm < 1500.0, and (coolant_status < 0.009765625 OR
 *      rpm_raw >= 375).  0x72C64 (0.009765625) is a coolant-status threshold,
 *      not an integrator gain.
 *   4. RAM[0xFFFFA730] IS A u8 STATUS BYTE, not the float "RPM threshold
 *      status" the lift names it; it is read for its pre-state and rewritten
 *      by the coolant hysteresis (0.6 / f32(0.6 - 0.045) thresholds).
 *   5. RAM[0xFFFFAADA] IS AN INPUT (closed-loop flag), not the "trailing edge
 *      fuel trim" output the lift names it — the function writes it nowhere.
 *   6. RAM[0xFFFFC084] IS A FLOAT coolant-status value compared against
 *      0.009765625; the lift treats it as a u8 "== 1" check.
 *   7. 0x72C5C IS THE u16 375 rpm_raw gate; the lift reads it as a float
 *      "error deadband".
 *   8. Clamp [-2.8, 0.7] applies only when status == 1 (RAM[0xFFFFA730]
 *      == 1); the lift clamps unconditionally.
 * =============================================================================
 */
#include <stdint.h>
#include <string.h>

#include "rx8_samples.h"

/* ---- RAM map (all addresses from the mov.w/mov.l literals of the ROM body) */
#define RAM_ENGINE_RPM          0xFFFFB5B8u  /* f32  engine speed             */
#define RAM_LAMBDA_FEEDBACK     0xFFFFB5C4u  /* f32  lambda / O2 feedback     */
#define RAM_COOLANT_TEMP        0xFFFFC12Cu  /* f32  coolant temperature      */
#define RAM_COOLANT_STATUS      0xFFFFC084u  /* f32  coolant status           */
#define RAM_RPM_RAW             0xFFFFA424u  /* u16  engine speed (raw)       */
#define RAM_TRIM_ENABLE         0xFFFFB5A4u  /* u8   adaptive-trim enable     */
#define RAM_TRIM_TABLE_SELECT   0xFFFFB5ACu  /* u8   table select (enable==0) */
#define RAM_TRIM_FLAG           0xFFFFB5AAu  /* u8   table select (enable!=0) */
#define RAM_CLOSED_LOOP_ACTIVE  0xFFFFAADAu  /* u8   closed-loop flag         */
#define RAM_TRIM_ERROR          0xFFFFA728u  /* f32  error output             */
#define RAM_TRIM_OUTPUT         0xFFFFA720u  /* f32  trim output              */
#define RAM_TRIM_STATUS         0xFFFFA730u  /* u8   status (in+out)          */
#define RAM_TRIM_LEADING        0xFFFFA718u  /* f32  gated/clamped output     */

/* ---- Calibration constants / tables (real stock values; the oracle maps the
 *      ROM pages so both sides read identical big-endian bytes) ------------ */
#define ROM_RPM_THRESHOLD       0x00072C60u  /* f32  1500.0  (rpm gate)       */
#define ROM_COOL_STATUS_THRESH  0x00072C64u  /* f32  0.009765625            */
#define ROM_RPM_RAW_THRESH      0x00072C5Cu  /* u16  375     (rpm_raw gate)   */
#define ROM_STATUS_HI           0x00072C68u  /* f32  0.6     (status ON)      */
#define ROM_STATUS_HYST         0x000138B8u  /* f32  -0.045 (0xBD3851EB)     */
#define ROM_TRIM_CLAMP_LO       0x00072C6Cu  /* f32  -2.8                     */
#define ROM_TRIM_CLAMP_HI       0x00072C70u  /* f32  0.7                      */
#define ROM_TABLE_PRIMARY       0x0006A868u  /* 1D descriptor (9 u8 cells)    */
#define ROM_TABLE_SECONDARY     0x0006A87Cu  /* 1D descriptor (9 u8 cells)    */

#define IO8(a)   (*(volatile uint8_t *)(uintptr_t)(a))
#define IO16(a)  (*(volatile uint16_t *)(uintptr_t)(a))
#define IOF(a)   (*(volatile float   *)(uintptr_t)(a))

/* Big-endian ROM reads: the SH-2E stores multi-byte constants big-endian, so
 * a straight little-endian dereference on the host would byte-swap them. */
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

/* ---- 0x1379C — adaptive fuel trim calculation (void; result is RAM). ---- */
void rx8_calc_adaptive_fuel_trim(void)
{
    float    rpm, coolant, lambda, coolant_status;
    uint8_t  enable, table_select, trim_flag, closed_loop;
    uint16_t rpm_raw;
    uint32_t desc_addr;
    float    error, trim, f15, status_hi, f555;
    uint8_t  status;

    rpm            = IOF(RAM_ENGINE_RPM);
    coolant        = IOF(RAM_COOLANT_TEMP);
    lambda         = IOF(RAM_LAMBDA_FEEDBACK);
    coolant_status = IOF(RAM_COOLANT_STATUS);
    enable         = IO8(RAM_TRIM_ENABLE);
    table_select   = IO8(RAM_TRIM_TABLE_SELECT);
    trim_flag      = IO8(RAM_TRIM_FLAG);
    closed_loop    = IO8(RAM_CLOSED_LOOP_ACTIVE);
    rpm_raw        = IO16(RAM_RPM_RAW);

    /* error = rpm - lambda (one fsub); published before the table work. */
    error = rpm - lambda;
    IOF(RAM_TRIM_ERROR) = error;

    /* Table selection: enable==0 keys off 0xFFFFB5AC, enable!=0 keys off
     * 0xFFFFB5AA (==1). */
    if (enable == 0u) {
        desc_addr = (table_select == 0u) ? ROM_TABLE_PRIMARY
                                         : ROM_TABLE_SECONDARY;
    } else {
        desc_addr = (trim_flag == 1u) ? ROM_TABLE_PRIMARY
                                      : ROM_TABLE_SECONDARY;
    }
    trim = rx8_table1d_lookup_2068(desc_addr, error);
    IOF(RAM_TRIM_OUTPUT) = trim;

    /* f15 gate: closed loop + rpm below 1500.0 + (coolant status below
     * 0.009765625 OR raw rpm at/above 375) -> trim, else 0.0. */
    f15 = 0.0f;
    if (closed_loop == 1u && rpm < rom_f32(ROM_RPM_THRESHOLD)) {
        if (rom_f32(ROM_COOL_STATUS_THRESH) > coolant_status ||
            rpm_raw >= rom_u16(ROM_RPM_RAW_THRESH)) {
            f15 = trim;
        }
    }

    /* Coolant hysteresis status byte (u8, pre-state read + rewrite). */
    status     = IO8(RAM_TRIM_STATUS);
    status_hi  = rom_f32(ROM_STATUS_HI);        /* 0.6   */
    f555       = status_hi + rom_f32(ROM_STATUS_HYST);  /* fadd, ~0.555 */
    if (status_hi > coolant) {
        if (f555 > coolant) {
            status = 0u;
        }
    } else {
        status = 1u;
    }
    IO8(RAM_TRIM_STATUS) = status;

    /* Clamp the leading value only while status == 1. */
    if (status == 1u) {
        f15 = rx8_clamp_2404(f15, rom_f32(ROM_TRIM_CLAMP_LO),
                             rom_f32(ROM_TRIM_CLAMP_HI));
    }
    IOF(RAM_TRIM_LEADING) = f15;
}

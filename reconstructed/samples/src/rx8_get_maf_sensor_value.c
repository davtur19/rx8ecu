/*
 * =============================================================================
 * rx8_get_maf_sensor_value.c  —  MAF SENSOR ADC -> VOLTAGE -> 2-D LOOKUP -> RANGE
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x745C
 * Status      : VERIFIED — behavioural equivalence to the ROM bytes held by
 *               reconstructed/samples/tests/harness_get_maf_sensor_value.py
 *               (host-gcc vs tools/sh2emu.py over 20000 random + edge vectors;
 *               bit-exact IEEE-754 single-precision MAF flow, byte-exact status,
 *               real f32 MAF table descriptor @0x6A0E4 of this ROM; 0 mismatches).
 * Lift (truth): c/maf_sensor_value.c  (getMAFSensorValue @ 0x745C)
 *
 * DISCREPANCIES FOUND IN THE LIFT (c/maf_sensor_value.c) — corrected here:
 *   1. Status logic was inverted for the low/normal branches and used `>` for
 *      the high branch.  The ROM (disassembly 0x7486-0x74A6) is:
 *          adc >= upper  -> status 1   (over-range HIGH)
 *          adc >= lower  -> status 0   (normal)
 *          else          -> status 2   (over-range LOW)
 *      i.e. `cmp/ge` (>=), and normal (0) sits between low (2) and high (1) —
 *      the lift had `> upper -> 1; >= lower -> 2; else -> 0`.
 *   2. Threshold addresses were TODO placeholders.  The ROM reads the limits at
 *      0x6CF02 (upper = 0xFAE1 = 64225) and 0x6CF04 (lower = 0x0AC0 = 2752),
 *      NOT 0x6D402/0x6D404 (which hold 0x0000 / the f32 1.0 pattern).
 *   3. MAF calibration table address was the VALUES array, not the descriptor.
 *      The ROM passes descriptor 0x6A0E4 to TwoDLookup @0x2068 (type 0, f32
 *      cells, 48 breakpoints 0.859..4.688 V -> 1.946..365.2 g/s).  0x6FBD8 is
 *      merely that descriptor's values pointer (+8).
 *   4. Scale constant: the lift's `7.62939e-5f` rounds to bits 0x389FFFFA; the
 *      ROM literal @0x74B4 is 0x38A00000 = 7.62939453125e-5 = 5.0/65536.  The
 *      lift constant is 6 ULP low and shifts the flow for every input.
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * Periodically reads the MAF sensor's raw ADC, scales the 16-bit count to a
 * 0-5 V voltage, interpolates the MAF "voltage -> g/s" calibration curve, stores
 * the result and flags sensor over-range.  Disassembly of 60E1D400.bin @0x745C:
 *
 *     2FE6   mov.l  r14,@-r15           ; prologue (r14 + pr)
 *     4F22   sts.l  pr,@-r15
 *     DE13   mov.l  @(0x13,pc),r14      ; r14 = 0xFFFF9EEA (MAF raw ADC, u16)
 *     6EE1   mov.w  @r14,r14            ; r14 = sign-extended ADC count
 *     C713   mova   0x74B4,r0           ; r0 = &scale literal (0x38A00000)
 *     63ED   extu.w r14,r3              ; r3 = (u16)adc
 *     D413   mov.l  @(0x13,pc),r4       ; r4 = 0x6A0E4 (MAF cal descriptor)
 *     435A   lds    r3,fpul
 *     F208   fmov.s @r0,fr2             ; fr2 = scale
 *     F32D   float  fpul,fr3            ; fr3 = (float)adc
 *     D312   mov.l  @(0x12,pc),r3       ; r3 = 0x2068 (TwoDLookup)
 *     F43C   fmov   fr3,fr4
 *     430B   jsr    @r3                 ; TwoDLookup(desc=0x6A0E4, x=voltage)
 *     F422   fmul   fr2,fr4             ;   (delay) fr4 = scale*(float)adc = V
 *     D211   mov.l  @(0x11,pc),r2       ; r2 = 0xFFFF9F78 (MAF flow, float)
 *     65ED   extu.w r14,r5              ; r5 = (u16)adc
 *     D112   mov.l  @(0x0E,pc),r1       ; r1 = 0x6CF02 (upper limit addr)
 *     F20A   fmov.s fr0,@r2             ; *(float*)0xFFFF9F78 = flow
 *     D410   mov.l  @(0x0C,pc),r4       ; r4 = 0xFFFF9F7C (status byte)
 *     6311   mov.w  @r1,r3
 *     633D   extu.w r3,r3
 *     3533   cmp/ge r3,r5               ; T = (adc >= upper)
 *     8F03   bf/s   0x7492
 *     0009   nop
 *     E001   mov    #0x01,r0
 *     A00B   bra    0x74A8
 *     2400   mov.b  r0,@r4              ;   (delay) status = 1
 *     D00E   mov.l  @(0x0E,pc),r0       ; r0 = 0x6CF04 (lower limit addr)
 *     6301   mov.w  @r0,r3
 *     633D   extu.w r3,r3
 *     3533   cmp/ge r3,r5               ; T = (adc >= lower)
 *     8D03   bt/s   0x74A4
 *     0009   nop
 *     E202   mov    #0x02,r2
 *     A002   bra    0x74A8
 *     2420   mov.b  r2,@r4              ;   (delay) status = 2
 *     E300   mov    #0x00,r3
 *     2430   mov.b  r3,@r4              ; status = 0
 *     4F26   lds.l  @r15+,pr
 *     000B   rts
 *     6EF6   mov.l  @r15+,r14           ;   (delay)
 *
 * The input is the u16 ADC at 0xFFFF9EEA; the outputs are the float MAF value
 * at 0xFFFF9F78 and the u8 status at 0xFFFF9F7C.  There is no ABI return value.
 *
 * CALLING CONVENTION
 * ------------------
 * `void rx8_get_maf_sensor_value(void)` — no arguments, no return.  Internally
 * it makes one REAL ABI call via `jsr` to TwoDLookup @0x2068 (r4 = descriptor
 * pointer, fr4 = input; float result in fr0) whose actual ROM bytes are
 * executed by the emulator harness.  The host C build cannot run those ROM
 * bytes, so the sample declares `rx8_twod_lookup()` extern and the ORACLE
 * supplies a faithful model of TwoDLookup's type-0 path (axis search + f32-cell
 * interpolation handler @0x2678, see c/2DLookup.c — already Track-A verified at
 * 0x2068) — see tests/oracle_get_maf_sensor_value.c.
 *
 * FP EXACTNESS
 * ------------
 *   - `voltage = (float)adc * scale` is one fmul (single rounding).
 *   - The type-0 handler @0x2678 computes `cells[i+1] - cells[i]` with one fsub
 *     then one fused `fmac fr0,fr1,fr2` (SINGLE rounding); `fmaf(t, v1-v0, v0)`
 *     reproduces that exactly (a plain `v0 + t*(v1-v0)` double-rounds).
 *   - The handler's `fcmp/eq t,0` fast path returns the raw cell when t == 0.0
 *     (e.g. x exactly on a breakpoint or a clamp) — modelled as `t == 0.0f`.
 *
 * ROM constants are big-endian; the host oracle mmap()s the ROM pages, so all
 * 16/32-bit reads here go through explicit byte assembly (rom_u16) — identical
 * value on both sides.
 * =============================================================================
 */
#include <stdint.h>

#include "rx8_samples.h"

/* Fixed machine addresses, straight from the mov.l literals of the ROM body. */
#define RX8_MAF_ADC_ADDR      0xFFFF9EEAu   /* u16 MAF raw ADC count (input)   */
#define RX8_MAF_FLOW_ADDR     0xFFFF9F78u   /* float processed MAF value (g/s) */
#define RX8_MAF_STATUS_ADDR   0xFFFF9F7Cu   /* u8  MAF status (0=OK 1=high 2=low) */
#define RX8_MAF_CAL_DESC      0x006A0E4u    /* TwoDLookup descriptor (type 0)  */
#define RX8_MAF_UPPER_LIMIT   0x006CF02u    /* u16 over-range HIGH threshold   */
#define RX8_MAF_LOWER_LIMIT   0x006CF04u    /* u16 over-range LOW threshold    */

/* ROM literal @0x74B4, bits 0x38A00000 = 7.62939453125e-5 = 5.0V / 65536. */
#define RX8_MAF_SCALE         7.62939453125e-5f

/* TwoDLookup @0x2068 — real ABI callee (jsr @0x2068 in the ROM body).  The
 * emulator harness runs the ACTUAL ROM bytes of the callee; on the host build
 * this is provided by the oracle (see oracle_get_maf_sensor_value.c). */
extern float rx8_twod_lookup(const void *desc, float x);

/* Big-endian u16 read: the ROM holds constants big-endian (SH-2E), so a
 * straight little-endian dereference on the host would byte-swap them. */
static uint16_t rom_u16(uint32_t addr)
{
    const uint8_t *p = (const uint8_t *)(uintptr_t)addr;
    return (uint16_t)((uint16_t)p[0] << 8) | p[1];
}

void rx8_get_maf_sensor_value(void)
{
    uint16_t adc = *(volatile uint16_t *)(uintptr_t)RX8_MAF_ADC_ADDR;
    float voltage;
    float flow;

    /* Scale the 16-bit ADC count to a 0-5 V voltage (one fmul, single rounding)
     * and interpolate the MAF calibration curve (f32 cells, type 0). */
    voltage = (float)adc * RX8_MAF_SCALE;
    flow = rx8_twod_lookup((const void *)(uintptr_t)RX8_MAF_CAL_DESC, voltage);
    *(volatile float *)(uintptr_t)RX8_MAF_FLOW_ADDR = flow;

    /* Range status: 1 = at/above upper limit, 0 = normal, 2 = below lower. */
    uint8_t status;
    if (adc >= rom_u16(RX8_MAF_UPPER_LIMIT)) {
        status = 1;
    } else if (adc >= rom_u16(RX8_MAF_LOWER_LIMIT)) {
        status = 0;
    } else {
        status = 2;
    }
    *(volatile uint8_t *)(uintptr_t)RX8_MAF_STATUS_ADDR = status;
}

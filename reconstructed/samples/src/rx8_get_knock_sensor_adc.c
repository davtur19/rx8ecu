/*
 * =============================================================================
 * rx8_get_knock_sensor_adc.c  —  KNOCK SENSOR STATE INITIALISATION
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0xC3CE  (120 bytes: 0xC3CE..0xC445; the body is shared with
 *                knockRelatedInit @0xC3C8, which pushes r13/r12/r11 and falls
 *                through into this entry, then pops them in the rts delay slot)
 * Status      : VERIFIED — behavioural equivalence to the ROM bytes held by
 *               reconstructed/samples/tests/harness_get_knock_sensor_adc.py
 *               (host-gcc + mmap vs tools/sh2emu.py over 20000 random + edge
 *               pre-states; byte-exact big-endian RAM side-effects incl. every
 *               store-width sentinel; 0 mismatches).
 *
 * LIFTS (truth source candidates) — ALL DISAGREE WITH THIS ROM, see below:
 *   c/getKnockSensorADC.c        @0xC3CE — describes a first-order-FILTER
 *                                read function (that is 60E0FC00.bin's function
 *                                at 0xC3CE).  WRONG for 60E1D400.bin.
 *   c/knock_sensor_adc_read.c    @0xC3CE — duplicate lift, same filter
 *                                behaviour, also wrong for 60E1D400.bin (its
 *                                RAM map is largely right; its filter/ADC
 *                                reads are not).
 *   c/knockRelatedInit.c         @0xC3C8 — same body, but lift has errors:
 *                                reads ADC from RAM 0xFFFF9F0E / RPM float
 *                                0xFFFF9F80 (the ROM reads ROM calibration),
 *                                uses 0xFFFFA37A for copy 1 (ROM writes
 *                                0xFFFFA37E), and models the rotor loop as a
 *                                single rotor.
 *   The ROM bytes win on every discrepancy (emulator executes the REAL ROM).
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * Startup/periodic initialisation of the knock-detection state block in
 * on-chip RAM.  The body (60E1D400.bin @0xC3CE) is pure straight-line code +
 * one 2-iteration loop; it makes NO RAM reads, NO calls, and copies the knock
 * sensor calibration into the RAM working copies.  Disassembly:
 *
 *     D231  mov.l @(0x31,pc),r2     ; r2 = 0x0007A178 (cal u16 #1)
 *     6321  mov.w @r2,r3
 *     D131  mov.l @(0x31,pc),r1     ; r1 = 0xFFFFA37E (copy 1)
 *     2131  mov.w r3,@r1            ; *(u16*)0xFFFFA37E = cal1 (0x005E)
 *     D331  mov.l @(0x31,pc),r3     ; r3 = 0x0007A17A (cal u16 #2)
 *     6031  mov.w @r3,r0
 *     D231  mov.l @(0x31,pc),r2     ; r2 = 0xFFFFA37C (copy 2)
 *     2201  mov.w r0,@r2            ; *(u16*)0xFFFFA37C = cal2 (0x00C1)
 *     D131  mov.l @(0x31,pc),r1     ; r1 = 0x0007A1A4 (cal f32)
 *     F318  fmov.s @r1,fr3
 *     D331  mov.l @(0x31,pc),r3     ; r3 = 0xFFFFA328 (ref float)
 *     F33A  fmov.s fr3,@r3          ; *(float*)0xFFFFA328 = 3.6875
 *     C731  mova   0xC4B0,r0        ; r0 = &pool float (0x41200000 = 10.0)
 *     F508  fmov.s @r0,fr5
 *     D231  mov.l @(0x31,pc),r2     ; r2 = 0xFFFFA360 (filter gain)
 *     F25A  fmov.s fr5,@r2          ; *(float*)0xFFFFA360 = 10.0
 *     D731  mov.l @(0x31,pc),r7     ; r7 = 0x0007A1D0 (cal f32 #2)
 *     F378  fmov.s @r7,fr3
 *     D331  mov.l @(0x31,pc),r3     ; r3 = 0xFFFFA364 (secondary param)
 *     F33A  fmov.s fr3,@r3          ; *(float*)0xFFFFA364 = 64.0
 *     914C  mov.w @(0x1C,pc),r1     ; r1 = 0x00FF (pool word)
 *     D031  mov.l @(0x31,pc),r0     ; r0 = 0xFFFFA384 (max byte)
 *     D231  mov.l @(0x31,pc),r2     ; r2 = 0xFFFFA385 (counter)
 *     2010  mov.b r1,@r0            ; *(u8*)0xFFFFA384 = 0xFF
 *     D331  mov.l @(0x31,pc),r3     ; r3 = 0xFFFFA386 (fault byte)
 *     E000  mov   #0x00,r0
 *     2200  mov.b r0,@r2            ; *(u8*)0xFFFFA385 = 0
 *     F48D  fldi0 fr4               ; fr4 = 0.0
 *     D231  mov.l @(0x31,pc),r2     ; r2 = 0xFFFFA32C (filter state)
 *     6603  mov   r0,r6             ; r6 = 0 (loop counter)
 *     DD32  mov.l @(0x31,pc),r13    ; r13 = 0x0007A164 (sensor-ID table)
 *     2300  mov.b r0,@r3            ; *(u8*)0xFFFFA386 = 0
 *     D12E  mov.l @(0x31,pc),r1     ; r1 = 0xFFFFA324 (fault byte 2)
 *     2100  mov.b r0,@r1            ; *(u8*)0xFFFFA324 = 0
 *     F24A  fmov.s fr4,@r2          ; *(float*)0xFFFFA32C = 0.0
 *     E102  mov   #0x02,r1          ; r1 = 2 (loop limit)
 *     D32E  mov.l @(0x31,pc),r3     ; r3 = 0xFFFFA348 (filter state A)
 *     E000  mov   #0x00,r0          ; r0 = 0 (byte/float offset)
 *     D52F  mov.l @(0x31,pc),r5     ; r5 = 0xFFFFA389 (sensor-ID byte)
 *     F34A  fmov.s fr4,@r3          ; *(float*)0xFFFFA348 = 0.0
 *     DA2F  mov.l @(0x31,pc),r10    ; r10 = 0xFFFFA334 (threshold A)
 *     DB30  mov.l @(0x31,pc),r11    ; r11 = 0xFFFFA368 (filter state B)
 *     DC30  mov.l @(0x31,pc),r12    ; r12 = 0xFFFFA350 (threshold B)
 *     ; ---- 2-iteration rotor loop (0xC426..0xC43A) ----
 *     7601  add   #0x01,r6          ; r6++
 *     FC57  fmov.s fr5,@(r0,r12)    ; threshold B[i]   = 10.0
 *     3613  cmp/ge r1,r6            ; T = (r6 >= 2)
 *     F378  fmov.s @r7,fr3          ; fr3 = cal f32 #2 (64.0)
 *     FB37  fmov.s fr3,@(r0,r11)    ; filter state B[i] = 64.0
 *     63D4  mov.b @r13+,r3          ; r3 = sensor-ID table[i]
 *     2530  mov.b r3,@r5            ; sensor-ID byte[i] = r3
 *     FA47  fmov.s fr4,@(r0,r10)    ; threshold A[i]   = 0.0
 *     7501  add   #0x01,r5          ; r5++
 *     8FF5  bf/s   0xC426           ; while r6 < 2
 *     7004  add   #0x04,r0          ;   (delay) r0 += 4
 *     6AF6/6BF6/6CF6  mov.l @r15+,r10/11/12
 *     000B  rts                     ; (delay slot pops r13)
 *
 * CALLING CONVENTION
 * ------------------
 * `void rx8_get_knock_sensor_adc(void)` — no ABI arguments, no return value.
 * Normal ABI prologue/epilogue (r10..r13 pushed/popped, rts via PR).  No
 * callees (no jsr/bsr in the body) — unlike the filter lift, nothing is
 * called, so there is nothing to stub on the host.
 *
 * RAM CELLS (all written unconditionally; NONE read — the function never
 * touches RAM as an input, so pre-state is irrelevant except as sentinels):
 *   role *unknown, matches ROM* unless a lift documents it:
 *
 *   0xFFFFA324  u8     fault byte 2          <- 0x00
 *   0xFFFFA328  f32    sensor ref float      <- cal @0x7A1A4   (3.6875)
 *   0xFFFFA32C  f32    filter state          <- 0.0
 *   0xFFFFA334  f32[2] per-rotor threshold A <- 0.0, 0.0
 *   0xFFFFA348  f32    per-rotor filter state A <- 0.0
 *   0xFFFFA350  f32[2] per-rotor threshold B <- 10.0, 10.0 (pool @0xC4B0)
 *   0xFFFFA360  f32    filter gain           <- 10.0
 *   0xFFFFA364  f32    secondary filter param<- cal @0x7A1D0   (64.0)
 *   0xFFFFA368  f32[2] per-rotor filter state B <- 64.0, 64.0 (cal @0x7A1D0)
 *   0xFFFFA37C  u16    ADC copy 2            <- cal @0x7A17A   (0x00C1)
 *   0xFFFFA37E  u16    ADC copy 1            <- cal @0x7A178   (0x005E)
 *   0xFFFFA384  u8     output limit byte     <- 0xFF (pool word @0xC494)
 *   0xFFFFA385  u8     counter               <- 0x00
 *   0xFFFFA386  u8     fault byte            <- 0x00
 *   0xFFFFA389  u8[2]  per-rotor sensor ID   <- ROM table @0x7A164 (1, 1)
 *
 * CALIBRATION TABLE (read from the ROM image):
 *   0x0007A164  u8[2]   per-rotor sensor-ID table (0x01, 0x01)
 *   0x0007A178  u16     0x005E = 94   (sensor cal constant 1)
 *   0x0007A17A  u16     0x00C1 = 193  (sensor cal constant 2)
 *   0x0007A1A4  f32     0x406C0000 = 3.6875
 *   0x0007A1D0  f32     0x42800000 = 64.0
 *
 * ROM LITERAL POOL of this function (not calibration):
 *   0x0000C4B0  f32     0x41200000 = 10.0   (filter gain / threshold B)
 *   0x0000C494  u16     0x00FF              (output limit byte)
 *
 * DISCREPANCIES vs THE LIFTS (corrected here):
 *   1. c/getKnockSensorADC.c and c/knock_sensor_adc_read.c describe a
 *      firstOrderFilter() ADC-read function (200<=RPM<2000 filter band, fault
 *      on RPM>=10000) — that is 60E0FC00.bin's function AT THE SAME ADDRESS.
 *      60E1D400.bin's body is a pure calibration/state init with NO filter,
 *      NO ADC read, NO call.  (The filter function of this ROM lives
 *      elsewhere, e.g. the 0xC460 knockSensorADCFault leaf, already verified
 *      as rx8_knock_sensor_adc_fault.)
 *   2. c/knockRelatedInit.c's copy 1 address (0xFFFFA37A) is wrong; the ROM
 *      writes 0xFFFFA37E.  Its claim that the filter state/gain are seeded
 *      from RAM (0xFFFF9F80 RPM ref) or that the ADC raw is copied is wrong;
 *      everything is seeded from ROM calibration constants.
 *   3. The rotor loop in c/knockRelatedInit.c models a single rotor and omits
 *      the threshold-B / filter-state-B writes; the ROM loop writes FOUR cells
 *      per rotor (threshold B, filter state B, sensor-ID byte, threshold A).
 * =============================================================================
 */
#include <stdint.h>
#include <string.h>

#include "rx8_samples.h"
#include "rx8_hw.h"

/* ---- RAM cells written by the function (see header for the full map) ---- */
#define RX8_KNOCK_FAULT2_ADDR   0xFFFFA324u   /* u8   fault byte 2            */
#define RX8_KNOCK_REF_ADDR      0xFFFFA328u   /* f32  sensor ref float        */
#define RX8_KNOCK_FLTSTATE_ADDR 0xFFFFA32Cu   /* f32  filter state            */
#define RX8_KNOCK_THR_A_BASE    0xFFFFA334u   /* f32[2] per-rotor threshold A */
#define RX8_KNOCK_FLTA_ADDR     0xFFFFA348u   /* f32  per-rotor filter state A*/
#define RX8_KNOCK_THR_B_BASE    0xFFFFA350u   /* f32[2] per-rotor threshold B */
#define RX8_KNOCK_GAIN_ADDR     0xFFFFA360u   /* f32  filter gain             */
#define RX8_KNOCK_PARAM2_ADDR   0xFFFFA364u   /* f32  secondary filter param  */
#define RX8_KNOCK_FLTB_BASE     0xFFFFA368u   /* f32[2] per-rotor filter st. B*/
#define RX8_KNOCK_COPY2_ADDR    0xFFFFA37Cu   /* u16  ADC copy 2              */
#define RX8_KNOCK_COPY1_ADDR    0xFFFFA37Eu   /* u16  ADC copy 1              */
#define RX8_KNOCK_MAXBYTE_ADDR  0xFFFFA384u   /* u8   output limit byte       */
#define RX8_KNOCK_COUNTER_ADDR  0xFFFFA385u   /* u8   counter                 */
#define RX8_KNOCK_FAULT_ADDR    0xFFFFA386u   /* u8   fault byte              */
#define RX8_KNOCK_SENSORID_ADDR 0xFFFFA389u   /* u8[2] per-rotor sensor ID    */

/* ---- ROM calibration table (see header) ---- */
#define RX8_KNOCK_SENSORID_TBL  0x0007A164u   /* u8[2] per-rotor sensor IDs   */
#define RX8_KNOCK_CAL1_ADDR     0x0007A178u   /* u16  sensor cal constant 1   */
#define RX8_KNOCK_CAL2_ADDR     0x0007A17Au   /* u16  sensor cal constant 2   */
#define RX8_KNOCK_CALF_ADDR     0x0007A1A4u   /* f32  sensor ref float value  */
#define RX8_KNOCK_THRESH_ADDR   0x0007A1D0u   /* f32  filter-state B value    */

/* ---- ROM literal pool of this function (embedded; not calibration) -------
 *   0xC4B0: 0x41200000 = 10.0f   (filter gain / per-rotor threshold B)
 *   0xC494: 0x00FF               (output limit byte) */
#define RX8_KNOCK_GAIN_VALUE    10.0f
#define RX8_KNOCK_MAXBYTE_VALUE 0xFFu

/* Big-endian ROM reads: the ROM holds constants big-endian (SH-2E), so a
 * straight little-endian dereference on the host would byte-swap them.  The
 * oracle mmap()s the ROM calibration page (see oracle_get_knock_sensor_adc.c),
 * so these helpers read the exact stock bytes. */
static uint8_t rom_u8(uint32_t addr)
{
    return *(volatile uint8_t *)(uintptr_t)addr;
}

static uint16_t rom_u16(uint32_t addr)
{
    const uint8_t *p = (const uint8_t *)(uintptr_t)addr;
    return (uint16_t)((uint16_t)p[0] << 8) | p[1];
}

static float rom_f32(uint32_t addr)
{
    const uint8_t *p = (const uint8_t *)(uintptr_t)addr;
    uint32_t u = ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16)
               | ((uint32_t)p[2] << 8) | (uint32_t)p[3];
    float f;
    memcpy(&f, &u, sizeof f);
    return f;
}

/* 0xC3CE — initialise the knock-detection state block from ROM calibration.
 * Body of knockRelatedInit @0xC3C8 as well (same code, three extra pushes). */
void rx8_get_knock_sensor_adc(void)
{
    int i;

    /* Sensor ADC calibration copies (mov.w stores, 16-bit each). */
    RX8_IO16(RX8_KNOCK_COPY1_ADDR) = rom_u16(RX8_KNOCK_CAL1_ADDR);
    RX8_IO16(RX8_KNOCK_COPY2_ADDR) = rom_u16(RX8_KNOCK_CAL2_ADDR);

    /* Sensor reference float and the two filter parameters. */
    *(volatile float *)(uintptr_t)RX8_KNOCK_REF_ADDR =
        rom_f32(RX8_KNOCK_CALF_ADDR);
    *(volatile float *)(uintptr_t)RX8_KNOCK_GAIN_ADDR = RX8_KNOCK_GAIN_VALUE;
    *(volatile float *)(uintptr_t)RX8_KNOCK_PARAM2_ADDR =
        rom_f32(RX8_KNOCK_THRESH_ADDR);

    /* Output limit byte (0xFF from the pool word) and the clear bytes. */
    RX8_IO8(RX8_KNOCK_MAXBYTE_ADDR) = RX8_KNOCK_MAXBYTE_VALUE;
    RX8_IO8(RX8_KNOCK_COUNTER_ADDR) = 0x00u;
    RX8_IO8(RX8_KNOCK_FAULT_ADDR) = 0x00u;
    RX8_IO8(RX8_KNOCK_FAULT2_ADDR) = 0x00u;

    /* Filter state + rotor A filter state start at 0.0. */
    *(volatile float *)(uintptr_t)RX8_KNOCK_FLTSTATE_ADDR = 0.0f;
    *(volatile float *)(uintptr_t)RX8_KNOCK_FLTA_ADDR = 0.0f;

    /* Per-rotor loop, exactly 2 iterations (r6 counts 1..2 vs limit 2). */
    for (i = 0; i < 2; i++) {
        *(volatile float *)(uintptr_t)(RX8_KNOCK_THR_B_BASE + 4 * (uint32_t)i)
            = RX8_KNOCK_GAIN_VALUE;                     /* threshold B */
        *(volatile float *)(uintptr_t)(RX8_KNOCK_FLTB_BASE + 4 * (uint32_t)i)
            = rom_f32(RX8_KNOCK_THRESH_ADDR);           /* filter state B */
        RX8_IO8(RX8_KNOCK_SENSORID_ADDR + (uint32_t)i)
            = rom_u8(RX8_KNOCK_SENSORID_TBL + (uint32_t)i); /* sensor ID */
        *(volatile float *)(uintptr_t)(RX8_KNOCK_THR_A_BASE + 4 * (uint32_t)i)
            = 0.0f;                                     /* threshold A */
    }
}

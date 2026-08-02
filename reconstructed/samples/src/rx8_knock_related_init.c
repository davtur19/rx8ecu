/*
 * =============================================================================
 * rx8_knock_related_init.c  —  KNOCK DETECTION SUBSYSTEM INIT
 *                              (per-rotor filter states, thresholds, sensor
 *                              IDs, fault flags, ADC-output copies)
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0xC3C8  (126 bytes: 0xC3C8..0xC445; next leaf @0xC446)
 * Status      : VERIFIED — behavioural equivalence to the ROM bytes held by
 *               reconstructed/samples/tests/harness_knock_related_init.py
 *               (host-gcc + mmap vs tools/sh2emu.py over edge + random
 *               pre-states; byte-exact RAM side effects: all 19 written
 *               cells incl. their store widths + 13 store-boundary
 *               sentinels; 0 mismatches).
 * Lift (truth): c/knockRelatedInit.c (knockRelatedInit — the ROM's
 *               per-rotor knock-filter/threshold/fault init).
 *
 * ADDRESS NOTE (discrepancy in the task address, fixed here):
 *   The task brief said "0xC1F8 (roms/stock/60E1D400.bin)" — that is the
 *   address of this function in the OLDER 60E0FC00.bin image.  In
 *   60E1D400.bin (the ROM this project verifies against) the very same
 *   function sits at 0xC3C8 and is reached by `bsr 0xC3C8` from
 *   knockFunctionInit @0xC31C (c/knockFunctionInit.c); 0xC1F8 in
 *   60E1D400.bin is unrelated code (`00 00 FF CF ...`).  The lift's own
 *   header documents both: "knockRelatedInit @ 0xC1F8 (60E0FC00) /
 *   0xC3C8 (60E1D400)".  The harness therefore drives the emulator at
 *   0xC3C8 (real 60E1D400.bin bytes); ROM wins over the brief.
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * Power-on initialisation of the knock detection subsystem, called once per
 * boot from knockFunctionInit @0xC31C (after the ATU2 timer waveform init).
 * The function has NO arguments and NO return value and performs no ABI
 * calls — it is a straight-line RAM initialisation: it publishes two fixed
 * 16-bit "ADC output" copies and six calibration floats/words taken from the
 * ROM calibration block @0x7A164..0x7A1D0 (plus its own literal-pool
 * constant 10.0), zeroes the per-rotor thresholds / filter states and the
 * fault bytes, arms the max-limit byte, and writes the two per-rotor sensor
 * IDs.  The ROM sequence (60E1D400.bin @0xC3C8) is:
 *
 *     2FD6  mov.l  r13,@-r15            ; prologue (r13,r12,r11,r10)
 *     2FC6  mov.l  r12,@-r15
 *     2FB6  mov.l  r11,@-r15
 *     2FA6  mov.l  r10,@-r15
 *     D231  mov.l  @(0x31,pc),r2        ; r2 = 0x0007A178 (cal u16 A)
 *     6321  mov.w  @r2,r3               ; r3 = *(u16*)0x7A178  = 0x005E
 *     D131  mov.l  @(0x31,pc),r1        ; r1 = 0xFFFFA37E
 *     2131  mov.w  r3,@r1               ; *(u16*)0xFFFFA37E = 0x005E   (WORD)
 *     D331  mov.l  @(0x30,pc),r3        ; r3 = 0x0007A17A (cal u16 B)
 *     6031  mov.w  @r3,r0               ; r0 = *(u16*)0x7A17A  = 0x00C1
 *     D231  mov.l  @(0x30,pc),r2        ; r2 = 0xFFFFA37C
 *     2201  mov.w  r0,@r2               ; *(u16*)0xFFFFA37C = 0x00C1   (WORD)
 *     D131  mov.l  @(0x2E,pc),r1        ; r1 = 0x0007A1A4 (cal f32)
 *     F318  fmov.s @r1,fr3              ; fr3 = *(float*)0x7A1A4 = 3.6875
 *     D331  mov.l  @(0x2E,pc),r3        ; r3 = 0xFFFFA328
 *     F33A  fmov.s fr3,@r3              ; *(float*)0xFFFFA328 = 3.6875  (4 B)
 *     C731  mova   0x0C4B0,r0           ; r0 = &literal pool @0x0C4B0
 *     F508  fmov.s @r0,fr5              ; fr5 = *(float*)0x0C4B0 = 10.0  (ROM const!)
 *     D231  mov.l  @(0x30,pc),r2        ; r2 = 0xFFFFA360
 *     F25A  fmov.s fr5,@r2              ; *(float*)0xFFFFA360 = 10.0    (4 B)
 *     D731  mov.l  @(0x2C,pc),r7        ; r7 = 0x0007A1D0 (cal f32)
 *     F378  fmov.s @r7,fr3              ; fr3 = *(float*)0x7A1D0 = 64.0
 *     D331  mov.l  @(0x2C,pc),r3        ; r3 = 0xFFFFA364
 *     F33A  fmov.s fr3,@r3              ; *(float*)0xFFFFA364 = 64.0    (4 B)
 *     914C  mov.w  0x0C494,r1           ; r1 = (s16)*0x0C494  = 0x00FF
 *     D031  mov.l  @(0x29,pc),r0        ; r0 = 0xFFFFA384 (max byte)
 *     D231  mov.l  @(0x29,pc),r2        ; r2 = 0xFFFFA385 (counter)
 *     2010  mov.b  r1,@r0               ; *(u8*)0xFFFFA384 = 0xFF       (BYTE)
 *     D331  mov.l  @(0x29,pc),r3        ; r3 = 0xFFFFA386 (fault byte)
 *     E000  mov    #0x00,r0             ; r0 = 0
 *     2200  mov.b  r0,@r2               ; *(u8*)0xFFFFA385 = 0          (BYTE)
 *     F48D  fldi0  fr4                  ; fr4 = 0.0
 *     D231  mov.l  @(0x29,pc),r2        ; r2 = 0xFFFFA32C (filter state)
 *     6603  mov    r0,r6                ; r6 = 0 (loop counter)
 *     DD32  mov.l  @(0x2C,pc),r13       ; r13 = 0x0007A164 (sensor-ID table)
 *     2300  mov.b  r0,@r3               ; *(u8*)0xFFFFA386 = 0          (BYTE)
 *     D12E  mov.l  @(0x28,pc),r1        ; r1 = 0xFFFFA324 (fault byte 2)
 *     2100  mov.b  r0,@r1               ; *(u8*)0xFFFFA324 = 0          (BYTE)
 *     F24A  fmov.s fr4,@r2              ; *(float*)0xFFFFA32C = 0.0     (4 B)
 *     E102  mov    #0x02,r1             ; r1 = 2 (loop limit)
 *     D32E  mov.l  @(0x28,pc),r3        ; r3 = 0xFFFFA348 (filter state A)
 *     E000  mov    #0x00,r0             ; r0 = 0 (float offset)
 *     D52F  mov.l  @(0x2A,pc),r5        ; r5 = 0xFFFFA389 (sensor-ID byte)
 *     F34A  fmov.s fr4,@r3              ; *(float*)0xFFFFA348 = 0.0     (4 B)
 *     DA2F  mov.l  @(0x2A,pc),r10       ; r10 = 0xFFFFA334 (threshold A)
 *     DB30  mov.l  @(0x2A,pc),r11       ; r11 = 0xFFFFA368 (filter state B)
 *     DC30  mov.l  @(0x2A,pc),r12       ; r12 = 0xFFFFA350 (threshold B)
 *   .L0:
 *     7601  add    #0x01,r6             ; iter++
 *     FC57  fmov.s fr5,@(r0,r12)        ; *(float*)(0xFFFFA350+off) = 10.0  (4 B)
 *     3613  cmp/ge r1,r6                ; T = (iter >= 2)
 *     F378  fmov.s @r7,fr3              ; fr3 = *(float*)0x7A1D0 = 64.0 (delay slot)
 *     FB37  fmov.s fr3,@(r0,r11)        ; *(float*)(0xFFFFA368+off) = 64.0 (4 B)
 *     63D4  mov.b  @r13+,r3             ; r3 = *(u8*)0x7A164++; (sensor ID)
 *     2530  mov.b  r3,@r5               ; *(u8*)0xFFFFA389+iter = ID    (BYTE)
 *     FA47  fmov.s fr4,@(r0,r10)        ; *(float*)(0xFFFFA334+off) = 0.0  (4 B)
 *     7501  add    #0x01,r5             ; sensor-ID byte ptr++
 *     8FF5  bf/s   0x0C426              ; if (iter < 2) goto .L0
 *     7004  add    #0x04,r0             ;   off += 4 (delay slot)
 *     6AF6  mov.l  @r15+,r10            ; epilogue (r10,r11,r12,r13)
 *     6BF6  mov.l  @r15+,r11
 *     6CF6  mov.l  @r15+,r12
 *     000B  rts
 *     6DF6  mov.l  @r15+,r13            ;   (delay slot)
 *
 * The two-iteration rotor loop therefore writes, in total:
 *   0xFFFFA350 / 0xFFFFA354 = 10.0 (2 x f32, "threshold" pair B),
 *   0xFFFFA368 / 0xFFFFA36C = 64.0 (2 x f32, "filter state" pair B),
 *   0xFFFFA389 / 0xFFFFA38A = sensor-ID bytes (ROM table @0x7A164),
 *   0xFFFFA334 / 0xFFFFA338 = 0.0  (2 x f32, "threshold" pair A).
 *
 * DISCREPANCIES vs THE LIFT (c/knockRelatedInit.c) — all ROM-wins here:
 *   1. "Copy raw knock ADC from 0xFFFF9F0E to 0xFFFFA37A and 0xFFFFA37C":
 *      the ROM NEVER reads 0xFFFF9F0E and NEVER writes 0xFFFFA37A (that
 *      word belongs to knockFunctionInit's threshold write @0xC31C).  It
 *      copies two FIXED calibration words 0x7A178=0x005E and
 *      0x7A17A=0x00C1 to 0xFFFFA37E and 0xFFFFA37C.
 *   2. "Set filter state (0xFFFFA374) = RPM ref (0xFFFF9F80)": the ROM does
 *      NOT touch 0xFFFFA374 (knockFunctionInit's scale float) and does NOT
 *      read 0xFFFF9F80.  0xFFFFA32C gets 0.0 (fldi0), and 0xFFFFA328 gets
 *      the calibration float 3.6875 (from 0x7A1A4), not an RPM reference.
 *   3. "Set filter gain (0xFFFFA360) = 10.0 from ROM 0x78EE0": 10.0 is
 *      right, but it comes from THIS function's own literal pool @0x0C4B0
 *      (mova + fmov.s @r0), not ROM 0x78EE0.  The same 10.0 float is also
 *      pushed to the per-rotor threshold pair 0xFFFFA350/0xFFFFA354.
 *   4. "Initialize secondary filter parameter (0xFFFFA364) from RPM ref":
 *      the ROM writes the calibration float 64.0 (0x7A1D0) to 0xFFFFA364 —
 *      and the same 64.0 to the per-rotor filter-state pair
 *      0xFFFFA368/0xFFFFA36C.  None of it comes from any RAM reference.
 *   5. "Clear fault byte 2 (0xFFFFA324), fault code (0xFFFFA325), counter
 *      (0xFFFFA385)": 0xFFFFA324 and 0xFFFFA385 are cleared, but 0xFFFFA325
 *      is NOT written by this function (knockFunctionInit clears it as its
 *      knock flag B); the second fault byte here is 0xFFFFA386.
 *   6. "Per-rotor thresholds/filter states to 0.0": only the A-pair
 *      (0xFFFFA334/0xFFFFA338) and 0xFFFFA348 are zeroed.  The B-pair
 *      threshold (0xFFFFA350/0xFFFFA354) is 10.0 and the B-pair filter
 *      state (0xFFFFA368/0xFFFFA36C) is 64.0 — the lift's "all 0.0" is
 *      wrong for four of the six floats.
 *   7. The lift's step-8/step-9 "per-rotor threshold from KNOCK_REF_FLOAT
 *      and sensor-ID-in-sequence" is functionally inverted: the sensor IDs
 *      ARE loaded from ROM 0x7A164 in the loop (correct), but the threshold
 *      copy from 0xFFFFA328 does not happen (the ROM stores fr4=0.0 there,
 *      and the loop uses the literal 10.0 / cal 64.0).
 *
 * RAM CELLS WRITTEN (addr, width, value):
 *   0xFFFFA324  u8     0x00   fault byte 2
 *   0xFFFFA328  f32    3.6875 calibration float (ROM 0x7A1A4)
 *   0xFFFFA32C  f32    0.0    filter state
 *   0xFFFFA334  f32    0.0    per-rotor threshold A[0]
 *   0xFFFFA338  f32    0.0    per-rotor threshold A[1]
 *   0xFFFFA348  f32    0.0    per-rotor filter state A
 *   0xFFFFA350  f32    10.0   per-rotor threshold B[0]
 *   0xFFFFA354  f32    10.0   per-rotor threshold B[1]
 *   0xFFFFA360  f32    10.0   filter gain (literal pool @0x0C4B0)
 *   0xFFFFA364  f32    64.0   secondary filter parameter (ROM 0x7A1D0)
 *   0xFFFFA368  f32    64.0   per-rotor filter state B[0]
 *   0xFFFFA36C  f32    64.0   per-rotor filter state B[1]
 *   0xFFFFA37C  u16    0x00C1 ADC-output copy (ROM word 0x7A17A)
 *   0xFFFFA37E  u16    0x005E ADC-output copy (ROM word 0x7A178)
 *   0xFFFFA384  u8     0xFF   max limit byte
 *   0xFFFFA385  u8     0x00   counter
 *   0xFFFFA386  u8     0x00   fault byte
 *   0xFFFFA389  u8     0x01   sensor ID rotor A (ROM table @0x7A164)
 *   0xFFFFA38A  u8     0x01   sensor ID rotor B (ROM table @0x7A165)
 *
 * ROM CALIBRATION (60E1D400.bin):
 *   0x0007A164  u8[2]  {0x01, 0x01}  per-rotor sensor IDs
 *   0x0007A178  u16    0x005E        ADC-output copy A
 *   0x0007A17A  u16    0x00C1        ADC-output copy B
 *   0x0007A1A4  f32    3.6875        reference float (0xFFFFA328)
 *   0x0007A1D0  f32    64.0          filter-state / filter-param float
 *   0x0000C4B0  f32    10.0          literal pool of THIS function (gain)
 *   0x0000C494  u16    0x00FF        max-limit byte (mov.w sign-extended)
 *
 * CALLING CONVENTION
 * ------------------
 * `void rx8_knock_related_init(void)` — no arguments, no return value, no
 * sub-calls (the emulator executes the real ROM bytes, all self-contained).
 * =============================================================================
 */
#include <stdint.h>
#include <string.h>
#include "rx8_samples.h"
#include "rx8_hw.h"

/* ---- RAM cells (addresses straight from the mov.l literals of the ROM) ---- */
#define RX8_KNOCK_FAULT_BYTE2_ADDR   0xFFFFA324u  /* u8 fault byte 2      */
#define RX8_KNOCK_REF_FLOAT_ADDR     0xFFFFA328u  /* f32 reference float  */
#define RX8_KNOCK_FILTER_STATE_ADDR  0xFFFFA32Cu  /* f32 filter state     */
#define RX8_KNOCK_THRESH_A_ADDR      0xFFFFA334u  /* f32 threshold A[0..1]*/
#define RX8_KNOCK_FILT_A_ADDR        0xFFFFA348u  /* f32 filter state A   */
#define RX8_KNOCK_THRESH_B_ADDR      0xFFFFA350u  /* f32 threshold B[0..1]*/
#define RX8_KNOCK_FILTER_GAIN_ADDR   0xFFFFA360u  /* f32 filter gain      */
#define RX8_KNOCK_FILTER_PARAM_ADDR  0xFFFFA364u  /* f32 filter parameter */
#define RX8_KNOCK_FILT_B_ADDR        0xFFFFA368u  /* f32 filter state B[0..1] */
#define RX8_KNOCK_ADC_COPY1_ADDR     0xFFFFA37Cu  /* u16 ADC-output copy B */
#define RX8_KNOCK_ADC_COPY2_ADDR     0xFFFFA37Eu  /* u16 ADC-output copy A */
#define RX8_KNOCK_MAX_BYTE_ADDR      0xFFFFA384u  /* u8 max limit byte    */
#define RX8_KNOCK_COUNTER_ADDR       0xFFFFA385u  /* u8 counter           */
#define RX8_KNOCK_FAULT_BYTE_ADDR    0xFFFFA386u  /* u8 fault byte        */
#define RX8_KNOCK_SENSOR_ID_ADDR     0xFFFFA389u  /* u8 sensor IDs (2)    */

/* ---- ROM calibration block (60E1D400.bin; oracle MAP_FIXED-maps the page) */
#define RX8_ROM_SENSOR_IDS  0x0007A164u  /* u8[2] per-rotor sensor IDs */
#define RX8_ROM_ADC_WORD_A  0x0007A178u  /* u16 0x005E                */
#define RX8_ROM_ADC_WORD_B  0x0007A17Au  /* u16 0x00C1                */
#define RX8_ROM_REF_FLOAT   0x0007A1A4u  /* f32 3.6875                */
#define RX8_ROM_FILT_PARAM  0x0007A1D0u  /* f32 64.0                  */

/* Literal pool of THIS function @0x0C4B0 (mova 0x0C4B0 + fmov.s @r0,fr5). */
#define RX8_KNOCK_GAIN_LITERAL  10.0f

/* Big-endian ROM reads: the SH-2E is big-endian, so multi-byte values are
 * assembled byte-wise (identical numeric value on the little-endian host
 * and on the emulator; the oracle backs these addresses with the real ROM
 * bytes via MAP_FIXED, same trick as rx8_get_maf_sensor_value.c). */
static uint8_t rx8_rom_u8(uint32_t addr)
{
    return *(const volatile uint8_t *)(uintptr_t)addr;
}

static uint16_t rx8_rom_u16(uint32_t addr)
{
    const uint8_t *p = (const uint8_t *)(uintptr_t)addr;
    return (uint16_t)((uint16_t)p[0] << 8) | p[1];
}

static float rx8_rom_f32(uint32_t addr)
{
    const uint8_t *p = (const uint8_t *)(uintptr_t)addr;
    uint32_t bits = ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16)
                  | ((uint32_t)p[2] << 8)  | (uint32_t)p[3];
    float v;
    memcpy(&v, &bits, sizeof v);
    return v;
}

/* 0xC3C8 — knock detection subsystem init (per-rotor setup). */
void rx8_knock_related_init(void)
{
    int i;

    /* 1. fixed u16 calibration words -> the two ADC-output copies. */
    RX8_IO16(RX8_KNOCK_ADC_COPY2_ADDR) = rx8_rom_u16(RX8_ROM_ADC_WORD_A); /* 0x005E */
    RX8_IO16(RX8_KNOCK_ADC_COPY1_ADDR) = rx8_rom_u16(RX8_ROM_ADC_WORD_B); /* 0x00C1 */

    /* 2. reference float (cal 3.6875) -> 0xFFFFA328. */
    *(volatile float *)(uintptr_t)RX8_KNOCK_REF_FLOAT_ADDR =
        rx8_rom_f32(RX8_ROM_REF_FLOAT);

    /* 3. filter gain = 10.0 (this function's own literal pool @0x0C4B0). */
    *(volatile float *)(uintptr_t)RX8_KNOCK_FILTER_GAIN_ADDR =
        RX8_KNOCK_GAIN_LITERAL;

    /* 4. secondary filter parameter = 64.0 (cal 0x7A1D0). */
    *(volatile float *)(uintptr_t)RX8_KNOCK_FILTER_PARAM_ADDR =
        rx8_rom_f32(RX8_ROM_FILT_PARAM);

    /* 5. max limit byte = 0xFF. */
    RX8_IO8(RX8_KNOCK_MAX_BYTE_ADDR) = 0xFFu;

    /* 6. counter + fault bytes cleared (0xFFFFA385, 0xFFFFA386, 0xFFFFA324;
     *    note: 0xFFFFA325 is NOT this function's — knockFunctionInit clears
     *    it as knock flag B). */
    RX8_IO8(RX8_KNOCK_COUNTER_ADDR)  = 0x00u;
    RX8_IO8(RX8_KNOCK_FAULT_BYTE_ADDR)  = 0x00u;
    RX8_IO8(RX8_KNOCK_FAULT_BYTE2_ADDR) = 0x00u;

    /* 7. filter state + per-rotor filter state A zeroed. */
    *(volatile float *)(uintptr_t)RX8_KNOCK_FILTER_STATE_ADDR = 0.0f;
    *(volatile float *)(uintptr_t)RX8_KNOCK_FILT_A_ADDR       = 0.0f;

    /* 8. per-rotor loop (2 rotors): thresholds, filter states, sensor IDs.
     *    ROM order per iteration: threshold B (10.0), filter state B (64.0),
     *    sensor-ID byte, threshold A (0.0). */
    for (i = 0; i < 2; i++) {
        *(volatile float *)(uintptr_t)(RX8_KNOCK_THRESH_B_ADDR + (uint32_t)i * 4u) =
            RX8_KNOCK_GAIN_LITERAL;
        *(volatile float *)(uintptr_t)(RX8_KNOCK_FILT_B_ADDR + (uint32_t)i * 4u) =
            rx8_rom_f32(RX8_ROM_FILT_PARAM);
        RX8_IO8(RX8_KNOCK_SENSOR_ID_ADDR + (uint32_t)i) =
            rx8_rom_u8(RX8_ROM_SENSOR_IDS + (uint32_t)i);
        *(volatile float *)(uintptr_t)(RX8_KNOCK_THRESH_A_ADDR + (uint32_t)i * 4u) =
            0.0f;
    }
}

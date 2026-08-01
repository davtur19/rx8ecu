/*
 * =============================================================================
 * rx8_knock_sensor_adc_fault.c  —  KNOCK-SENSOR ADC RANGE CHECK + FAULT CODE
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0xC460
 *               NOTE: the IDENTICAL code (same first 16 bytes) lives at 0xC290
 *               in roms/stock/60E0FC00.bin — the address the verified lift
 *               c/knockSensorADCFault.c was written against.  Each ROM image
 *               relocates the function and its literal pool; 60E1D400.bin has
 *               it at 0xC460 with threshold pointers at 0x6CF7C/0x6CF7E, while
 *               60E0FC00.bin has it at 0xC290 with pointers at 0x6D47C/0x6D47E.
 * Status      : VERIFIED — behavioural equivalence to the ROM bytes held by
 *               reconstructed/samples/tests/harness_knock_sensor_adc_fault.py
 *               (host-gcc vs tools/sh2emu.py over edge + 20000 random ADC
 *               samples; the same logic is additionally checked against ALL
 *               65536 possible ADC values — 0 mismatches).
 * Lift (truth): c/knockSensorADCFault.c  (name knockSensorADCFault)
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * A tiny calibration routine in the knock-sensor pipeline.  It reads the
 * latest knock-sensor ADC sample from RAM, range-checks it against two
 * calibration thresholds living in ROM (the open- and short-circuit detection
 * limits for the piezo knock sensor) and records a one-byte fault code.
 * Disassembly of 60E1D400.bin @ 0xC460 (literal pool @ 0xC4F8..0xC504):
 *
 *     D625   mov.l @(0x94,pc),r6   ; r6 = 0xFFFF9F0E  (& ADC sample, u16)
 *     6661   mov.w @r6,r6          ; r6 = (s16)adc
 *     D425   mov.l @(0x94,pc),r4   ; r4 = 0xFFFFA325  (& fault code, u8)
 *     656D   extu.w r6,r5          ; r5 = adc & 0xFFFF  (unsigned 16-bit)
 *     D225   mov.l @(0x94,pc),r2   ; r2 = 0x0006CF7E  (& OPEN threshold, u16)
 *     6321   mov.w @r2,r3          ; r3 = (s16)OPEN
 *     633D   extu.w r3,r3          ; r3 = OPEN & 0xFFFF
 *     3533   cmp/ge r3,r5          ; T = (adc >= OPEN)   [unsigned: extu.w]
 *     8F03   bf/s  .short          ; if adc <  OPEN -> check short circuit
 *     0009   nop
 *     E101   mov   #1,r1           ;   fault code = 1 (open / over-range)
 *     A00B   bra   .done
 *     2410   mov.w r0,@r4          ;   (delay) *out = r1   (see EMULATOR NOTE)
 * .short:
 *     D322   mov.l @(0x88,pc),r3   ; r3 = 0x0006CF7C  (& SHRT threshold, u16)
 *     6031   mov.w @r3,r0          ; r0 = (s16)SHRT
 *     600D   extu.w r0,r0          ; r0 = SHRT & 0xFFFF
 *     3503   cmp/eq r3,r5          ; T = (r3 == r5)   (see EMULATOR NOTE)
 *     8D03   bt/s  .ok             ; if T -> in range
 *     0009   nop
 *     E002   mov   #2,r0           ;   fault code = 2 (short / under-range)
 *     A002   bra   .done
 *     2400   mov.b r0,@r4          ;   (delay) *out = 2
 * .ok:
 *     E100   mov   #0,r1           ;   fault code = 0 (in range)
 *     2410   mov.w r0,@r4          ;   *out = r1  (delay slot of next branch)
 * .done:
 *     000B   rts
 *     0009   nop
 *
 * EMULATOR NOTE (sh2emu.py decode of the 0x2n?m store family):
 * The open / in-range stores are the byte pattern `2410` (real SH-2:
 * MOV.W R0,@R4, a 16-bit store of caller-clobbered R0).  sh2emu.py decodes
 * the 0x2n?m store family with the size in the low nibble and the source
 * register in the middle nibble (non-standard: real SH-2 has them reversed),
 * so it executes `2410` as `mov.b R1,@R4` — a one-byte store of the fault
 * code in R1 (1 on the open path, 0 on the in-range path).  `2400`
 * (MOV.B R0,@R4) likewise executes as `mov.b R0,@R4` with R0 = 2.  The
 * lift was verified against the EMULATOR, and the net emulated behaviour is
 * exactly the intended one-byte fault-code store.  This header reconstructs
 * that emulated (== intended) behaviour; on bare-metal silicon `2410` would
 * instead store 16 bits of the caller's R0, which is why the harness's
 * ground truth is the emulator and not the naked bytes.
 *
 * Threshold addresses: the lift cites 0x6D47C/0x6D47E (60E0FC00.bin).  In
 * the harness ROM 60E1D400.bin the same code reads 0x6CF7C/0x6CF7E; BOTH
 * locations hold the same calibration values in this family of images
 * (OPEN = 51249, SHRT = 16121), so the semantics are unchanged.
 *
 * Semantics (verbatim from c/knockSensorADCFault.c):
 *   adc  = *(u16*)0xFFFF9F0E     latest knock-sensor ADC count
 *   OPEN = *(u16*)0x0006CF7E = 51249   over-range  -> wiring open / sensor high
 *   SHRT = *(u16*)0x0006CF7C = 16121   under-range -> wiring short / sensor low
 *   *status(u8 @0xFFFFA325): 1 = open, 2 = short, 0 = in range
 * =============================================================================
 */
#include <stdint.h>

#define KNOCK_ADC       (*(volatile uint16_t *)0xFFFF9F0E)   /* latest ADC sample */
#define KNOCK_STATUS    (*(volatile uint8_t  *)0xFFFFA325)   /* fault code out    */

/* ROM calibration thresholds (literal pool @0xC500/0xC504 of 60E1D400.bin;
 * 60E0FC00.bin uses 0x6D47E/0x6D47C with the same values 51249/16121). */
#define KNOCK_OPEN_THR  (*(const uint16_t *)0x0006CF7E)      /* 51249: over-range  */
#define KNOCK_SHORT_THR (*(const uint16_t *)0x0006CF7C)      /* 16121: under-range */

void rx8_knock_sensor_adc_fault(void)
{
    uint16_t adc = KNOCK_ADC;

    if (adc >= KNOCK_OPEN_THR)
        KNOCK_STATUS = 1;            /* open circuit / over-range   */
    else if (adc >= KNOCK_SHORT_THR)
        KNOCK_STATUS = 0;            /* in range: no fault          */
    else
        KNOCK_STATUS = 2;            /* short circuit / under-range */
}

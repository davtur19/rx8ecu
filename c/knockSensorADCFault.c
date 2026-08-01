/*
 * knockSensorADCFault  —  RX-8 PCM @ ROM 0xC290  (equinox name, hand Ghidra RE by
 * equinox311).  Range-checks the knock-sensor ADC reading and records a fault code.
 *
 * No arguments: reads the latest knock-sensor ADC sample from RAM and writes a
 * one-byte status.  Two calibration thresholds live in ROM (open- and short-circuit
 * detection limits for the piezo knock sensor).
 *
 *   adc  = *(u16*)0xFFFF9F0E             latest knock-sensor ADC count
 *   OPEN = *(u16*)0x0006D47E   = 51249   over-range  -> wiring open / sensor high
 *   SHRT = *(u16*)0x0006D47C   = 16121   under-range -> wiring short / sensor low
 *   status -> *(u8*)0xFFFFA325  : 1 = open, 2 = short, 0 = in range
 *
 * Original SH-2E (values extu.w -> unsigned 16-bit; cmp/ge on positives == unsigned):
 *   if (adc >= OPEN)      status = 1;    // bf/s after cmp/ge OPEN  -> open
 *   else if (adc >= SHRT) status = 0;    // bt/s after cmp/ge SHRT  -> ok
 *   else                  status = 2;    //                         -> short
 *
 * Track A: verified behavior-equivalent to the emulated ROM (tools/sh2emu.py) across
 * ALL 65536 possible ADC values — 65536/65536 exact.  Test: c/tests/test_knockSensorADCFault.py
 * (First drafted by a Haiku sub-agent, then exact-lifted and verified here.)
 */
#include <stdint.h>

#define KNOCK_ADC       (*(volatile uint16_t *)0xFFFF9F0E)   /* latest ADC sample   */
#define KNOCK_STATUS    (*(volatile uint8_t  *)0xFFFFA325)   /* fault code out      */

/* ROM calibration thresholds (constant values shown are for image 60E0FC00) */
#define KNOCK_OPEN_THR  (*(const uint16_t *)0x0006D47E)      /* 51249: over-range   */
#define KNOCK_SHORT_THR (*(const uint16_t *)0x0006D47C)      /* 16121: under-range  */

void knockSensorADCFault(void)
{
    uint16_t adc = KNOCK_ADC;

    if (adc >= KNOCK_OPEN_THR)
        KNOCK_STATUS = 1;            /* open circuit / over-range   */
    else if (adc >= KNOCK_SHORT_THR)
        KNOCK_STATUS = 0;            /* in range: no fault          */
    else
        KNOCK_STATUS = 2;            /* short circuit / under-range */
}

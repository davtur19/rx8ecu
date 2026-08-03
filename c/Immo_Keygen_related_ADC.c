/*
 * Immo_Keygen_related_ADC  —  RX-8 PCM @ ROM 0x36AFC (60E1D400.bin)
 *
 * Rolling-code / key generator.  Mixes three ADC samples with the previous
 * mixer state (0xFFFFC288/0xFFFFC28A/0xFFFFC293) and a CRC-ish value from
 * adc_read() (0x3EDBC) to produce the next 32-bit rolling code at
 * 0xFFFFC278.  If the fresh code is 0, the stored pairing words
 * (0xFFFFC2DC | 0xFFFFC2E0) are used as a fallback.
 *
 * ADC inputs (verified): adc_a = *(u16*)0xFFFF9F1C, adc_b = *(u16*)0xFFFF9F1E,
 * adc_c = *(u16*)0xFFFF9F00 (base 0xFFFF9EE4 + 0x1C).  ret = adc_read(0xFFFF869C, 0).
 *
 * The two `cmp/ge` guards in the original (0x36B3E, 0x36B72) are compiled
 * from a conditional that is NEVER true: `cmp/ge` is a 32-bit SIGNED compare
 * and the left operand is the 32-bit complement of a 16-bit value (high word
 * 0xFFFF, i.e. negative) while the right operand is 0..0xFFFF (non-negative),
 * so T is always 0 and the `bt` (skip) is never taken — the guarded
 * increment blocks always execute.  They are modeled unconditionally here
 * (verified by differential test test_Immo_Keygen_related_ADC_36AFC.py).
 *
 * Return value: r0 at the end = ((ret>>16) & 0xFFFF) + (int16)*w288 + adc_b
 * (computed before *w288 is overwritten at 0x36B64).
 */
#include "eeprom_immo.h"

uint32_t Immo_Keygen_related_ADC(void)
{
    uint16_t adc_a = *(volatile uint16_t *)0xFFFF9F1C;   /* r13 */
    uint16_t adc_b = *(volatile uint16_t *)0xFFFF9F1E;   /* r14 */
    uint16_t adc_c = *(volatile uint16_t *)0xFFFF9F00;   /* r12 = 0xFFFF9EE4 + 0x1C */
    uint32_t ret   = adc_read(0xFFFF869C, 0);            /* r7 */
    volatile uint16_t *w288 = (volatile uint16_t *)0xFFFFC288;
    volatile uint16_t *w28A = (volatile uint16_t *)0xFFFFC28A;
    uint8_t *cnt = (uint8_t *)0xFFFFC293;
    uint32_t retval;

    /* 0x36B1E..0x36B30: *cnt = (ret & 0xFFFF) + adc_a + *cnt (byte) */
    *cnt = (uint8_t)((uint16_t)ret + adc_a + *cnt);

    /* 0x36B32..0x36B5A: cmp/ge (32-bit signed) on ~(u16)*w288 (always
     * negative) vs (ret>>16)&0xFFFF (always >= 0) is NEVER true, so the
     * increment block ALWAYS runs (verified against the emulator). */
    if ((uint16_t)*w28A == 0xFFFF)
        *cnt = (uint8_t)(*cnt + 1);
    *w28A = (uint16_t)(*w28A + 1);

    /* 0x36B5C..0x36B64: adc_b is added SIGN-extended (mov.w @(0x3A,r4),r14) */
    retval = ((ret >> 16) & 0xFFFF) + (int16_t)*w288 + (int16_t)adc_b;
    *w288 = (uint16_t)retval;

    /* 0x36B66..0x36B7C: same guard shape on ~(u16)*w28A — never true, the
     * increment ALWAYS runs. */
    *cnt = (uint8_t)(*cnt + 1);

    /* 0x36B7E..0x36B88: *w28A += ((ret&0x00FFFF00)>>8) + *w28A + adc_c */
    {
        uint32_t r7 = (ret & 0x00FFFF00) >> 8;
        r7 = r7 + (int16_t)*w28A + (int16_t)adc_c;
        *w28A = (uint16_t)r7;
    }

    /* 0x36B8A..0x36B98: *w288 = ((adc_c<<8) + (adc_a&0xFF)) ^ *w288 */
    {
        uint16_t v = (uint16_t)(((uint16_t)(adc_c & 0xFF) << 8) +
                                (adc_a & 0xFF));
        *w288 = (uint16_t)(v ^ (uint16_t)*w288);
    }

    /* 0x36B96..0x36BA2: *w28A = ~(((adc_a<<8) + (adc_b&0xFF)) ^ *w28A) */
    {
        uint16_t v = (uint16_t)(((uint16_t)(adc_a & 0xFF) << 8) +
                                (adc_b & 0xFF));
        *w28A = (uint16_t)~(v ^ (uint16_t)*w28A);
    }

    /* 0x36BA4..0x36BA8: *cnt = (uint8)(adc_b ^ *cnt) */
    *cnt = (uint8_t)(adc_b ^ (uint16_t)*cnt);

    /* 0x36BAC..0x36BBA: combine and publish; fallback when zero */
    {
        uint32_t combined = ((uint32_t)(uint16_t)*w288 << 16) |
                            (uint16_t)*w28A;
        IMMO_KEYGEN_ADC = combined;
        if (combined == 0) {
            IMMO_KEYGEN_ADC = *(volatile uint32_t *)0xFFFFC2DC |
                              *(volatile uint32_t *)0xFFFFC2E0;
        }
    }
    return retval;
}

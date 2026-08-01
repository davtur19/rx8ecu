/* math_min_max_49ED0.c
 *
 * ROM: 60E1D400  |  Address: 0x49ED0  |  Size: 34 bytes
 *
 * Flag-setter leaf: reads a 16-bit word at RAM 0xFFFFF76C, tests bit 0x100
 * and writes a 0/1 flag byte to both 0xFFFFCD48 and 0xFFFFCD49.
 * Returns the flag.
 *
 * SH-2E asm (simplified):
 *   0x49ED0: mov.w 0x49EF2,r6   ; r6 = 0xFFFFCD49 (output B; mov.w sign-extends)
 *   0x49ED2: mov.w 0x49EF4,r5   ; r5 = 0xFFFFCD48 (output A)
 *   0x49ED4: mov.w 0x49EF6,r3   ; r3 = 0xFFFFF76C (input word addr)
 *   0x49ED6: mov.w @r3,r0       ; r0 = word@0xFFFFF76C (sign-extended)
 *   0x49ED8: extu.w r0,r0       ; r0 &= 0xFFFF
 *   0x49EDA: mov.w 0x49EF8,r2   ; r2 = 0x00000100
 *   0x49EDC: and r2,r0          ; r0 &= 0x100
 *   0x49EDE: tst r0,r0          ; T = (r0 == 0)          = (bit clear)
 *   0x49EE0: movt r0            ; r0 = 1 if bit clear
 *   0x49EE2: xor #0x01,r0       ; r0 ^= 1  → 0 if clear, 1 if set
 *   0x49EE4: cmp/eq #0x01,r0    ; T = (r0 == 1)          = (bit set)
 *   0x49EE6: movt r0            ; r0 = 1 if bit set
 *   0x49EE8: cmp/eq #0x01,r0    ; T = (r0 == 1)          = (bit set)
 *   0x49EEA: movt r4            ; r4 = 1 if bit set
 *   0x49EEC: mov.b r4,@r5       ; byte@0xFFFFCD48 = r4
 *   0x49EEE: rts
 *   0x49EF0: mov.b r4,@r6       ; (delay) byte@0xFFFFCD49 = r4
 *
 * Semantics: v = (word@0xFFFFF76C & 0x100) ? 1 : 0;
 *            byte@0xFFFFCD48 = v; byte@0xFFFFCD49 = v; return v.
 *
 * Verified against ROM emulator: c/tests/test_math_min_max_49ED0.py
 * Host C companion:             c/tests/test_math_min_max_49ED0.c
 */
#include <stdint.h>

/* 0x49ED0 — set both flags from input word bit 0x100 */
uint32_t math_min_max_49ED0(void)
{
    uint32_t v = (*(volatile uint16_t *)0xFFFFF76C & 0x0100) ? 1 : 0;
    *(volatile uint8_t *)0xFFFFCD48 = (uint8_t)v;
    *(volatile uint8_t *)0xFFFFCD49 = (uint8_t)v;
    return v;
}

/* incrementCountToCap21_0x13DA2.c
 *
 * ROM: 60E0FC00 | Address: 0x13DA2 | Size: 0x62 (98) bytes per CSV range
 * 0x13DA2..0x13E04.  Code ends at `rts` @0x13DBE (delay nop @0x13DC0);
 * the region 0x13DC0..0x13E03 is the literal pool, and the next function
 * starts exactly at 0x13E04 (debounceThrottleRate prologue @0x13E04).
 * The CSV range is CORRECT — no correction needed.
 *
 * ENTRY VERIFICATION: 0x13DA2 matches the symbols CSV row
 * (0x013DA2..0x013E04).  Valid entry (opens with `mov #0x15,r1` + sts.l pr);
 * the preceding function knock_counter_reset_check (0x13D1C) ends `rts`
 * @0x13DB6 (delay @0x13D68?), so no fall-through.  Called via the dispatcher
 * engineControlCalculateTiming (0x141FC) dispatch table (callgraph:
 * 0x141FC -> 0x13DA2 FUN_00013da2, ref).  The CSV address IS the real entry.
 *
 * NAME DISCREPANCY (documented): the merged2 CSV row named this
 * `read_o2_sensor_voltage_trim` (ida-ai-xmap, flagged DUBIOUS).  This is
 * WRONG: the function performs NO O2/voltage/trim reads;
 * it reads a single global byte at 0xFFFFA758 and saturating-increments it
 * by 1 while it is below 21 (0x15).  Renamed here to what the code actually
 * does: `incrementCountToCap21`.  (The 0xFFFFA758 counter is the same ramp
 * count consumed by the neighbouring coolant-based timing derate lift
 * getCoolantBasedTimingDerate /0x13E30, which reads A758 into a f32.)
 *
 * SEMANTICS (line-for-line, see disasm):
 *   lim = 0x15 (21)
 *   if u8@0xFFFFA758 < lim:          // bf/s when r3(=byte) >= lim
 *       u8@0xFFFFA758 = addSaturate8Bit_0x2478(u8@0xFFFFA758, 1)   // r0
 *   else: no write
 * where addSaturate8Bit(r0x(r4), r5=1) = r0 = ((r4&0xFF)+(r5&0xFF)) ;
 *   r0 = (r0 >= 0xFF) ? 0xFF : r0   (saturating +1).  Because the guard
 *   requires value < 0x15 (<< 0xFE), the +1 never actually saturates; it is
 *   a plain increment.  r0 on the non-increment path retains its entry value.
 *
 * RAM r/w: reads 0xFFFFA758; writes 0xFFFFA758 (when the guard passes).
 * Sub-calls: addSaturate8Bit @0x2478 (inlined in the lift; see note).
 * Stack: r15 frame only (pr saved).
 * VERIFIED vs tools/sh2emu.py (60E0FC000.bin) in c/tests/test_... — 0
 * mismatches over 5 seeds x 100000 iterations (byte-exact post RAM + r0).
 */
#include <stdint.h>

#define RAM_CNT (*(volatile uint8_t *)0xFFFFA758)  /* ramp counter (A758)   */
#define CAP     0x15                                /* 0x10F578 cap = 21     */

/* 0x2478 addSaturate8Bit(r, 1): ((r & 0xFF) + 1), saturate at 0xFF */
static uint32_t add_saturate(uint32_t a, uint32_t b)
{
    uint32_t r = (a & 0xFF) + (b & 0xFF);
    return (r >= 0xFF) ? 0xFF : r;
}

void incrementCountToCap21_0x13DA2(void)
{
    if (RAM_CNT < CAP)
        RAM_CNT = (uint8_t)add_saturate(RAM_CNT, 1);
}
/* getKnockSensorFaultedStatus_0x136D6.c
 *
 * ROM: 60E0FC00 | Address: 0x136D6 | Size: 0x28 (40) bytes per CSV range
 * 0x136D6..0x136FE.  Code ends at the `rts` @0x136FA (delay nop @0x136FC);
 * the input-status literal halfwords live in the shared pool @0x13730/0x13732
 * and the output address literal @0x1375C.  The next function
 * getKnockControlActive (0x136FE) starts at the CSV end.
 *
 * BANK NOTE (discrepancy, documented): the task brief said "bank 60E1D400",
 * but the byte-identical knock-sensor-fault writer (reads 0xFFFFCC30/0xFFFFCC32,
 * writes 0xFFFFA739) is NOT in 60E1D400.  In 60E1D400 address 0x136D6 falls
 * inside the jump-table of calc_evap_purge_duty (0x13652..0x136AE).  It IS the
 * genuine function in 60E0FC00 and 60E0FB00 (the 0x136D6..0x137A0 region is
 * byte-identical in both), where it is called by the dispatcher
 * engineControlCalculateTiming @0x141FC, function-pointer slot @0x14410
 * phase 1, between getKnockControlAllowed?? (0x13686, slot 0x1440C) and
 * getKnockControlActive (0x136FE, slot 0x14414).  The slot @0x14410 literal
 * (0x000136D6) is the ONLY 32-bit reference to 0x136D6 in the binary.  The CSVs
 * with the row for this function are symbols_60E0FC00.csv (and the merged2 /
 * FB00 variants), so those are updated here, not the 60E1D400 CSVs.
 *
 * Entry  : 0x136D6 — matches the symbols CSV row (0x0136D6,0x0136FE,
 *           getKnockSensorFaultedStatus?).  Valid entry (opens straight with a
 *           mov.l literal load; the preceding function getKnockControlAllowed??
 *           ends with `rts` @0x136D2 + nop @0x136D4, so there is no fall-through
 *           into us; no incoming branches into the middle).  The CSV address IS
 *           the real entry point.
 *
 * Semantics (instruction-for-instruction, see disasm):
 *   if u8@0xFFFFCC30 == 1 && u8@0xFFFFCC32 == 1: u8@0xFFFFA739 = 1
 *   else:                                          u8@0xFFFFA739 = 0
 * i.e. the knock-sensor-faulted status latch is the AND of two per-sensor
 * status bytes.  This is a flag WRITER (shape identical to calc_rotor_sync_
 * base_A_0x13A5E which &&s CDA4/CD32 -> writes A749); the CSV name
 * getKnockStatusSensorFaultedStatus is kept (matches the repo / dispatcher
 * compute-family naming, cf. getKnockControlAllowed, getKnockControlActive).
 *
 * Range  : 0x136D6 .. 0x136FE
 * Literal pool (verified against roms/stock/60E0FC00.bin):
 *   0x13730 0xCC30   (mov.w -> u8 status input @0xFFFFCC30)
 *   0x13732 0xCC32   (mov.w -> u8 status input @0xFFFFCC32)
 *   0x1375C 0xFFFFA739 (mov.l -> u8 output latched flag @0xFFFFA739)
 * RAM r/w: reads 0xFFFFCC30, 0xFFFFCC32; writes 0xFFFFA739.
 * ROM read: only the literal pool above.  Sub-calls: none.  Stack: none.
 * VERIFIED against the SH-2 emulator (tools/sh2emu.py, 60E0FC00.bin) in
 * c/tests/test_getKnockSensorFaultedStatus_0x136D6.py — 0 mismatches over
 * 5 seeds x 100000 iterations (byte-exact full post-call RAM overlay + r0).
 */
#include <stdint.h>

/* ---- RAM globals (mov.w sign-extends to 0xFFFFxxxx; byte reads) ---- */
#define IN_A_CC30 (*(volatile uint8_t *)0xFFFFCC30)  /* u8 knock sensor A status */
#define IN_B_CC32 (*(volatile uint8_t *)0xFFFFCC32)  /* u8 knock sensor B status */
#define OUT_A739  (*(volatile uint8_t *)0xFFFFA739)  /* u8 knock-sensor-fault flag */

void getKnockSensorFaultedStatus_0x136D6(void)
{
    uint8_t out = 0;

    /* 0x136DA..0x136DE: read u8@CC30 (extu.b) ; cmp/eq #1 ; bf/s 0x136F6 */
    if ((IN_A_CC30 & 0xFFu) == 1) {
        /* 0x136E6..0x136EA: read u8@CC32, cmp/eq #1 ; bf/s 0x136F6 */
        if ((IN_B_CC32 & 0xFFu) == 1)
            out = 1;                 /* 0x136F0..0x136F4: A739 = 1 */
    }

    OUT_A739 = out;                  /* 0x136F6..0x136F8: A739 = 0 (or bra delay) */
}
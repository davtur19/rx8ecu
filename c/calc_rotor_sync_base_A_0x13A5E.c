/* calc_rotor_sync_base_A_0x13A5E.c
 *
 * ROM: 60E1D400 | Address: 0x13A5E | Size: 0x28 (40) bytes per CSV range
 * 0x13A5E..0x13A86.  Code ends at the `rts` @0x13A82 (delay nop @0x13A84);
 * the input-status literal words live in the shared pool @0x13AB8/0x13ABA
 * and the output address literal @0x13AE4.  The next function
 * getKnockControlActive (0x13A86) starts at the CSV end.
 *
 * Entry  : 0x13A5E — matches the symbols CSV row (0x013A5E,0x013A86,
 *           calc_rotor_sync_base_A).  Valid entry (opens straight with a
 *           mov.l literal load; the preceding function calc_ignition_advance
 *           _modifier ends with `rts` @0x13A5A + nop @0x13A5C, so there is no
 *           fall-through into us; there are no incoming branches into the
 *           middle).  Called via the function-pointer dispatch slot @0x1479
 *           of the engineControlCalculateTiming dispatcher (0x14584) —
 *           dispatch phase 1, between getKnockControlAllowed (0x14794) and
 *           getKnockControlActive (0x1479C).  The ROM literal @0x14798 is the
 *           ONLY 32-bit reference to 0x13A5E in the binary (no other callers).
 *           The CSV address IS the real entry point.
 *
 * NAME DISCREPANCY (documented, decision): the dispatcher comment names this
 * slot getKnockSensorFaultedStatus, but BOTH symbols CSV sources (ida-ai and
 * ghidra-hand-xmap) name it calc_rotor_sync_base_A.  The real semantics (see
 * below) are a flag WRITER, not a fault-status getter: it latches the rotor
 * sync base gate u8@0xFFFFA749 = (u8@0xFFFFCDA4 == 1 && u8@0xFFFFCDA6 == 1),
 * feeding getKnockControlActive (0x13A86) which ANDs A749 with the
 * ignition-advance-modifier flag A748 into the knock-control-active flag A740.
 * This matches calc_rotor_sync_base_A (and the existing committed DRAFT lift
 * of the same name), so getKnockSensorFaultedStatus is NOT chosen.  DECISION:
 * keep calc_rotor_sync_base_A (semantically correct; unchanged in both CSVs).
 *
 * Range  : 0x13A5E .. 0x13A86
 *
 * Literal pool (values verified against roms/stock/60E1D400.bin):
 *   0x13AE4 0xFFFFA749    (mov.l -> u8 output flag @0xFFFFA749)
 *   0x13AB8 0xCDA4        (mov.w -> u8 status input @0xFFFFCDA4)
 *   0x13ABA 0xCDA6        (mov.w -> u8 status input @0xFFFFCDA6)
 *
 * Semantics (instruction-for-instruction, see disasm):
 *   if u8@0xFFFFCDA4 == 1 && u8@0xFFFFCDA6 == 1: u8@0xFFFFA749 = 1
 *   else:                                          u8@0xFFFFA749 = 0
 * r0 after return = the masked byte of the last-read status that decided the
 * branch: 1 when both gates match (the CDA6 mask), else the masked CDA6 byte
 * when the second check fails, else the masked CDA4 byte when the first fails.
 * No stack frame, no sub-calls; only the u8@A749 store is a RAM side effect.
 * VERIFIED against the SH-2 emulator (tools/sh2emu.py) in
 * c/tests/test_calc_rotor_sync_base_A_0x13A5E.py — 0 mismatches over 5 seeds
 * x 100000 iterations (byte-exact full post-call RAM overlay + r0).
 */
#include <stdint.h>

/* ---- RAM globals (mov.w sign-extends to 0xFFFFxxxx; byte reads) ---- */
#define IN_A_CDA4 (*(volatile uint8_t *)0xFFFFCDA4)  /* u8 status input A */
#define IN_B_CDA6 (*(volatile uint8_t *)0xFFFFCDA6)  /* u8 status input B */
#define OUT_A749  (*(volatile uint8_t *)0xFFFFA749)  /* u8 rotor-sync-base flag */

void calc_rotor_sync_base_A_0x13A5E(void)
{
    uint8_t out = 0;

    /* 0x13A62..0x13A68: read u8@CDA4 (extu.b) ; cmp/eq #1 ; bf/s 0x13A7E.
     * Both status bytes must be exactly 1 for the output to be set. */
    if ((IN_A_CDA4 & 0xFFu) == 1) {
        /* 0x13A6E..0x13A76: read u8@CDA6, cmp/eq #1 ; bf/s 0x13A7E */
        if ((IN_B_CDA6 & 0xFFu) == 1)
            out = 1;                 /* 0x13A78..0x13A7C: A749 = 1 */
    }

    OUT_A749 = out;                  /* 0x13A7E..0x13A80: A749 = 0 (or bra delay) */
}
/* getKnockControlActive_0x13A86.c
 *
 * ROM: 60E1D400 | Address: 0x13A86 | Size: 0x28 (40) bytes per CSV range
 * 0x13A86..0x13AAE.  Code ends at the `rts` @0x13AAA (delay nop @0x13AAC);
 * the literal pool sits @0x13AAC..0x13AB8 (mov.l/mov.w PC-relative loads).
 * The next function limitKnockRetardMax_CondRPM (0x13AE4) starts at the CSV
 * end; the bytes between 0x13AB0 and 0x13AE4 are the shared literal pool.
 *
 * Entry  : 0x13A86 — matches the symbols merged-CSV row (0x013A86,0x013AAE,
 *           getKnockControlActive).  Valid entry (no incoming branches into
 *           the middle; the preceding function calc_rotor_sync_base_A ends
 *           with `rts` @0x13A82 so there is no fall-through into us).
 *           Called via the function-pointer dispatch slot @0x1479C of the
 *           engineControlCalculateTiming dispatcher (0x14584) — dispatch
 *           phase 1, immediately before updateKnockMaxRAM (0x147A0).  The
 *           CSV address IS the real entry point.
 *
 * NAME DISCREPANCY (documented, decision): the ida-ai symbols row named this
 * entry calc_rotor_sync_base_B; the merged CSV row (ghidra-hand-xmap) names
 * it getKnockControlActive.  The real semantics — A740 = A748 & A749, where
 * A748 is the ignition-advance-modifier flag (0x13A0E) and A749 the rotor
 * sync flag (0x13A5E), both of which gate the knock control — match
 * getKnockControlActive.  DECISION: use getKnockControlActive (matches the
 * task + merged CSV + the committed DRAFT lift); the ida-ai row is renamed
 * to it in both CSVs.
 *
 * Range  : 0x13A86 .. 0x13AAE
 *
 * Literal pool (values verified against roms/stock/60E1D400.bin):
 *   0x13AB4 0xA740        (mov.w -> u8 output flag @0xFFFFA740)
 *   0x13AAC 0xFFFFA748    (mov.l -> u8 gate input @0xFFFFA748)
 *   0x13AB0 0xFFFFA749    (mov.l -> u8 gate input @0xFFFFA749)
 *
 * Semantics (instruction-for-instruction, see disasm):
 *   if u8@0xFFFFA748 == 1 && u8@0xFFFFA749 == 1: u8@0xFFFFA740 = 1
 *   else:                                       u8@0xFFFFA740 = 0
 * No stack frame, no sub-calls; only the u8@A740 store is a RAM side effect.
 * VERIFIED against the SH-2 emulator (tools/sh2emu.py) in
 * c/tests/test_getKnockControlActive_0x13A86.py — 0 mismatches over 5 seeds x
 * 100000 iterations (byte-exact full post-call RAM overlay + r0).
 */
#include <stdint.h>

/* ---- RAM globals (mov.w sign-extends to 0xFFFFxxxx) ---- */
#define GATE_A748 (*(volatile uint8_t *)0xFFFFA748)  /* u8 gate input (0x13A0E flag) */
#define GATE_A749 (*(volatile uint8_t *)0xFFFFA749)  /* u8 gate input (rotor sync)   */
#define OUT_A740  (*(volatile uint8_t *)0xFFFFA740)  /* u8 knock-control-active flag */

void getKnockControlActive_0x13A86(void)
{
    uint8_t out = 0;

    /* 0x13A8A..0x13A9C: both gates must be exactly 1 (extu.b then cmp/eq #1) */
    if ((GATE_A748 & 0xFFu) == 1 && (GATE_A749 & 0xFFu) == 1)
        out = 1;                   /* 0x13AA0..0x13AA4: A740 = 1 */

    OUT_A740 = out;                /* 0x13AA6..0x13AA8: A740 = 0 (or bra delay) */
}
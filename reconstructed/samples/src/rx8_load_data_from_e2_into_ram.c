/*
 * =============================================================================
 * rx8_load_data_from_e2_into_ram.c  —  BOOT STUB: EEPROM SHADOW-RAM LOADER
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x36BD6
 * Status      : VERIFIED — behavioural equivalence to the ROM bytes held by
 *               reconstructed/samples/tests/harness_load_data_from_e2_into_ram.py
 *               (host-gcc vs tools/sh2emu.py over random + edge vectors,
 *               real ROM bytes @0x36BD6; return value + full 256-byte EEPROM
 *               shadow + complement + scratch window compared; 0 mismatches).
 * Lift (truth): c/loadDatafromE2intoRAM.c  (loadDatafromE2intoRAM @ 0x36BD6)
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * Boot-time loader: copies the first 32 bytes of the EEPROM into the shadow
 * RAM (primary 0xFFFFC2FE + complement 0xFFFFC3FE) by calling the generic
 * E2IntoRAM(0, 32) helper @0x38F58.  Disassembly of 60E1D400.bin @ 0x36BD6:
 *
 *     E520   mov  #0x20,r5        ; r5 = 32 (byte count)
 *     D30F   mov.l @(0x0F,pc),r3  ; r3 = 0x00038F58  (E2IntoRAM)
 *     4F22   sts.l pr,@-r15
 *     430B   jsr  @r3
 *     E400   mov  #0x00,r4        ; r4 = 0 (e2_addr)  [delay slot]
 *     4F26   lds.l @r15+,pr
 *     000B   rts
 *     0009   nop                  [delay slot]
 *
 * So the whole function is a leaf wrapper:
 *     loadDatafromE2intoRAM(void)  =>  E2IntoRAM(0, 32)
 * and its only observable side effects are E2IntoRAM's: the 16 flash-backup
 * half-words are split into (high, low) byte pairs written to the primary and
 * complement shadows, plus the half-window scratch words at 0xFFFFC502/0xFFFFC504.
 *
 * LIFT DISCREPANCY (documented)
 * -----------------------------
 * The lift's listing says `mov.l @(0x1E,pc),r3` — the real byte at 0x36BD8 is
 * D30F, i.e. displacement 0x0F.  The target is the SAME longword pool entry,
 * 0x00038F58, so the lift's C (`E2IntoRAM(0, 32)`) is unaffected and correct.
 *
 * CALLING CONVENTION / RETURN VALUE
 * ---------------------------------
 * The wrapper takes no arguments and returns nothing (void); r0 is a
 * side-channel holding E2IntoRAM's return (1 = both SPI-retry polls reported
 * busy -> early abort, 0 = EEPROM copy performed).  The harness compares that
 * r0 too, but the reconstructed signature stays void to match the ROM.
 *
 * HARDWARE ABSTRACTION (verification notes)
 * -----------------------------------------
 * E2IntoRAM @0x38F58 polls the SPI-retry hook (0xC0A8) twice; with the default
 * emulator state (GPIO data-in 0xFFFFF738 bit 0x0800 clear) it returns 1 and
 * the function aborts WITHOUT touching the shadow.  With bit 0x0800 set the
 * copy path runs.  The real flash reader (0xBFCA) bit-bangs the on-chip SPI
 * and busy-waits on peripheral status bits of 0xFFFFF024 (TX-buffer-ready /
 * RX-buffer-ready) that sh2emu does not model, so it can never terminate under
 * the emulator.  Following the repo-established pattern
 * (c/tests/test_getFromE2.py), the harness stubs 0xBFCA (flash reader) and
 * optionally 0xC0A8 (retry) in the RAM overlay, then executes the REAL wrapper
 * bytes and the REAL E2IntoRAM control flow + copy loop.  The host oracle
 * mirrors the same stubs through its porting layer.
 * =============================================================================
 */
#include <stdint.h>

#include "rx8_samples.h"

/* 0x38F58 — E2IntoRAM(e2_addr, length), lift c/E2IntoRAM.c.  Supplied by the
 * porting layer of the host oracle (tests/oracle_load_data_from_e2_into_ram.c)
 * when this sample is compiled for equivalence testing. */
uint8_t E2IntoRAM(uint16_t e2_addr, uint8_t length);

void rx8_load_data_from_e2_into_ram(void)
{
    E2IntoRAM(0, 32);
}

/*
 * =============================================================================
 * rx8_baro_sensor_value.c  —  BARO "SENSOR VALUE" @ 0xD144 — PERIPHERAL-WORD
 *                              WRITER (byte-swapped u16 -> HCAN mailbox regs)
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0xD144  (body 0xD144..0xD162; `rts` at 0xD160 with the
 *               `mov.w r3,@r4` store in its delay slot at 0xD162.  The next
 *               function starts at 0xD164.)
 *
 * Status      : VERIFIED — behavioural equivalence to the ROM bytes held by
 *               reconstructed/samples/tests/harness_baro_sensor_value.py
 *               (host-gcc vs tools/sh2emu.py over edge + 20000 random vectors,
 *               fixed seed 0x60E1D400; every side-effected MMIO cell compared
 *               byte-for-byte; 0 mismatches).
 *
 * Lift (truth): c/baro_sensor_value.c  (getBaroSensorVal @ 0xD144)
 *               and docs/functions/getBaroSensorVal.md.
 *
 * MAJOR DISCREPANCY vs THE LIFT — READ THIS FIRST
 * -----------------------------------------------
 * The lift describes an ADC->fixed-point->float barometric-pressure pipeline:
 * it reads the baro ADC at RAM16 0xFFFF9F18, calls fixedPointScaling @0x2510,
 * converts via fixedPointToFloat_16bit_MULT_OFF_SIG @0x24C0, stores a float at
 * 0xFFFFA3DC and returns a range status 0/1/2 against the u16 thresholds at
 * 0x6D46C/0x6D46E.  NONE OF THAT EXISTS at 0xD144 in 60E1D400.bin:
 *
 *   1. There is no `jsr`/`bsr`, no FPU instruction and no ADC read anywhere in
 *      0xD144..0xD162.  The body is a 20-byte leaf: `extu.b r4,r4; tst r4,r4;
 *      bf/s; extu.w r5,r6; mov.w 0xE40A/0xE60A; mov.l 0x0000FF00; extu.b;
 *      shll8; and; shlr8; or; rts / mov.w r3,@r4` — i.e. byte-swap a u16 and
 *      store it to an on-chip peripheral register.
 *   2. The lift's RAM cells (0xFFFF9F18, 0xFFFFA3DC, 0xFFFFC5D8) and cal
 *      tables (f32 @0x7978C/0x79790, u16 @0x6D46C/0x6D46E) are never touched
 *      by these bytes.  The two addresses actually written are
 *      0xFFFFE40A (bank == 0) and 0xFFFFE60A (bank != 0) — on-chip MMIO in
 *      the HCAN mailbox data-word region (the 16-bit literals 0xE40A/0xE60A
 *      sign-extend because bit 15 is set; docs/functions/txCAN_EventBased.md
 *      documents the same 0xE406/0xE40A mailbox-flag pattern, and the block
 *      immediately below this function, 0xD198..0xD1AA, is the verified
 *      HCAN register-address helper getHCANRegisterAddress).
 *   3. The lift's described function IS the ROM at 0xD144..0xD1E0 of the
 *      sibling bin roms/stock/60E0FC00.bin (its literal pool at 0xD1BC-0xD1DE
 *      holds exactly 0x00002510, 0x38A00000, 0x000024C0, 0x0007978C,
 *      0x00079790, 0xFFFFA3DC, 0xFFFFA3E0, 0x0006D46C, 0x0006D46E), and the
 *      symbol table marks THAT rom's 0xD144..0xD1E0 as `baro_sensor_value`
 *      (ghidra-hand).  The IDA-AI label on 60E1D400 (symbols_60E1D400_ida.csv)
 *      inherited the name for a different body.
 *
 * WHAT THIS FUNCTION ACTUALLY DOES
 * --------------------------------
 * A register-argument leaf that publishes a 16-bit word to one of two HCAN
 * mailbox data registers.  It is big-endian-CPU -> little-endian-peripheral
 * conversion: the SH-2E byte-swaps the word (low byte moved to the high
 * position, high byte to the low position) before the big-endian `mov.w`
 * store, so the MMIO register ends up holding the LITTLE-ENDIAN image of the
 * value — exactly the store shape an HCAN message-data word needs.
 *
 * Disassembly of 60E1D400.bin @0xD144:
 *
 *     extu.b  r4,r4          ; r4 = (u8)bank
 *     tst     r4,r4          ; T = (bank == 0)
 *     bf/s    0xD152         ; if (bank != 0) goto 0xD152
 *       extu.w r5,r6         ;   (delay) r6 = (u16)value
 *     mov.w   @0xD182,r4     ; r4 = 0xE40A  -> sign-extended 0xFFFFE40A
 *     bra     0xD154
 *       nop
 * 0xD152:
 *     mov.w   @0xD184,r4     ; r4 = 0xE60A  -> sign-extended 0xFFFFE60A
 * 0xD154:
 *     mov.l   @0xD194,r2     ; r2 = 0x0000FF00
 *     extu.b  r6,r3          ; r3 = value & 0xFF
 *     shll8   r3             ; r3 = (value & 0xFF) << 8
 *     and     r6,r2          ; r2 = value & 0xFF00
 *     shlr8   r2             ; r2 = (value >> 8) & 0xFF
 *     or      r2,r3          ; r3 = swap16(value)
 *     rts
 *       mov.w r3,@r4         ;   (delay) write u16 (big-endian) to the reg
 *
 * CALLING CONVENTION
 * ------------------
 * `void rx8_baro_sensor_value(uint8_t bank, uint16_t value)` — the ROM reads
 * r4 (bank selector, only the low byte is used: `extu.b`) and r5 (the u16
 * value, only the low half is used: `extu.w`).  There is no ABI return value
 * (r0 is untouched; cpu.call() returns whatever was in r0, which the harness
 * ignores).  The function is driven through the standard SH2.call() entry and
 * verified by comparing the two written MMIO cells byte-for-byte.
 *
 * MMIO CELLS (on-chip peripheral registers; SH-2E big-endian byte store)
 * ---------------------------------------------------------------------
 *   OUT u16 0xFFFFE40A  HCAN mailbox-A data word   (written when bank == 0)
 *   OUT u16 0xFFFFE60A  HCAN mailbox-B data word   (written when bank != 0)
 *   The unselected cell is NEVER touched, so its pre-state must survive — the
 *   harness seeds distinguishable pre-states into both cells and checks that
 *   the unselected one is left byte-identical.
 *
 * CALIBRATION / CONSTANTS (ROM literal pool, not cal tables)
 * ---------------------------------------------------------
 *   u16 @0xD182 = 0xE40A  -> target register 0xFFFFE40A (sign-extended)
 *   u16 @0xD184 = 0xE60A  -> target register 0xFFFFE60A (sign-extended)
 *   u32 @0xD194 = 0x0000FF00 (mask for bits 8..15 of the value)
 *   There are no RAM/EEPROM calibration reads in this function.
 *
 * INTERNAL CALLEES: none — no jsr/bsr anywhere in the body; the emulator
 * harness runs the exact bytes with no call graph and the host build is
 * completely self-contained.
 * =============================================================================
 */
#include <stdint.h>

#include "rx8_hw.h"

/* ---- MMIO cells (addresses are the sign-extended 16-bit mov.w literals) --- */
#define RX8_BARO_MBOX_A_ADDR  0xFFFFE40Au   /* u16 mailbox-A data word        */
#define RX8_BARO_MBOX_B_ADDR  0xFFFFE60Au   /* u16 mailbox-B data word        */

/* ---- big-endian u16 store: mirrors the ROM's `mov.w r3,@r4` on the SH-2E
 * (byte-exact on the little-endian host oracle too). ----------------------- */
static void rx8_be16_store(uint32_t addr, uint16_t v)
{
    RX8_IO8(addr)      = (uint8_t)(v >> 8);
    RX8_IO8(addr + 1u) = (uint8_t)(v & 0xFFu);
}

/* 0xD144 — byte-swapped peripheral word writer (bank-selectable). */
void rx8_baro_sensor_value(uint8_t bank, uint16_t value)
{
    /* r3 = (value & 0xFF) << 8 | (value >> 8) & 0xFF  == swap16(value) */
    uint16_t swapped = (uint16_t)(((value & 0xFFu) << 8) |
                                  ((value >> 8) & 0xFFu));

    /* bf/s at 0xD148: bank != 0 selects the B register, bank == 0 the A one.
     * The tst compares the extu.b'd r4, so only the low byte matters. */
    if (bank == 0u)
        rx8_be16_store(RX8_BARO_MBOX_A_ADDR, swapped);
    else
        rx8_be16_store(RX8_BARO_MBOX_B_ADDR, swapped);
}

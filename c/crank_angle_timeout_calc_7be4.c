/* ROM: 60E1D400 | Address: 0x7BE4 | Size: 40 bytes
 * Human-verified lift (was: auto-generated DRAFT by tools/gen_c_lift_v3.py).
 *
 * Crank-angle timeout calculator: saturating-increments an 8-bit event
 * counter (unless already 0xFF), then copies one ROM calibration byte to a
 * RAM timeout cell and returns the RAM cell address (as the ROM leaves it
 * in r0).
 *
 * Hardware binding is injected by the caller — no absolute addresses in
 * this unit (host-testable):
 *   counter  - r4 in the ROM: u8 event counter (read-modify-write)
 *   rom_cal  - ROM byte 0x0006CF58 (timeout calibration value)
 *   ram_out  - RAM byte 0xFFFF9FC8 (timeout output cell)
 *
 * Semantics (instruction-for-instruction from the disasm):
 *   if (*counter < 0xFF) (*counter)++;   // cmp/ge #0xFF skips the inc
 *   *ram_out = *rom_cal;                 // mov.b @rom -> @ram
 *   return ram_out;                      // r0 = 0xFFFF9FC8 on the ECU
 *
 * NOTE: bytes after the `rts` at 0x7BFC (0x7C00..0x7C0E: writes to
 * 0xFFFF9FC6 / reads 0xFFFF9F96) are NOT part of this function — they are
 * the entry points of the following ROM functions. The old DRAFT wrongly
 * carried them as unreachable tail code; they are dropped here.
 */
#include <stdint.h>

uint32_t crank_angle_timeout_calc_7be4(uint8_t *counter, const uint8_t *rom_cal,
                                       uint8_t *ram_out)
{
    /* 0x007BE4..0x007BF4: saturating counter increment (skipped at 0xFF) */
    if (*counter < 0xFFu) {
        (*counter)++;
    }
    /* 0x007BF6..0x007BFE (delay): copy ROM cal byte to RAM timeout cell */
    *ram_out = *rom_cal;
    /* r0 carries the RAM cell address on return */
    return (uint32_t)(uintptr_t)ram_out;
}

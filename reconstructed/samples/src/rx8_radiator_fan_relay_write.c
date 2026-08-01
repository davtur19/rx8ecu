/*
 * =============================================================================
 * rx8_radiator_fan_relay_write.c  —  RADIATOR FAN RELAY OUTPUT (ACTIVE-LOW)
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x259C0
 * Status      : VERIFIED — behavioural equivalence to the ROM bytes held by
 *               reconstructed/samples/tests/harness_radiator_fan_relay_write.py
 *               (host-gcc vs tools/sh2emu.py over edge + random vectors,
 *               comparing the side-effected relay byte; 0 mismatches).
 * Lift (truth): c/radiator_fan_relay_write.c  (also verified there by
 *               c/tests/test_radiator_fan_relay.py, exhaustive 0..255 +
 *               3000 random inputs)
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * A tiny active-low relay driver: it reflects bit 0 of the fan-status byte
 * RAM[0xFFFF9ECD] into the radiator-fan relay byte RAM[0xFFFFB5AB].  The relay
 * is energised (byte = 1) when the status bit is CLEAR, and dropped (byte = 0)
 * when the bit is SET.  The status byte carries many other bits (only bit 0 is
 * tested), so the write target is a full 8-bit byte, not a masked port.
 *
 *   RAM[0xFFFFB5AB] = (RAM[0xFFFF9ECD] & 1) ? 0 : 1
 *
 * Disassembly of 60E1D400.bin @ 0x259C0 (20 words, 40 bytes):
 *
 *     9571   mov.w  0x25AA6,r5      ; r5 = 0xFFFFB5AB (relay byte; 0xB5AB sign-ext)
 *     E401   mov    #0x01,r4        ; r4 = 1
 *     D33D   mov.l  0x25ABC,r3      ; r3 = 0xFFFF9ECD (fan status byte)
 *     6030   mov.b  @r3,r0          ; r0 = sign-extended status byte
 *     600C   extu.b r0,r0           ; r0 = status & 0xFF
 *     2048   tst    r4,r0           ; T = ((r0 & 1) == 0)
 *     8F02   bf/s   0x259D4         ; bit SET  -> 0x259D4 (r0 = 0)
 *     0009   nop                    ;   (delay slot)
 *     A001   bra    0x259D6         ; bit CLEAR -> 0x259D6 with r0 = 1
 *     6043   mov    r4,r0           ;   (delay slot) r0 = 1
 *     259D4: E000   mov    #0x00,r0 ; r0 = 0 (bit SET path)
 *     259D6: 8801   cmp/eq #0x01,r0 ; T = (r0 == 1)
 *     8F02   bf/s   0x259E0         ; r0 != 1 -> write 0, return
 *     0009   nop                    ;   (delay slot)
 *     A002   bra    0x259E4         ; r0 == 1 -> write 1, return
 *     2540   mov.b  r4,@r5          ;   (delay slot) relay = 1
 *     259E0: E200   mov    #0x00,r2 ; r2 = 0
 *     2520   mov.b  r2,@r5          ; relay = 0
 *     000B   rts
 *     0009   nop                    ;   (delay slot)
 *
 * The two-step register dance (bit test, then a second compare against 1) is a
 * compiler artifact of the boolean expression `(status & 1) ? 0 : 1`; the
 * observable behaviour is a single byte write, so the C below collapses it.
 * The status byte is read exactly once (single `mov.b @r3,r0`), which the
 * volatile read below preserves.
 *
 * RAM SIDE EFFECT: writes one byte @0xFFFFB5AB — the harness compares that
 * byte (the emulator's RAM overlay) against the host's mmap-backed page.
 * =============================================================================
 */
#include <stdint.h>
#include <stddef.h>

#include "rx8_samples.h"

/* Fan-status and relay addresses are not (yet) documented in include/rx8_hw.h;
 * they come from the verified lift c/radiator_fan_relay_write.c. */
#define RX8_FAN_STATUS_ADDR  0xFFFF9ECDu   /* fan status byte, bit 0 = request  */
#define RX8_FAN_RELAY_ADDR   0xFFFFB5ABu   /* radiator fan relay byte (active-low) */

/* 0x259C0 — drive the radiator fan relay from bit 0 of the status byte.
 * Active-low: relay energised (1) when the status bit is clear. */
void rx8_radiator_fan_relay_write(void)
{
    uint8_t status = *(volatile uint8_t *)(uintptr_t)RX8_FAN_STATUS_ADDR;
    *(volatile uint8_t *)(uintptr_t)RX8_FAN_RELAY_ADDR = (status & 1u) ? 0u : 1u;
}

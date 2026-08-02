/*
 * =============================================================================
 * rx8_set_immo_light.c  —  IMMOBILIZER WARNING LAMP DRIVER (setImmoLight)
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x263C8
 * Status      : VERIFIED — behavioural equivalence to the ROM bytes held by
 *               reconstructed/samples/tests/harness_set_immo_light.py
 *               (host-gcc vs tools/sh2emu.py over edge + N random initial-RAM
 *               state vectors, comparing the 16-bit lamp register side effect;
 *               0 mismatches).
 * Lift (truth): c/setImmoLight.c  (setImmoLight @ 0x263C8)
 *
 * WHY THIS FUNCTION EXISTS / STANDALONE VERSION
 * ---------------------------------------------
 * Drives the immobilizer warning lamp.  `(on & 0xFF) == 1` lights it,
 * anything else extinguishes it.  The lamp is bit pair 0x40|0x20 of the
 * 16-bit status word RX8_STATUS_WORD @0xFFFFF754, written through the
 * reg16SetClear helper (0x4BBC), each access wrapped in a save/restore of the
 * SR interrupt-mask nibble (0x2054 / 0x2064).
 *
 * The immo siblings rx8_immo_bad_state_set.c (0x365B8) and
 * rx8_immo_good_state_set.c (0x36544) both INLINE this routine's net RAM
 * effect (word &= ~0x0060 for setImmoLight(0), word |= 0x60 for
 * setImmoLight(1)) so their samples stay self-contained — their harnesses
 * already execute the REAL 0x263C8 bytes inside the emulator.  This sample is
 * the standalone reconstruction of 0x263C8 itself, driving the lamp through
 * the same harness rig over both paths (on == 1 and on != 1) and the full
 * 32-bit `on` argument space, not just the two constants the siblings use.
 *
 * CALLING CONVENTION
 * ------------------
 * void setImmoLight(uint8_t on): normal ABI entry, the on/off argument comes
 * in r4 (the ROM reads only its low byte: `extu.b r4,r0`); no meaningful
 * return value (r0 is left holding the last saveSRMaskParam SR snapshot).
 * Driven via cpu.call(0x263C8, r4=on) and verified by comparing the
 * side-effected lamp register (same rig as the immo siblings).
 *
 * FULL LISTING (verified disassembly of 60E1D400.bin @ 0x263C8-0x26448)
 * ----------------------------------------------------------------------
 *    0x263C8  2FE6  mov.l  r14,@-r15          ; prologue: push r14,r13,r12,r11,r10,pr
 *    0x263CA  604C  extu.b r4,r0              ; r0 = on & 0xFF
 *    0x263CC  2FD6  mov.l  r13,@-r15
 *    0x263CE  8801  cmp/eq #0x01,r0           ; T = ((on & 0xFF) == 1)
 *    0x263D0  DE21  mov.l  0x26458,r14        ; r14 = 0x4BBC (reg16SetClear)
 *    0x263D2  2FC6  mov.l  r12,@-r15
 *    0x263D4  2FB6  mov.l  r11,@-r15
 *    0x263D6  2FA6  mov.l  r10,@-r15
 *    0x263D8  4F22  sts.l  pr,@-r15
 *    0x263DA  7FE8  add    #-0x18,r15         ; 24-byte local frame
 *    0x263DC  DA1C  mov.l  0x26450,r10        ; r10 = 0x2054 (saveSRMaskParam)
 *    0x263DE  DB1D  mov.l  0x26454,r11        ; r11 = 0x2064 (loadStatusRegister_ADDR)
 *    0x263E0  9C33  mov.w  0x2644A,r12        ; r12 = 0x00E0 (SR mask)
 *    0x263E2  9D33  mov.w  0x2644C,r13        ; r13 = 0xF754 SIGN-EXT -> 0xFFFFF754
 *    0x263E4  8F14  bf/s   0x26410            ; T==0 -> OFF path
 *    0x263E6  0009  nop
 *    ---- ON  path (on & 0xFF == 1): set 0x40 then set 0x20 ----
 *    0x263E8  65C3  mov    r12,r5             ; saveSRMaskParam(r15+0x14, 0xE0)
 *    0x263EA  64F3  mov    r15,r4
 *    0x263EC  4A0B  jsr    @r10
 *    0x263EE  7414  add    #0x14,r4           ;   (delay)
 *    0x263F0  E601  mov    #0x01,r6           ; reg16SetClear(0xFFFFF754, 0x40, 1)
 *    0x263F2  E540  mov    #0x40,r5
 *    0x263F4  4E0B  jsr    @r14
 *    0x263F6  64D3  mov    r13,r4             ;   (delay) r4 = lamp addr
 *    0x263F8  4B0B  jsr    @r11               ; loadStatusRegister_ADDR(@(0x14,r15))
 *    0x263FA  54F5  mov.l  @(0x14,r15),r4     ;   (delay) r4 = saved SR
 *    0x263FC  65C3  mov    r12,r5             ; saveSRMaskParam(r15+0x10, 0xE0)
 *    0x263FE  64F3  mov    r15,r4
 *    0x26400  4A0B  jsr    @r10
 *    0x26402  7410  add    #0x10,r4           ;   (delay)
 *    0x26404  E601  mov    #0x01,r6           ; reg16SetClear(0xFFFFF754, 0x20, 1)
 *    0x26406  E520  mov    #0x20,r5
 *    0x26408  4E0B  jsr    @r14
 *    0x2640A  64D3  mov    r13,r4             ;   (delay)
 *    0x2640C  A013  bra    0x26436            ; common trailing restore
 *    0x2640E  54F4  mov.l  @(0x10,r15),r4     ;   (delay) r4 = saved SR #2
 *    ---- OFF path (on & 0xFF != 1): clear 0x20 then clear 0x40 ----
 *    0x26410  65C3  mov    r12,r5             ; saveSRMaskParam(r15+0x0C, 0xE0)
 *    0x26412  64F3  mov    r15,r4
 *    0x26414  4A0B  jsr    @r10
 *    0x26416  740C  add    #0x0C,r4           ;   (delay)
 *    0x26418  E600  mov    #0x00,r6           ; reg16SetClear(0xFFFFF754, 0x20, 0)
 *    0x2641A  E520  mov    #0x20,r5
 *    0x2641C  4E0B  jsr    @r14
 *    0x2641E  64D3  mov    r13,r4             ;   (delay)
 *    0x26420  4B0B  jsr    @r11               ; loadStatusRegister_ADDR(@(0x0C,r15))
 *    0x26422  54F3  mov.l  @(0xC,r15),r4      ;   (delay)
 *    0x26424  65C3  mov    r12,r5             ; saveSRMaskParam(r15+0x08, 0xE0)
 *    0x26426  64F3  mov    r15,r4
 *    0x26428  4A0B  jsr    @r10
 *    0x2642A  7408  add    #0x08,r4           ;   (delay)
 *    0x2642C  E600  mov    #0x00,r6           ; reg16SetClear(0xFFFFF754, 0x40, 0)
 *    0x2642E  E540  mov    #0x40,r5
 *    0x26430  4E0B  jsr    @r14
 *    0x26432  64D3  mov    r13,r4             ;   (delay)
 *    0x26434  54F2  mov.l  @(0x8,r15),r4      ; r4 = saved SR #2 (fall-through)
 *    ---- common trailing SR restore + epilogue ----
 *    0x26436  4B0B  jsr    @r11               ; loadStatusRegister_ADDR(r4)
 *    0x26438  0009  nop                       ;   (delay)
 *    0x2643A  7F18  add    #0x18,r15
 *    0x2643C  4F26  lds.l  @r15+,pr
 *    0x2643E  6AF6  mov.l  @r15+,r10
 *    0x26440  6BF6  mov.l  @r15+,r11
 *    0x26442  6CF6  mov.l  @r15+,r12
 *    0x26444  6DF6  mov.l  @r15+,r13
 *    0x26446  000B  rts
 *    0x26448  6EF6  mov.l  @r15+,r14          ;   (delay)
 *    ... literal pool @ 0x2644A: 00E0 | F754 | 00002054 00002064 00004BBC
 *
 * RAM CELL (the only side effect the harness compares)
 * ----------------------------------------------------
 *   0xFFFFF754 u16  RX8_STATUS_WORD  (rx8_hw.h).  RMW twice by the 0x4BBC
 *   helper (16-bit mov.w read, mask, 16-bit mov.w write back):
 *     on == 1 : word |= 0x40; then word |= 0x20   ->  word |= 0x0060
 *     on != 1 : word &= ~0x20; then word &= ~0x40  ->  word &= ~0x0060
 *
 * CALLEES FOLDED IN (real ROM bytes always executed by the emulator)
 * ------------------------------------------------------------------
 *   0x4BBC  reg16SetClear(addr, mask, set): w = *(u16*)addr;
 *           w = set ? (w|mask) : (w & ~mask); *(u16*)addr = w.
 *   0x2054  saveSRMaskParam(slot, mask): slot = SR & 0xF0;
 *           SR = (mask >= (SR & 0xF0)) ? mask : (SR & 0xF0)  (cmp/hs).
 *   0x2064  loadStatusRegister_ADDR(v): SR = v (ldc Rn,SR in the rts slot).
 *   The SR save/restore pairs (two per path) are CPU-internal: the saved
 *   slots live in the transient 24-byte frame at sp+0x14/0x10/0xC/0x8 and are
 *   fully restored by the epilogue, so they leave NO observable RAM trace and
 *   are folded here (exactly like the immo siblings fold the whole call).
 *
 * DISCREPANCIES vs c/setImmoLight.c  (lift conventions, corrected here)
 * ---------------------------------------------------------------------
 *   1. The lift's IMMO_LAMP_REG macro spells 0xF754; the ROM loads the lamp
 *      address with `mov.w @(disp,pc),r13` which SIGN-EXTENDS the 16-bit
 *      literal 0xF754 to the CPU's effective address 0xFFFFF754 (same
 *      correction documented in rx8_immo_good_state_set.c / -bad_state_set.c).
 *   2. The lift names the helpers from c/eeprom_immo.h; the real ROM
 *      subroutine addresses are reg16SetClear @0x4BBC, saveSRMaskParam
 *      @0x2054, loadStatusRegister_ADDR @0x2064 — all verified byte-for-byte
 *      from the disassembly above.  Net effect identical to the lift.
 *   3. The lift and this sample agree on the (on & 0xFF) == 1 gate; the ROM's
 *      `cmp/eq #0x01` compares the zero-extended byte, so ANY r4 value with
 *      low byte 0x01 lights the lamp (e.g. 0x101 / 0x80000001) — the harness
 *      pins those cases.
 * =============================================================================
 */
#include <stdint.h>

#include "rx8_hw.h"

/* ---- 0x263C8  setImmoLight(uint8_t on): immobilizer warning lamp --------- */
void rx8_set_immo_light(uint8_t on)
{
    if ((on & 0xFFu) == 1u) {
        /* ON  path (0x263E8-0x2640A): reg16SetClear(0xFFFFF754, 0x40, 1)
         * then reg16SetClear(0xFFFFF754, 0x20, 1), each SR-mask-wrapped. */
        RX8_IO16(0xFFFFF754) |= 0x40u;
        RX8_IO16(0xFFFFF754) |= 0x20u;
    } else {
        /* OFF path (0x26410-0x26434): reg16SetClear(0xFFFFF754, 0x20, 0)
         * then reg16SetClear(0xFFFFF754, 0x40, 0), same SR wrapping. */
        RX8_IO16(0xFFFFF754) &= ~0x20u;
        RX8_IO16(0xFFFFF754) &= ~0x40u;
    }
    /* trailing loadStatusRegister_ADDR (0x26436) + full stack restore:
     * CPU-internal SR and transient frame — no observable RAM effect. */
}

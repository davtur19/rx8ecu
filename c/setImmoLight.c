/*
 * setImmoLight  —  RX-8 PCM @ ROM 0x263C8 (60E1D400.bin)
 *
 * Drives the immobilizer warning lamp.  `on` != 0 lights it, `on` == 0
 * extinguishes it.  The lamp is a 16-bit GPIO register (0xF754) whose bits
 * 0x40 and 0x20 are set/cleared through the 0x4BBC helper; each GPIO write
 * is wrapped in a save/restore of the SR interrupt mask (0x2054/0x2064).
 *
 * Original listing (verified):
 *   0x263D0  r14 = 0x4BBC (reg16SetClear)
 *   0x263DC  r10 = 0x2054 (saveSRMaskParam)   r11 = 0x2064 (loadStatusRegister_ADDR)
 *   0x263E0  r12 = 0xE0                        r13 = 0xF754 (lamp reg)
 *   0x263E4  bf/s 0x26410 (r0 = on & 0xFF; cmp/eq #0x01)
 *   ON  (state == 1):  saveSRMaskParam(&s1,0xE0); reg16SetClear(0xF754,0x40,1);
 *                      loadStatusRegister_ADDR(s1); saveSRMaskParam(&s2,0xE0);
 *                      reg16SetClear(0xF754,0x20,1); loadStatusRegister_ADDR(s2);
 *                      loadStatusRegister_ADDR(s3); saveSRMaskParam(&s4,0xE0);
 *                      reg16SetClear(0xF754,0x40,0); loadStatusRegister_ADDR(s4);
 *   0x26436  jsr @r11 (common 0x2064 restore of the slot saved at 0x2640E/0x26434)
 *
 * (The saved SR slots at sp+0x14/0x10/0xC/0x8 are reused; the final 0x2064
 * call restores the last one.)
 */
#include "eeprom_immo.h"

void setImmoLight(uint8_t on)
{
    uint32_t slot;

    if ((on & 0xFF) == 1) {
        saveSRMaskParam(&slot, 0xE0);
        reg16SetClear(&IMMO_LAMP_REG, 0x40, 1);
        loadStatusRegister_ADDR(slot);
        saveSRMaskParam(&slot, 0xE0);
        reg16SetClear(&IMMO_LAMP_REG, 0x20, 1);
        loadStatusRegister_ADDR(slot);
    } else {
        saveSRMaskParam(&slot, 0xE0);
        reg16SetClear(&IMMO_LAMP_REG, 0x20, 0);
        loadStatusRegister_ADDR(slot);
        saveSRMaskParam(&slot, 0xE0);
        reg16SetClear(&IMMO_LAMP_REG, 0x40, 0);
        loadStatusRegister_ADDR(slot);
    }
    loadStatusRegister_ADDR(slot);   /* 0x26436: the trailing 0x2064 */
}

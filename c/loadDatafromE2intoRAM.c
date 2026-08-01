/*
 * loadDatafromE2intoRAM  —  RX-8 PCM @ ROM 0x36BD6 (60E1D400.bin)
 *
 * Boot stub: loads the first 32 bytes of the EEPROM into the shadow RAM
 * (primary + complement) by calling E2IntoRAM(0, 32).  The flash backup
 * image supplies the (value, ~value) pairs.
 *
 * Original listing (verified):
 *   0x36BD6  mov #0x20,r5
 *   0x36BD8  mov.l @(0x1E,pc),r3  ; 0x00038F58 (E2IntoRAM)
 *   0x36BDA  sts.l pr,@-r15
 *   0x36BDC  jsr @r3 ; mov #0x00,r4
 *   0x36BE0  lds.l @r15+,pr
 *   0x36BE2  rts
 */
#include "eeprom_immo.h"

void loadDatafromE2intoRAM(void)
{
    E2IntoRAM(0, 32);
}

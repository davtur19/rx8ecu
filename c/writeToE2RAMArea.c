/*
 * writeToE2RAMArea  —  RX-8 PCM @ ROM 0x39124 (60E1D400.bin)
 *
 * Writes `length` bytes from `src` into the EEPROM shadow RAM, storing each
 * byte together with its complement at the parallel complement shadow.
 * The pair (data, ~data) is the integrity scheme used for all EEPROM data:
 * readers accept a byte only when byte == ~complement.
 *
 * Original SH-2E listing (verified):
 *   0x39124  mov.l  r14,@-r15      ; r14 = len
 *   0x39128  mov.l  @(0x60,pc),r3  ; 0x3920 getSR
 *   0x3912E  mov    r4,r13         ; r13 = index
 *   0x39132  mov    r5,r12         ; r12 = src
 *   0x3913A  mov.l  @(0x62,pc),r7  ; 0xFFFFC3FE complement base
 *   0x3913C  mov.l  @(0x5E,pc),r6  ; 0xFFFFC2FE primary base
 *   0x39140  mov.l  r0,@r15        ; save SR
 *   loop (while len != 0):
 *   0x39142  extu.w r13,r0         ; idx = index & 0xFFFF
 *   0x39144  mov.b  @r12+,r2       ; b = *src++
 *   0x39146  add    #0xFF,r14      ; len--
 *   0x39148  mov    r0,r5 ; add r6,r5 ; mov.b r2,@r5   ; primary[idx] = b
 *   0x3914E  add    #0x01,r13      ; index++
 *   0x39150  mov.b  @r5,r3 ; not r3                  ; ~primary[idx]
 *   0x39154  mov.b  r3,@r0,r7      ; complement[idx] = ~primary[idx]
 *   0x39156  extu.b r14,r2 ; tst r2 ; bf/s loop
 *   0x3915E  mov.l  @(0x56,pc),r3  ; 0x3934 setSR
 *   0x39160  jsr    @r3 ; mov.l @r15,r4               ; setSR(saved)
 *   0x3916C  rts
 *
 * Note the read-back: complement[idx] is the complement of the value READ
 * BACK from primary[idx], not of the source byte (they are equal unless a
 * memory write is filtered by the hardware).
 */
#include "eeprom_immo.h"

void writeToE2RAMArea(uint16_t index, const uint8_t *src, uint8_t length)
{
    uint32_t saved_sr = getSR(0x10);          /* disable interrupts        */
    uint8_t *primary   = (uint8_t *)E2_PRIMARY_BASE;
    uint8_t *complement = (uint8_t *)E2_COMPLEMENT_BASE;

    while (length != 0) {
        uint16_t idx = index;                 /* extu.w r13,r0             */
        uint8_t  b   = *src++;                /* mov.b @r12+,r2            */
        length--;                             /* add #0xFF,r14             */
        index++;                              /* add #0x01,r13             */
        primary[idx]   = b;                   /* mov.b r2,@r5              */
        complement[idx] = (uint8_t)~primary[idx]; /* read-back, not, store */
    }

    setSR(saved_sr);
}

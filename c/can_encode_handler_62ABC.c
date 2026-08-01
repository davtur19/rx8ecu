/* can_encode_handler_62ABC.c
 *
 * ROM: 60E1D400  |  Address: 0x62ABC  |  Size: 104 bytes (to 0x62B24)
 *
 * CAN-encode dispatch leaf (common tail of dtc_handler_61550's mode-3
 * path): looks up the DTC's mode-dispatch byte in the per-DTC table at
 * 0xFFFF8D7C (indexed by (dtc & 0xFFFF) * 2) and, for selected mode values,
 * folds r5 into the two run-sum cells via obd_service_handler_648B4:
 *
 *   mode = byte@(0xFFFF8D7C + (dtc & 0xFFFF) * 2)
 *   vl   = r5 & 0xFF
 *
 *   mode == 0x00          -> call obd_service_handler_648B4(r5)
 *   mode == 0x10          -> call 0x648B4(r5)  iff vl == 0x20 or vl == 0x11
 *   mode == 0x11          -> call 0x648B4(r5)  iff vl == 0x20
 *   mode == 0x20 (or any other value)          -> no call
 *
 * (The mode table is really a 16-bit-per-DTC table — the sibling 0x62B24
 * reads the high byte at 0xFFFF8D7D + dtc*2.  Tests restrict dtc so the
 * table read stays clear of the 0xFFFF8E98/0xFFFF8E9A run-sum cells.)
 *
 * SH-2E asm (r14 = r5, r12 = r5&0xFF; 0x62BA0 = 0x648B4):
 *   0x62ABC: mov.l  r14,@-r15
 *   0x62ABE: extu.w r4,r4
 *   0x62AC0: mov.l  0x62B9C,r0            ; r0 = 0xFFFF8D7C (mode table)
 *   0x62AC2: mov    r5,r14
 *   0x62AC4: mov.l  r13,@-r15
 *   0x62AC6: shll   r4                    ; r4 = dtc*2
 *   0x62AC8: mov.l  r12,@-r15
 *   0x62ACA: sts.l  pr,@-r15
 *   0x62ACC: mov.b  @(r0,r4),r4           ; mode = byte@(table + dtc*2)
 *   0x62ACE: mov.l  0x62BA0,r13           ; r13 = 0x648B4 (run-sum leaf)
 *   0x62AD0: extu.b r4,r0
 *   0x62AD2: cmp/eq #0,r0                 ; mode == 0
 *   0x62AD4: bt/s   0x62AEE               ;   -> call
 *   0x62AD6: extu.b r14,r12               ; (delay) r12 = r5 & 0xFF
 *   0x62AD8: cmp/eq #0x10,r0
 *   0x62ADA: bt/s   0x62AF6               ;   -> test vl
 *   0x62ADC: nop
 *   0x62ADE: cmp/eq #0x11,r0
 *   0x62AE0: bt/s   0x62B0E               ;   -> test vl == 0x20
 *   0x62AE2: nop
 *   0x62AE4: cmp/eq #0x20,r0
 *   0x62AE6: bt/s   0x62B1A               ;   -> no call
 *   0x62AE8: nop
 *   0x62AEA: bra    0x62B1A               ;   default: no call
 *   0x62AEC: nop
 *   0x62AEE: jsr    @r13                  ; mode 0
 *   0x62AF0: mov    r14,r4                ; (delay) r4 = r5
 *   0x62AF2: bra    0x62B1A
 *   0x62AF4: nop
 *   0x62AF6: mov    r12,r0                ; mode 0x10: vl == 0x20 || 0x11
 *   0x62AF8: cmp/eq #0x20,r0
 *   0x62AFA: bt/s   0x62B06
 *   0x62AFC: nop
 *   0x62AFE: mov    r12,r0
 *   0x62B00: cmp/eq #0x11,r0
 *   0x62B02: bf/s   0x62B1A
 *   0x62B04: nop
 *   0x62B06: jsr    @r13                  ; -> call 0x648B4(r5)
 *   0x62B08: mov    r14,r4
 *   0x62B0A: bra    0x62B1A
 *   0x62B0C: nop
 *   0x62B0E: mov    r12,r0                ; mode 0x11: vl == 0x20 only
 *   0x62B10: cmp/eq #0x20,r0
 *   0x62B12: bf/s   0x62B1A
 *   0x62B14: nop
 *   0x62B16: jsr    @r13
 *   0x62B18: mov    r14,r4
 *   0x62B1A: lds.l  @r15+,pr
 *   0x62B1C: mov.l  @r15+,r12
 *   0x62B1E: mov.l  @r15+,r13
 *   0x62B20: rts
 *   0x62B22: mov.l  @r15+,r14
 *
 * Called with (dtc, 0x20) from dtc_handler_61550's common tail when the
 * DTC currently addressed (word @0xFFFFD700) equals dtc.
 *
 * Verified against ROM emulator: c/tests/test_can_encode_handler_62ABC.py
 * (emulator executes the real 0x648B4/0x2420 bodies, so the test covers the
 * full call chain).  No host-C companion: the lift calls the external leaf
 * obd_service_handler_648B4 (same convention as c/dtc_handler_61550.c).
 */
#include <stdint.h>

#define MODE_TABLE  0xFFFF8D7Cu   /* per-DTC mode dispatch byte table      */

extern void obd_service_handler_648B4(uint32_t r4);   /* ROM 0x648B4       */

/* 0x62ABC — dispatch the DTC's mode byte to the run-sum update leaf */
void can_encode_handler_62ABC(uint32_t dtc, uint32_t r5)
{
    uint8_t mode = *(volatile uint8_t *)(MODE_TABLE + ((dtc & 0xFFFFu) << 1));
    uint8_t vl   = (uint8_t)(r5 & 0xFFu);
    int call = 0;

    switch (mode) {
    case 0x00u:
        call = 1;
        break;
    case 0x10u:
        call = (vl == 0x20u || vl == 0x11u);
        break;
    case 0x11u:
        call = (vl == 0x20u);
        break;
    case 0x20u:                          /* explicit no-op path             */
    default:
        call = 0;
        break;
    }

    if (call)
        obd_service_handler_648B4(r5);
}

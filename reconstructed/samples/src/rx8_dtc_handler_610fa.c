/*
 * =============================================================================
 * rx8_dtc_handler_610fa.c  —  OBD DTC SERVICE-CHAIN DISPATCHER
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x610FA
 * Status      : VERIFIED — behavioural equivalence to the ROM bytes held by
 *               reconstructed/samples/tests/harness_dtc_handler_610fa.py
 *               (host-gcc vs tools/sh2emu.py over 20000 random + edge vectors;
 *               RAM side-effects compared bit-exactly, 0 mismatches).
 * Lift (truth): c/dtc_handler_610FA.c  (dtc_handler_610FA @ 0x610FA; the lift
 *               had not yet been promoted to verified_addrs.txt — this sample
 *               re-verified it and found NO discrepancies).
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * The dispatch entry point of the OBD Mode-03-style DTC reporting pipeline.
 * It reads the "current DTC index" register 0xFFFF8928, uses it to index the
 * DTC handler byte-code opcode table at 0xFFFF87DE (16 bytes per entry, the
 * opcode is the FIRST byte of the entry), and acts on the opcode:
 *
 *   opcode == 0x50  ("pending/completed" entry)  or
 *   opcode == 0x00  (empty entry)
 *       -> can_encode_handler_62FAC(8), obd_service_handler_64258(),
 *          then tail-call obd_service_handler_63312()
 *
 *   any other opcode -> return immediately with NO side effects (the DTC entry
 *   is not in a serviceable state).
 *
 * Disassembly of 60E1D400.bin @ 0x610FA:
 *
 *     4F22   sts.l        pr,@-r15            ; prologue
 *     D335   mov.l        0x611D4,r3          ; r3 = 0xFFFF8928 (current index)
 *     6431   mov.w        @r3,r4              ; r4 = s16(word@0xFFFF8928)
 *     D035   mov.l        0x611D8,r0          ; r0 = 0xFFFF87DE (opcode table)
 *     644D   extu.w       r4,r4               ; idx &= 0xFFFF
 *     4408   shll2        r4                  ; idx *= 4
 *     4408   shll2        r4                  ; idx *= 4   (== *16)
 *     044C   mov.b        @(r0,r4),r4         ; r4 = s8(opcode@table + idx*16)
 *     644C   extu.b       r4,r4               ; op = r4 & 0xFF
 *     6043   mov          r4,r0
 *     8850   cmp/eq       #0x50,r0            ; T = (op == 0x50)
 *     8D03   bt/s         0x6111A             ;   -> service chain
 *     0009   nop
 *     2448   tst          r4,r4               ; T = (op == 0x00)
 *     8F09   bf/s         0x6112C             ; op != 0 -> return
 *     0009   nop
 *     6111A: D330  mov.l  0x611DC,r3          ; r3 = 0x62FAC
 *     6111C: 430B  jsr    @r3                 ; can_encode_handler_62FAC()
 *     6111E: E408  mov    #0x08,r4            ;   (delay) r4 = mode 8
 *     61120: D22F  mov.l  0x611E0,r2          ; r2 = 0x64258
 *     61122: 420B  jsr    @r2                 ; obd_service_handler_64258()
 *     61124: 0009  nop
 *     61126: D32A  mov.l  0x611D0,r3          ; r3 = 0x63312
 *     61128: 432B  jmp    @r3                 ; tail call: obd_service_handler_63312()
 *     6112A: 4F26  lds.l  @r15+,pr            ;   (delay) epilogue
 *     6112C: 4F26  lds.l  @r15+,pr            ; (return path) epilogue
 *     6112E: 000B  rts
 *     61130: 0009  nop
 *
 * The heavier per-entry logic lives in dtc_handler_61D2A, which calls back
 * into this function for every processed DTC.
 *
 * CALLING CONVENTION
 * ------------------
 * Plain ABI leaf entry, NO register arguments and NO meaningful return value
 * (r0 ends up echoing whatever the tail-called 63312 left in it — 0xFF on the
 * service path, the opcode value on the early-return path).  The lift models
 * it as `void`.
 *
 * CALLEES
 * -------
 * The three helpers are real ROM functions executed BY THE EMULATOR from ROM
 * bytes, and are declared here (not inlined) exactly like the lift:
 *   - can_encode_handler_62FAC(8)  @0x62FAC  — DTC-can-encode dispatcher;
 *   - obd_service_handler_64258()  @0x64258  — active-row counter update
 *     (own verified sample: samples/src/rx8_obd_dtc_row_update_64258.c);
 *   - obd_service_handler_63312()  @0x63312  — pending-flag clear, tail-called
 *     via `jmp @Rn` (own verified sample:
 *     samples/src/rx8_obd_service_handler_63312.c).
 * The host oracle (tests/oracle_dtc_handler_610fa.c) supplies side-effect
 * models for these three callees so the whole chain can be linked and run on
 * the host; the harness restricts the 0xFFFF87D0 dispatch byte to values != 2
 * so can_encode takes its simple flag!=2 path (the flag==2 branch calls a
 * deeper encoder chain that is out of scope here and documented in the oracle).
 *
 * RAM SIDE EFFECTS (whole chain, flag@0xFFFF87D0 != 2)
 * ---------------------------------------------------
 *   long@0xFFFF87BC = 0xFFFF0000         (0x2430(0xFFFF); can_encode)
 *   word@0xFFFF87D0 = 0x00FF             (0x2420(0);     obd_service_63312)
 *   row p = 0xFFFF8930 + word@0xFFFF8D74 * 0x34:
 *     p[0x32] = (p[0x32] + p[0x07] + 0xFF) & 0xFF   ; p[0x07] = 1
 *     p[0x32] = (p[0x32] + p[0x08] + 0xF9) & 0xFF   ; p[0x08] = 7
 * =============================================================================
 */
#include <stdint.h>

#include "rx8_samples.h"

#define DTC_CUR_INDEX  0xFFFF8928u   /* word: DTC index being serviced    */
#define DTC_OPCODES    0xFFFF87DEu   /* byte: handler byte-code opcodes   */
#define DTC_STRIDE     16u

/* called helpers (ROM addresses; emulator executes the REAL bytes, the host
 * oracle provides the side-effect models — see the header notes above) */
extern void can_encode_handler_62FAC(uint8_t mode);
extern void obd_service_handler_64258(void);
extern void obd_service_handler_63312(void);   /* tail-called (jmp @Rn)    */

/* 0x610FA — dispatch: service the DTC entry whose opcode is 0x50/0x00, else
 * return with no side effects. */
void rx8_dtc_handler_610fa(void)
{
    uint16_t idx = *(volatile uint16_t *)(uintptr_t)DTC_CUR_INDEX;
    uint8_t  op  = *(volatile uint8_t *)(uintptr_t)(DTC_OPCODES
                                                    + (uint32_t)idx * DTC_STRIDE);

    if (op == 0x50u || op == 0x00u) {
        can_encode_handler_62FAC(0x08u);
        obd_service_handler_64258();
        obd_service_handler_63312();           /* tail call (jmp @Rn)      */
    }
}

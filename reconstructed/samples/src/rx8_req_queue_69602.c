/*
 * =============================================================================
 * rx8_req_queue_69602.c  —  REQUEST-QUEUE STORE / CLEAR (BYTE-FLAG + u32 SLOTS)
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Addresses   : req_queue_store @0x69602, req_queue_clear @0x69694
 * Status      : VERIFIED — behavioural equivalence to the ROM bytes held by
 *               reconstructed/samples/tests/harness_req_queue_69602.py
 *               (host-gcc vs tools/sh2emu.py over edge + random vectors,
 *               comparing the whole request-queue RAM state, 0 mismatches).
 * Lift (truth): c/req_queue_69602.c  (same two packed leaves, verified in
 *               c/tests/test_req_queue_69602.py/.c)
 *
 * WHY THESE FUNCTIONS EXIST
 * -------------------------
 * The two leaves implement a 256-entry software request queue: a byte-flag
 * array (in-use bit) at 0xFFFFDE38 and a parallel 32-bit value array at
 * 0xFFFFDE40, each indexed by the low byte of r4.  `store` computes a scaled
 * value `r5 * 0x0FA0` + a 32-bit base read from RAM, writes it into the
 * value slot and sets the flag; `clear` just drops the flag so the slot can
 * be reused.  Both are dispatched through function-pointer tables elsewhere
 * in the ROM (e.g. the pool at 0x68CF4, and 0x69694 from 0x68A74/0x68BA0/
 * 0x68E38/0x68F6C/0x690BC/0x69310/0x69458/0x695A8).
 *
 * Disassembly of 60E1D400.bin @ 0x69602 (store):
 *
 *     624C   extu.b r4,r2            ; b = r4 & 0xFF
 *     D02E   mov.l  0x696C0,r0       ; r0 = 0xFFFFDE40 (value-array base)
 *     4208   shll2  r2               ; b * 4
 *     4F12   sts.l  macl,@-r15       ; save macl (mul.l clobbers it)
 *     9354   mov.w  0x696B6,r3       ; r3 = 0x0FA0
 *     0537   mul.l  r3,r5            ; macl = r5 * 0x0FA0
 *     051A   sts    macl,r5          ; r5 = (uint32)(r5 * 0x0FA0)
 *     9352   mov.w  0x696B8,r3       ; r3 = word 0xF430, SIGN-EXTENDED -> 0xFFFFF430
 *     6132   mov.l  @r3,r1           ; r1 = long@0xFFFFF430  (base value)
 *     351C   add    r1,r5            ; r5 = r5 + base
 *     644C   extu.b r4,r4            ; b (for the flag array index)
 *     0256   mov.l  r5,@(r0,r2)      ; long@(0xFFFFDE40 + b*4) = v
 *     E201   mov    #0x01,r2
 *     D027   mov.l  0x696BC,r0       ; r0 = 0xFFFFDE38 (flag-array base)
 *     0424   mov.b  r2,@(r0,r4)      ; byte@(0xFFFFDE38 + b) = 1
 *     000B   rts
 *     4F16   lds.l  @r15+,macl       ;   (delay slot) restore macl
 *
 * and @ 0x69694 (clear):
 *
 *     D009   mov.l  0x696BC,r0       ; r0 = 0xFFFFDE38 (flag-array base)
 *     E300   mov    #0x00,r3
 *     644C   extu.b r4,r4            ; b = r4 & 0xFF
 *     000B   rts
 *     0424   mov.b  r3,@(r0,r4)      ;   (delay slot) byte@(0xFFFFDE38 + b) = 0
 *
 * BIT-EXACTNESS NOTES
 * -------------------
 * 1. The 0x0FA0 multiplier is a plain SH-2 `mul.l` (low 32 bits only, held in
 *    MACL) — a modulo-2^32 multiply, so `(uint32_t)r5 * 0x0FA0u` matches even
 *    for r5 where the full product would overflow 32 bits.
 * 2. The base pointer is loaded as a WORD from the literal pool at 0x696B8
 *    (`0xF430`) and sign-extended to 0xFFFFF430 by `mov.w` — NOT 0x0000F430.
 *    `mov.l @r3,r1` then dereferences the RAM location 0xFFFFF430.
 * 3. `store` has a memory side effect on the flag byte even though it also
 *    writes the value slot; `clear` is a pure flag write.  Neither leaf reads
 *    the flag before writing — the flag always ends up 1 / 0 respectively.
 * 4. MACL is preserved across `store` via the stack; `clear` touches nothing
 *    but the flag byte and r0/r3/r4.
 *
 * Calling convention: plain SH-2 ABI entry — r4 = index (masked to 8 bits),
 * r5 = value (store only); no return value (void).
 * =============================================================================
 */
#include <stdint.h>

#include "rx8_samples.h"

#define REQ_FLAGS  0xFFFFDE38u   /* 256 byte in-use flags (byte per index)   */
#define REQ_VALUES 0xFFFFDE40u   /* 256 x u32 value slots, parallel array    */
#define REQ_BASE   0xFFFFF430u   /* u32 base added to every stored entry     */

/* 0x69602 — store one entry + set its flag.
 *   b = r4 & 0xFF
 *   long@(0xFFFFDE40 + b*4) = (uint32)(r5 * 0x0FA0) + long@0xFFFFF430
 *   byte@(0xFFFFDE38 + b)   = 1
 * (The 0x0FA0 multiply is the SH-2 `mul.l` low-32 result — modulo 2^32.) */
void rx8_req_queue_store_69602(uint32_t r4, uint32_t r5)
{
    uint32_t b = r4 & 0xFFu;
    uint32_t v = ((uint32_t)r5 * 0x0FA0u) + *(volatile uint32_t *)REQ_BASE;
    *(volatile uint32_t *)(REQ_VALUES + b * 4) = v;
    *(volatile uint8_t *)(REQ_FLAGS + b) = 1;
}

/* 0x69694 — clear one entry's flag (the value slot is left untouched). */
void rx8_req_queue_clear_69694(uint32_t r4)
{
    *(volatile uint8_t *)(REQ_FLAGS + (r4 & 0xFFu)) = 0;
}

/*
 * =============================================================================
 * rx8_least_square.c  —  SECURITY STATE CHECK BYTE
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x5687A
 * Status      : VERIFIED — behavioural equivalence to the ROM held by
 *               reconstructed/samples/tests/harness_least_square.py
 *               (host-gcc + mmap vs tools/sh2emu.py over random byte pairs),
 *               in addition to the existing emulator test
 *               c/tests/test_least_square_0x5687A.py (256 × 5 edge + random,
 *               0 errors).
 * Lift (truth): c/least_square_0x5687A.c  (same address; the IDA-ai symbol
 *               `least_square_0x5687A` is a misnomer — the function is NOT a
 *               least-squares fit).
 *
 * WHAT THIS IS
 * ------------
 * Despite the symbol name, the leaf is a 24-byte equality test:
 *
 *     0x5687A  extu.b  r4,r4           ; val = r4 & 0xFF
 *     0x5687C  mov.l   @(0x40,pc),r2   ; r2 = &0xFFFFD20B
 *     0x5687E  mov.b   @r2,r3          ; r3 = (int8)*(uint8*)r2  (sign-ext)
 *     0x56880  extu.b  r3,r3           ; ref = r3 & 0xFF
 *     0x56882  cmp/eq  r4,r3           ; T = (val == ref)
 *     0x56884  bf/s    .diff           ; T == 0 -> return 1
 *     0x56888  mov     #0x00,r4        ; T == 1 -> r4 = 0
 *     0x5688C  mov     #0x01,r4        ; .diff: r4 = 1
 *     0x5688E  rts / mov r4,r0
 *
 * i.e. 1 if the input byte differs from the byte stored at 0xFFFFD20B,
 * 0 if it matches.  The sign-extending `mov.b` + `extu.b` pair reduces to a
 * plain zero-extended byte load.  The two-way branch is a simple
 * compare-and-return; there is no arithmetic at all.
 *
 * ROLE IN THE FIRMWARE
 * --------------------
 * The address 0xFFFFD20B is `SECURITY_STATE_1` (docs/functions/
 * security_access_handler.md): non-zero = security already unlocked.  This
 * leaf is the `state_check1` helper of the SecurityAccess handler (SID 0x27):
 * subfunction 0x01 (RequestSeed) calls it with r4 = 0 and, when the stored
 * state is non-zero, gets back 1 → NRC 0x11 (GeneralReject).  The name
 * `rx8_least_square` keeps the IDA-ai symbol base; the behaviour is the
 * state check.
 *
 * NOTE ON THE HARDWARE ADDRESS: 0xFFFFD20B is not yet spelled out in
 * rx8_hw.h, so it is defined locally here (documented in the SecurityAccess
 * notes).  The host harness mmap()s the backing page so the volatile
 * dereference below works on x86-64 exactly as it does on the target.
 * =============================================================================
 */
#include <stdint.h>
#include "rx8_samples.h"

/* SECURITY_STATE_1 — non-zero = security already unlocked.
 * Source: docs/functions/security_access_handler.md (RAM state map). */
#define RX8_SECURITY_STATE_1_ADDR   0xFFFFD20Bu

/* 0x5687A  Returns 1 if `val` differs from SECURITY_STATE_1, else 0.
 * The parameter is deliberately `uint8_t`: the ROM's leading `extu.b` masks
 * r4 to its low byte, and a byte-typed parameter is that mask at the ABI
 * boundary (the oracle truncates any upper bits before the call). */
uint32_t rx8_least_square(uint8_t val)
{
    uint8_t ref = *(volatile uint8_t *)RX8_SECURITY_STATE_1_ADDR;
    return (val != ref) ? 1u : 0u;
}

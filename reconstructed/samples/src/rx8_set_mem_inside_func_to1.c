/*
 * =============================================================================
 * rx8_set_mem_inside_func_to1.c  —  SET A RAM FAULT/IN-PROGRESS FLAG BYTE TO 1
 * =============================================================================
 * ROM         : roms/stock/60E0FC00.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x3E3F0
 * Status      : VERIFIED — behavioural equivalence to the ROM bytes held by
 *               reconstructed/samples/tests/harness_set_mem_inside_func_to1.py
 *               (host-gcc vs tools/sh2emu.py over edge + 20000 random vectors,
 *               RAM side effect diffed bit-exactly; 0 mismatches).
 * Lift (truth): c/setMemInsideFUNCto1.c  (setMemInsideFUNCto1 @ 0x3E3F0)
 *
 * DISCREPANCY NOTE (ROM image):
 * -----------------------------
 * The lift and its docs (docs/functions/setMemInsideFUNCto1.md) place this
 * helper in **60E0FC00.bin**, and that is where the 6-byte leaf below really
 * lives.  In the sibling stock image roms/stock/60E1D400.bin the same address
 * 0x3E3F0 holds MID-FUNCTION bytes of an unrelated mem-accessor routine
 * (mov.l @lit,r0 / mov.b r14,@r1 ...) — executing it there runs off into
 * garbage and hits the reserved opcode 0x0000 (NotImplementedError), so the
 * harness MUST target 60E0FC00.bin for this address.  This is the only
 * discrepancy found vs the lift; the lift itself is byte-exact for its image.
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * A tiny register-only leaf called by the redundant-RAM read/validate layer
 * (c/mem_accessors.c: readValue_8bit @0x3E0DC, readValue_16bit @0x3E11C,
 * readValue_32bit_ADDRESS_VAL @0x3E15C, readValue_float @0x3E1AA ...) on a
 * complement/checksum mismatch to mark the cell as faulted/invalid.  It sets
 * the byte RAM[0xFFFFC638] to 1 ("inside function" / error flag).  Exact
 * disassembly of 60E0FC00.bin @ 0x3E3F0:
 *
 *     928B   mov.w  0x3E50A,r2   ; r2 = sign-ext(0xC638) = 0xFFFFC638
 *     E301   mov    #0x01,r3     ; r3 = 1
 *     000B   rts                 ; return to pr
 *     2230   mov.b  r3,@r2       ;   (delay slot) *(uint8_t*)0xFFFFC638 = 1
 *
 * The 16-bit literal 0xC638 at ROM 0x3E50A is SIGN-EXTENDED by mov.w, so the
 * effective byte address is 0xFFFFC638 (on-chip RAM window).  The write is a
 * plain 8-bit store of constant 1; nothing else is touched (no stack frame,
 * no other RAM/registers except r2/r3, both dead after the call).  The
 * function is ABI-clean: entered via bsr/jsr with pr holding the return
 * address and returned via rts — no args, no result.
 * =============================================================================
 */
#include <stdint.h>

/* 0xFFFFC638 — RAM fault / "inside function" in-progress flag byte, set to 1
 * by the redundant-memory read/validate layer on a validity mismatch. */
#define RX8_MEM_INSIDE_FLAG (*(volatile uint8_t *)0xFFFFC638u)

void rx8_set_mem_inside_func_to1(void)
{
    RX8_MEM_INSIDE_FLAG = 1;
}

/*
 * =============================================================================
 * rx8_obd_service_handler_648b4.c  —  OBD RUN-SUM UPDATE LEAF (RAM SIDE-EFFECTS)
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x648B4  (48 bytes, 0x648B4..0x648E3)
 * Status      : VERIFIED — behavioural equivalence to the ROM held by
 *               reconstructed/samples/tests/harness_obd_service_handler_648b4.py
 *               (host-gcc + mmap vs tools/sh2emu.py over edge + random vectors,
 *               comparing the two 16-bit RAM run-sum cells after every call;
 *               0 mismatches).
 * Lift (truth): c/obd_service_handler_648B4.c (same address; verified vs the
 *               ROM emulator in c/tests/test_obd_service_handler_648B4.py)
 *
 * WHAT THIS IS
 * ------------
 * The OBD/UDS service handler folds each encoded DTC byte into a pair of
 * redundant 16-bit (value, complement) run-sum cells in on-chip RAM:
 *
 *     0xFFFF8E98  cell A: written with enc8(running delta)
 *     0xFFFF8E9A  cell B: written with enc8(b)
 *
 * where enc8(x) = (x << 8) | ~x  is the verified (value,~value) cell encoder
 * leaf @0x2420 (c/math_primitives.c `encode`, sample rx8_encode.c).  The
 * value byte of a cell is its HIGH byte (big-endian SH-2E), so cell A's
 * running sum is the signed-byte sum of the two value bytes minus the input:
 *
 *     delta = s8(hi(word@0xFFFF8E98)) + s8(hi(word@0xFFFF8E9A)) - s8(b)
 *
 * The complement (low) bytes are never read — only rewritten — so a caller
 * that keeps the cells self-consistent (as enc8 always writes them) sees the
 * classic Denso redundant-encoding convention.  This leaf is invoked from
 * can_encode_handler_62ABC (0x62ABC, .py-tested) for each encoded DTC.
 *
 * CALLING CONVENTION
 * ------------------
 * Normal ABI entry: r4 = byte value b (only the low 8 bits are used — the
 * ROM saves r4 with `mov.b r4,@r15` and later reloads it sign-extended).
 * pr is saved/restored so the function can be called freely; r0-r4 are
 * clobbered; there is NO return value (pure side-effect leaf; r0 is left
 * holding the last enc8() result, unused).
 *
 * ENDIAN NOTE (host-C testing)
 * ----------------------------
 * byte@addr of a big-endian cell is the high byte of the 16-bit word.  The
 * C reads each cell as a uint16_t and extracts the high byte with `>> 8`, so
 * the numeric word values on the little-endian x86-64 test host agree with
 * the ROM exactly (same endian-safe pattern as obd_dtc_row_update_0x64490
 * and the c/obd_service_handler_648B4.c lift).
 * =============================================================================
 */
#include <stdint.h>

#include "rx8_samples.h"

/* Two redundant (value, ~value) 16-bit run-sum cells (on-chip RAM window). */
#define RX8_OBD_RUNSUM_CELL_A  0xFFFF8E98u   /* running-delta cell (this leaf) */
#define RX8_OBD_RUNSUM_CELL_B  0xFFFF8E9Au   /* last-input cell                */

/* enc8 — verified (value, complement) byte encoder leaf @0x2420
 * (c/math_primitives.c `encode`; sample rx8_encode.c).  High byte = value,
 * low byte = its ones' complement. */
static inline uint16_t enc8(uint8_t x)
{
    return (uint16_t)((x << 8) | (uint8_t)~x);
}

/* 0x648B4 — fold byte b into the two OBD run-sum cells (side effects only).
 *
 *   delta = s8(hi(cell A)) + s8(hi(cell B)) - s8(b)
 *   cell A = enc8(delta)
 *   cell B = enc8(b)
 *
 * The int8_t conversions reproduce the ROM's sign-extending `mov.b` loads;
 * the final (uint8_t) cast keeps enc8's input to the low byte of the 32-bit
 * delta, exactly like the ROM's `extu.b` inside the 0x2420 leaf.  The low
 * (complement) byte of each cell is read as part of the word but never
 * inspected, matching the ROM, which only loads the high byte. */
void rx8_obd_service_handler_648b4(uint8_t b)
{
    uint16_t wA = *(volatile uint16_t *)(uintptr_t)RX8_OBD_RUNSUM_CELL_A;
    uint16_t wB = *(volatile uint16_t *)(uintptr_t)RX8_OBD_RUNSUM_CELL_B;
    int32_t  delta = (int32_t)(int8_t)((wA >> 8) & 0xFF)
                   + (int32_t)(int8_t)((wB >> 8) & 0xFF)
                   - (int32_t)(int8_t)b;

    *(volatile uint16_t *)(uintptr_t)RX8_OBD_RUNSUM_CELL_A = enc8((uint8_t)delta);
    *(volatile uint16_t *)(uintptr_t)RX8_OBD_RUNSUM_CELL_B = enc8(b);
}

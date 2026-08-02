/*
 * =============================================================================
 * rx8_mem_accessors.c  —  THE REDUNDANT-RAM ACCESSOR FAMILY (11 LEAF FUNCTIONS)
 * =============================================================================
 * ROM         : roms/stock/60E0FC00.bin (Mazda RX-8 PCM, N3J1 family) — see the
 *               "ROM IDENTIFICATION" section below for why NOT 60E1D400.bin.
 * Addresses   : 0x3E0DC readValue_8bit_ADDRESS_VAL          (uint8_t r4 -> r0)
 *               0x3E11C readValue_16bit_ADDRESS_VAL          (uint16_t -> r0)
 *               0x3E15C readValue_32bit_ADDRESS_VAL          (uint32_t -> r0)
 *               0x3E1AA readValue_float_DEFAULTVAL_ADDRESS   (float fr4 -> fr0)
 *               0x3E1F8 updateMemoryAtAddress_8bit_ADDR_VAL  (void, r0 = 0)
 *               0x3E208 updateMemoryAtAddress_16bit_ADDR_VAL (void, r0 = 0)
 *               0x3E218 updateMemoryAtAddress_32bit_ADDR_VAL (void, r0 = 0)
 *               0x3E29E validateAddressCopy_8bit_ADDRESS     (int r0 = 0/1)
 *               0x3E2DA validateAddressCopy_16bit_ADDRESS    (int r0 = 0/1)
 *               0x3E330 validateAddressCopy_32bit_ADDRESS    (int r0 = 0/1)
 *               0x3E38A validateAddressCopy_float_ADDRESS    (int r0 = 0/1)
 * Status      : VERIFIED — behavioural equivalence to the ROM bytes held by
 *               reconstructed/samples/tests/harness_mem_accessors.py
 *               (host-gcc vs tools/sh2emu.py over edge vectors + N random
 *               vectors per accessor; bit-exact returns AND cell RAM
 *               side-effects incl. the checksum "scrub"; 0 mismatches).
 * Lift (truth): c/mem_accessors.c  — read that file first; it documents the
 *               two storage schemes (8/16-bit complement cells; 32-bit/float
 *               8-byte cells with a duplicated 16-bit checksum).
 * Harness     : reconstructed/samples/tests/harness_mem_accessors.py (this
 *               sample + tests/oracle_mem_accessors.c).
 *
 * ROM IDENTIFICATION (task-text discrepancy, documented)
 * -----------------------------------------------------
 * The task text names roms/stock/60E1D400.bin for these addresses.  That is
 * NOT the ROM this family lives in at 0x3E0DC..0x3E38A:
 *   - 60E0FC00.bin @0x3E0DC = 2F E6 6E 43 D3 8F ...   (the accessor bodies)
 *   - 60E1D400.bin @0x3E0DC = C7 41 FC 0C 93 6F ...   (unrelated calibration
 *     /fan code — NOT the accessors)
 * The addresses 0x3E0DC..0x3E38A in c/verified_addrs.txt (line 3) belong to
 * 60E0FC00.bin: c/mem_accessors.c documents them there, and its Track-A test
 * c/tests/test_mem_accessors.py executes the ROM at exactly those addresses
 * with ROM_PATH = roms/stock/60E0FC00.bin.  In 60E1D400.bin the SAME family
 * moved to 0x3ED3C (readValue_8bit), 0x3ED7C (readValue_16bit), etc., and its
 * update pair is cited in c/verified_addrs.txt as the "leaf port helpers"
 * 0x3EE58 (u16 complement store) / 0x3EE68 (u32 complement store) — those are
 * NOT in c/mem_accessors.c, so per the task they are excluded here (they are
 * part of the family but not of the lift).  The harness therefore runs the
 * REAL ROM bytes of 60E0FC00.bin at the eleven addresses above.
 *
 * STORAGE SCHEMES (from the lift)
 * -------------------------------
 * (1) 8-bit / 16-bit complement cells:  value stored together with its
 *     bitwise COMPLEMENT, big-endian.
 *        update_8bit  -> *(u16)addr  = (val<<8)  | (uint8_t)~val
 *        update_16bit -> *(u32)addr  = (val<<16) | (uint16_t)~val
 *     Read valid iff value == ~complement, else return the caller default.
 * (2) 32-bit / float cells: 8-byte cell = 4-byte value + a 16-bit CHECKSUM
 *     (~(hi16(value)+lo16(value))) stored TWICE (addr+4 and addr+6); a read is
 *     valid iff the freshly computed checksum equals EITHER stored copy.
 *     validateAddressCopy_32bit/float additionally SELF-HEAL on the valid
 *     path: both checksum copies are rewritten with the fresh checksum
 *     (the value bytes addr+0..3 are never touched; nothing is written on
 *     the invalid path).
 *
 * CALLING CONVENTIONS (all standard SH-2E ABI — NO non-ABI leaf)
 * -------------------------------------------------------------
 * Every function is entered via r4/r5 (integer args) and/or fr4 (the single
 * float arg of readValue_float) and returns in r0 (or fr0 for the float read),
 * exactly like a C function under the SH-2E ABI.  The harness therefore uses
 * plain cpu.call() for all eleven — no call_leaf() driver is needed.  The ROM
 * returns the 8/16-bit reads SIGN-EXTENDED in r0 (mov.b/mov.w into r13); the
 * lift returns uint8_t/uint16_t, so the harness compares r0&0xFF / r0&0xFFFF
 * against the lifted width (documented in the harness header).
 *
 * INTERNAL CALLEES (stubbed during verification, same as c/tests)
 * --------------------------------------------------------------
 *  0x3920 getSR, 0x3934 setSR             — interrupt-mask critical section
 *  0x3E3F0 setMemInsideFUNCto1            — error flag on read mismatch
 *  0x3E5A8 SetMemoryNotValid2             — error flag on validate mismatch
 * These are orthogonal to the returned datum (and to the cell side-effects
 * below); the lift omits them and c/tests/test_mem_accessors.py stubs all
 * four to `rts; nop` in the emulator RAM overlay.  This harness does the same
 * so the DATA behavior (complement/checksum validation + default fallback +
 * scrub) is what is compared.  0x3E1F8 and 0x3E208 make NO calls at all.
 *
 * RAM CELLS TOUCHED (per accessor)
 * --------------------------------
 *  update_8bit         writes addr[0..1]
 *  update_16bit        writes addr[0..3]
 *  update_32bit        writes addr[0..7] (value + two checksum copies)
 *  readValue_*         reads addr[0..3] (+ addr[4..7] for 32/float); no writes
 *  validate_8bit/16bit reads addr[0..3]; no writes
 *  validate_32/float   reads addr[0..7]; on the VALID path rewrites addr[4..5]
 *                      and addr[6..7] with the fresh checksum (scrub)
 *
 * ENDIANNESS APPROACH (host oracle is little-endian)
 * --------------------------------------------------
 * The SH-2E is big-endian; a host x86 is little-endian.  All multi-byte cell
 * traffic here goes through EXPLICIT big-endian byte assembly (b[0]<<8|b[1],
 * b[0]<<24|...), identical to rx8_get_maf_sensor_value.c, so the reconstructed
 * C and the emulator see the same NUMBER regardless of host endianness.  The
 * uint16_t* / uint32_t* pointer types of the lift are kept in the signatures
 * for name/type fidelity but the bodies access the bytes via a uint8_t* cast.
 *
 * LIFT-VS-ROM DISCREPANCIES
 * -------------------------
 * None found: the ROM data behavior matches c/mem_accessors.c bit-for-bit on
 * every path (complement/checksum validity, defaults, sign-extension of the
 * returned width, and both validate scrub side-effects) — consistent with the
 * lift's own 20000+-input Track-A result.  The only lift detail worth noting
 * is that the ROM's checksum is computed on SIGN-extended 16-bit halfwords
 * (mov.w) before the final extu.w; in two's-complement this is bit-identical
 * to the lift's unsigned (hi+lo) & 0xFFFF, so no code change was needed.
 * =============================================================================
 */
#include <stdint.h>
#include <string.h>

#include "rx8_samples.h"

/* ---- writes: store the value together with its complement ---- */

/* 0x3E1F8  updateMemoryAtAddress_8bit — *(u16*)addr = (val<<8) | (u8)~val.
 * ROM body: extu.b r5,r3; shll8 r3; not r5,r2; extu.b r2,r2; add r2,r3;
 * mov.w r3,@r4; rts (delay: mov #0,r0).  Pure leaf, r0 = 0. */
void updateMemoryAtAddress_8bit(uint16_t *addr, uint8_t val)
{
    uint8_t *b = (uint8_t *)addr;
    b[0] = val;
    b[1] = (uint8_t)~val;
}

/* 0x3E208  updateMemoryAtAddress_16bit — *(u32*)addr = (val<<16) | (u16)~val.
 * ROM body: extu.w r5,r3; shll16 r3; not r5,r2; extu.w r2,r2; add r2,r3;
 * mov.l r3,@r4; rts (delay: mov #0,r0).  Pure leaf, r0 = 0. */
void updateMemoryAtAddress_16bit(uint32_t *addr, uint16_t val)
{
    uint8_t *b = (uint8_t *)addr;
    b[0] = (uint8_t)(val >> 8);
    b[1] = (uint8_t)val;
    b[2] = (uint8_t)((uint16_t)~val >> 8);
    b[3] = (uint8_t)~val;
}

/* 0x3E218  updateMemoryAtAddress_32bit_ADDR_VAL — 8-byte checksum-guarded cell:
 * addr[0..3] = val; addr[4..5] = addr[6..7] = checksum = ~(hi16+lo16).
 * ROM body stages the value on the stack, computes the checksum once and
 * stores it to addr+4 and addr+6 around a getSR/setSR critical section,
 * then returns r0 = 0. */
void updateMemoryAtAddress_32bit_ADDR_VAL(uint8_t *addr, uint32_t val)
{
    uint16_t hi = (uint16_t)(val >> 16);
    uint16_t lo = (uint16_t)val;
    uint16_t checksum = (uint16_t)~(uint16_t)(hi + lo);

    addr[0] = (uint8_t)(hi >> 8);  addr[1] = (uint8_t)hi;
    addr[2] = (uint8_t)(lo >> 8);  addr[3] = (uint8_t)lo;
    addr[4] = (uint8_t)(checksum >> 8); addr[5] = (uint8_t)checksum;
    addr[6] = (uint8_t)(checksum >> 8); addr[7] = (uint8_t)checksum;
}

/* ---- reads: validate the complement/checksum, else return the default ---- */

/* 0x3E0DC  readValue_8bit_ADDRESS_VAL — 8-bit complement cell.  Returns the
 * stored value if intact else `dflt`.  The ROM returns the byte SIGN-EXTENDED
 * in r0 (the lift's uint8_t is compared via r0 & 0xFF). */
uint8_t readValue_8bit(const uint8_t *addr, uint8_t dflt)
{
    const uint8_t *b = (const uint8_t *)addr;
    uint8_t value = b[0];
    uint8_t comp  = b[1];
    if (value == (uint8_t)~comp)
        return value;                 /* complement matches: trusted */
    /* setMemInsideFUNCto1() 0x3E3F0: flag corruption (stubbed) */
    return dflt;                      /* fall back to caller default */
}

/* 0x3E11C  readValue_16bit_ADDRESS_VAL — 16-bit complement cell
 * (addr[0..1] = value, addr[2..3] = ~value).  Sign-extended r0 compared via
 * r0 & 0xFFFF. */
uint16_t readValue_16bit(const uint16_t *addr, uint16_t dflt)
{
    const uint8_t *b = (const uint8_t *)addr;
    uint16_t value = (uint16_t)(((uint16_t)b[0] << 8) | b[1]);
    uint16_t comp  = (uint16_t)(((uint16_t)b[2] << 8) | b[3]);
    if (value == (uint16_t)~comp)
        return value;
    /* setMemInsideFUNCto1() 0x3E3F0: flag corruption (stubbed) */
    return dflt;
}

/* 0x3E15C  readValue_32bit_ADDRESS_VAL — 32-bit value guarded by a duplicated
 * 16-bit checksum (8-byte cell, see updateMemoryAtAddress_32bit_ADDR_VAL).
 * Valid iff the fresh checksum matches EITHER stored copy (addr+4 or addr+6). */
uint32_t readValue_32bit_ADDRESS_VAL(const uint8_t *addr, uint32_t dflt)
{
    uint16_t hi = (uint16_t)(((uint16_t)addr[0] << 8) | addr[1]);
    uint16_t lo = (uint16_t)(((uint16_t)addr[2] << 8) | addr[3]);
    uint16_t checksum = (uint16_t)~(uint16_t)(hi + lo);
    uint16_t copy1 = (uint16_t)(((uint16_t)addr[4] << 8) | addr[5]);
    uint16_t copy2 = (uint16_t)(((uint16_t)addr[6] << 8) | addr[7]);

    if (checksum == copy1 || checksum == copy2)
        return ((uint32_t)hi << 16) | lo;
    /* setMemInsideFUNCto1() 0x3E3F0: flag corruption (stubbed) */
    return dflt;
}

/* 0x3E1AA  readValue_float_DEFAULTVAL_ADDRESS — float variant of
 * readValue_32bit_ADDRESS_VAL (same 8-byte checksum-guarded cell).  Register
 * assignment confirmed from asm: address is the int arg r4, dflt is the float
 * arg fr4 (stashed on the stack, reloaded into fr0 only on the invalid path);
 * the SH-2E ABI routes int args (r4-r7) and float args (fr4-fr6) through
 * independent register files. */
float readValue_float_DEFAULTVAL_ADDRESS(const uint8_t *addr, float dflt)
{
    uint16_t hi = (uint16_t)(((uint16_t)addr[0] << 8) | addr[1]);
    uint16_t lo = (uint16_t)(((uint16_t)addr[2] << 8) | addr[3]);
    uint16_t checksum = (uint16_t)~(uint16_t)(hi + lo);
    uint16_t copy1 = (uint16_t)(((uint16_t)addr[4] << 8) | addr[5]);
    uint16_t copy2 = (uint16_t)(((uint16_t)addr[6] << 8) | addr[7]);

    if (checksum == copy1 || checksum == copy2) {
        uint32_t bits = ((uint32_t)hi << 16) | lo;
        float value;
        memcpy(&value, &bits, sizeof(value));
        return value;
    }
    /* setMemInsideFUNCto1() 0x3E3F0: flag corruption (stubbed) */
    return dflt;
}

/* ---- validate-only: return an ERROR CODE (0 = intact, 1 = corrupted) ----
 * These do NOT return the stored value (confirmed from asm: no default arg,
 * r0 is only ever 0 or 1).  Polarity is inverted vs a natural "is valid". */

/* 0x3E29E  validateAddressCopy_8bit_ADDRESS — 8-bit complement cell.
 * Returns 0 if intact, 1 if corrupted (+ SetMemoryNotValid2() on the 1 path). */
int validateAddressCopy_8bit_ADDRESS(const uint8_t *addr)
{
    const uint8_t *b = (const uint8_t *)addr;
    uint8_t value = b[0];
    uint8_t comp  = b[1];
    if (value == (uint8_t)~comp)
        return 0;                     /* intact */
    /* SetMemoryNotValid2() 0x3E5A8: flag corruption (stubbed) */
    return 1;                         /* corrupted */
}

/* 0x3E2DA  validateAddressCopy_16bit_ADDRESS — 16-bit complement cell
 * (addr[0..1] = value, addr[2..3] = ~value).  Returns 0/1. */
int validateAddressCopy_16bit_ADDRESS(const uint8_t *addr)
{
    uint16_t value = (uint16_t)(((uint16_t)addr[0] << 8) | addr[1]);
    uint16_t comp  = (uint16_t)(((uint16_t)addr[2] << 8) | addr[3]);
    if (value == (uint16_t)~comp)
        return 0;
    /* SetMemoryNotValid2() 0x3E5A8: flag corruption (stubbed) */
    return 1;
}

/* 0x3E38A  validateAddressCopy_float_ADDRESS — validate the 8-byte
 * checksum-guarded float cell.  SIDE EFFECT confirmed from asm and emulator
 * RAM diffing: on the VALID path (and only there) it unconditionally rewrites
 * BOTH checksum copies (addr+4 and addr+6) with the fresh checksum — i.e. it
 * "scrubs"/re-synchronizes the redundant pair, healing whichever copy did not
 * individually match.  Never touches the value bytes; no write on the invalid
 * path.  Returns 0 if intact, 1 if corrupted. */
int validateAddressCopy_float_ADDRESS(uint8_t *addr)
{
    uint16_t hi = (uint16_t)(((uint16_t)addr[0] << 8) | addr[1]);
    uint16_t lo = (uint16_t)(((uint16_t)addr[2] << 8) | addr[3]);
    uint16_t checksum = (uint16_t)~(uint16_t)(hi + lo);
    uint16_t copy1 = (uint16_t)(((uint16_t)addr[4] << 8) | addr[5]);
    uint16_t copy2 = (uint16_t)(((uint16_t)addr[6] << 8) | addr[7]);

    if (checksum == copy1 || checksum == copy2) {
        addr[4] = (uint8_t)(checksum >> 8); addr[5] = (uint8_t)checksum;
        addr[6] = (uint8_t)(checksum >> 8); addr[7] = (uint8_t)checksum;
        return 0;
    }
    /* SetMemoryNotValid2() 0x3E5A8: flag corruption (stubbed) */
    return 1;
}

/* 0x3E330  validateAddressCopy_32bit_ADDRESS — validate the 8-byte
 * checksum-guarded cell holding a raw 32-bit VALUE (as opposed to the float
 * bit-pattern above): same redundancy scheme, same self-heal scrub, confirmed
 * identical from asm apart from what is stored at addr+0..3.  Returns 0/1.
 * (The asm also stages a throwaway stack copy of the value — dead, never read
 * back; omitted, it has no effect on the result.) */
int validateAddressCopy_32bit_ADDRESS(uint8_t *addr)
{
    uint16_t hi = (uint16_t)(((uint16_t)addr[0] << 8) | addr[1]);
    uint16_t lo = (uint16_t)(((uint16_t)addr[2] << 8) | addr[3]);
    uint16_t checksum = (uint16_t)~(uint16_t)(hi + lo);
    uint16_t copy1 = (uint16_t)(((uint16_t)addr[4] << 8) | addr[5]);
    uint16_t copy2 = (uint16_t)(((uint16_t)addr[6] << 8) | addr[7]);

    if (checksum == copy1 || checksum == copy2) {
        addr[4] = (uint8_t)(checksum >> 8); addr[5] = (uint8_t)checksum;
        addr[6] = (uint8_t)(checksum >> 8); addr[7] = (uint8_t)checksum;
        return 0;
    }
    /* SetMemoryNotValid2() 0x3E5A8: flag corruption (stubbed) */
    return 1;
}

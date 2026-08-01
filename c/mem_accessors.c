/*
 * mem_accessors.c  —  RX-8 PCM redundant RAM accessor layer (equinox names, hand Ghidra
 * RE by equinox311).  Safety-critical variables are stored together with a redundancy
 * check; a read validates the check and falls back to a caller default on mismatch
 * (single-bit RAM corruption -> safe default + error flag). This is the layer under
 * most fueling/ignition/adaptive state; readValue_8bit is called ~129x, update_8bit ~145x.
 *
 * Two storage schemes coexist in this family:
 *
 *  (1) 8-bit/16-bit cells: value stored together with its bitwise COMPLEMENT, big-endian.
 *        update_8bit  writes a 16-bit word: (val<<8)  | (uint8_t)~val
 *        update_16bit writes a 32-bit word: (val<<16) | (uint16_t)~val
 *      Validity: value == ~complement.
 *
 *  (2) 32-bit/float cells: 8-byte redundant cell = 4-byte value + a 16-bit CHECKSUM
 *      (~(hi16(value)+lo16(value))) stored TWICE (addr+4 and addr+6) — the value itself
 *      is NOT duplicated, only the checksum is, and either copy matching is accepted
 *      (confirmed from asm: this differs from the simple complement scheme above, despite
 *      the "value + ~value" shorthand used to describe this family generally).
 *        update_32bit writes: addr[0..3]=val, addr[4..5]=addr[6..7]=checksum
 *      Validity: checksum == addr[4..5] OR checksum == addr[6..7].
 *
 * The read/validate side runs inside an interrupt-masked critical section (getSR(0x3920)
 * raise IPL -> ... -> setSR(0x3934) restore) and calls setMemInsideFUNCto1(0x3E3F0) (8/16/32/
 * float reads) or SetMemoryNotValid2(0x3E5A8) (validateAddressCopy_* family) to set an error
 * flag on mismatch — see docs/functions/setMemInsideFUNCto1.md and
 * docs/functions/SetMemoryNotValid2.md. Those wrappers are orthogonal to the data result
 * and are omitted from the lift (stubbed to rts during verification); the DATA behavior below
 * is what was checked.
 *
 * Track A: verified behavior-equivalent to the emulated ROM (tools/sh2emu.py) — >=20000 random
 * inputs each (valid + corrupted pairs), 0 mismatches. Test: c/tests/test_mem_accessors.py.
 * (Verifying these required fixing sh2emu's mov.b/mov.w @(disp,Rm),R0 opcode mask, 0xF00F->0xFF00.)
 */
#include <stdint.h>
#include <string.h>

/* ---- writes: store value together with its complement ---- */

/* 0x3E1F8  *(uint16_t*)addr = value:~value  (8-bit datum, 16-bit redundant cell) */
void updateMemoryAtAddress_8bit(uint16_t *addr, uint8_t val)
{
    *addr = (uint16_t)((val << 8) | (uint8_t)~val);
}

/* 0x3E208  *(uint32_t*)addr = value:~value  (16-bit datum, 32-bit redundant cell) */
void updateMemoryAtAddress_16bit(uint32_t *addr, uint16_t val)
{
    *addr = ((uint32_t)val << 16) | (uint16_t)~val;
}

/* 0x3E218  *(uint32_t*)addr = val; checksum = ~(hi16(val)+lo16(val)) written TWICE
 * (addr+4 and addr+6) — 8-byte redundant cell (32-bit value guarded by a duplicated 16-bit
 * checksum, NOT a full complement of the value; see file header). */
void updateMemoryAtAddress_32bit_ADDR_VAL(uint8_t *addr, uint32_t val)
{
    uint16_t hi = (uint16_t)(val >> 16);
    uint16_t lo = (uint16_t)val;
    uint16_t checksum = (uint16_t)~(uint16_t)(hi + lo);

    addr[0] = (uint8_t)(hi >> 8);  addr[1] = (uint8_t)hi;
    addr[2] = (uint8_t)(lo >> 8);  addr[3] = (uint8_t)lo;
    addr[4] = (uint8_t)(checksum >> 8); addr[5] = (uint8_t)checksum;   /* checksum copy 1 */
    addr[6] = (uint8_t)(checksum >> 8); addr[7] = (uint8_t)checksum;   /* checksum copy 2 */
}

/* ---- reads: validate the complement/checksum, else return the default ---- */

/* 0x3E0DC  read an 8-bit redundant cell; return value if intact, else `dflt` (+error flag). */
uint8_t readValue_8bit(const uint8_t *addr, uint8_t dflt)
{
    uint8_t value = addr[0];
    uint8_t comp  = addr[1];
    if (value == (uint8_t)~comp)
        return value;                 /* complement matches: trusted */
    /* setMemInsideFUNCto1(): flag corruption */
    return dflt;                      /* fall back to caller default */
}

/* 0x3E11C  read a 16-bit redundant cell; return value if intact, else `dflt` (+error flag). */
uint16_t readValue_16bit(const uint16_t *addr, uint16_t dflt)
{
    uint16_t value = addr[0];
    uint16_t comp  = addr[1];
    if (value == (uint16_t)~comp)
        return value;
    /* setMemInsideFUNCto1(): flag corruption */
    return dflt;
}

/* 0x3E15C  read a 32-bit value guarded by a redundant 16-bit checksum (8-byte cell — see
 * updateMemoryAtAddress_32bit_ADDR_VAL): checksum = ~(hi16(value)+lo16(value)); valid if the
 * freshly computed checksum matches EITHER stored copy (addr+4 or addr+6). Returns value if
 * valid, else `dflt` (+error flag). */
uint32_t readValue_32bit_ADDRESS_VAL(const uint8_t *addr, uint32_t dflt)
{
    uint16_t hi = (uint16_t)(((uint16_t)addr[0] << 8) | addr[1]);
    uint16_t lo = (uint16_t)(((uint16_t)addr[2] << 8) | addr[3]);
    uint16_t checksum = (uint16_t)~(uint16_t)(hi + lo);
    uint16_t copy1 = (uint16_t)(((uint16_t)addr[4] << 8) | addr[5]);
    uint16_t copy2 = (uint16_t)(((uint16_t)addr[6] << 8) | addr[7]);

    if (checksum == copy1 || checksum == copy2)
        return ((uint32_t)hi << 16) | lo;
    /* setMemInsideFUNCto1(): flag corruption */
    return dflt;
}

/* 0x3E1AA  float variant of readValue_32bit_ADDRESS_VAL (same 8-byte checksum-guarded cell).
 * Register assignment CONFIRMED from asm: address is the int arg r4 (drives every byte/word
 * read), dflt is the float arg fr4 (stashed on the stack, reloaded into fr0 only on the
 * invalid path). The SH-2E ABI routes int/pointer args (r4-r7) and float args (fr4-fr6)
 * through independent register files, so the ordering implied by the Ghidra name
 * ("DEFAULTVAL_ADDRESS") does not mean dflt is passed before address -- address is still
 * the (only) integer arg, dflt is still the (only) float arg. */
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
    /* setMemInsideFUNCto1(): flag corruption */
    return dflt;
}

/* ---- validate-only: check redundancy, return an ERROR CODE (0=intact,1=corrupted) ----
 * These do NOT return the stored value (confirmed from asm: no default arg, r0 is only
 * ever 0 or 1). Note the polarity is inverted vs a natural "is valid" boolean. */

/* 0x3E29E  validate an 8-bit redundant cell (addr[0]=value, addr[1]=~value).
 * Returns 0 if intact, 1 if corrupted (+ SetMemoryNotValid2() error flag on the 1 path). */
int validateAddressCopy_8bit_ADDRESS(const uint8_t *addr)
{
    uint8_t value = addr[0];
    uint8_t comp  = addr[1];
    if (value == (uint8_t)~comp)
        return 0;                     /* intact */
    /* SetMemoryNotValid2(): flag corruption */
    return 1;                         /* corrupted */
}

/* 0x3E2DA  validate a 16-bit redundant cell (addr[0..1]=value, addr[2..3]=~value).
 * Returns 0 if intact, 1 if corrupted (+ SetMemoryNotValid2() error flag on the 1 path). */
int validateAddressCopy_16bit_ADDRESS(const uint8_t *addr)
{
    uint16_t value = (uint16_t)(((uint16_t)addr[0] << 8) | addr[1]);
    uint16_t comp  = (uint16_t)(((uint16_t)addr[2] << 8) | addr[3]);
    if (value == (uint16_t)~comp)
        return 0;
    /* SetMemoryNotValid2(): flag corruption */
    return 1;
}

/* 0x3E38A  validate the 8-byte checksum-guarded float cell (see readValue_float_DEFAULTVAL_
 * ADDRESS). Returns 0 if intact, 1 if corrupted (+ SetMemoryNotValid2() error flag on the 1
 * path). SIDE EFFECT confirmed from asm and from emulator RAM diffing: on the VALID path
 * (and only there) it unconditionally rewrites BOTH checksum copies (addr+4 and addr+6)
 * with the freshly recomputed checksum -- i.e. it "scrubs"/re-synchronizes the redundant
 * checksum pair, healing whichever copy did not individually match (the OR check means one
 * stale/corrupted copy is still accepted, and this call repairs it in place). It never
 * touches the value bytes (addr+0..3) and performs no write on the invalid path. */
int validateAddressCopy_float_ADDRESS(uint8_t *addr)
{
    uint16_t hi = (uint16_t)(((uint16_t)addr[0] << 8) | addr[1]);
    uint16_t lo = (uint16_t)(((uint16_t)addr[2] << 8) | addr[3]);
    uint16_t checksum = (uint16_t)~(uint16_t)(hi + lo);
    uint16_t copy1 = (uint16_t)(((uint16_t)addr[4] << 8) | addr[5]);
    uint16_t copy2 = (uint16_t)(((uint16_t)addr[6] << 8) | addr[7]);

    if (checksum == copy1 || checksum == copy2) {
        addr[4] = (uint8_t)(checksum >> 8); addr[5] = (uint8_t)checksum;   /* re-sync copy 1 */
        addr[6] = (uint8_t)(checksum >> 8); addr[7] = (uint8_t)checksum;   /* re-sync copy 2 */
        return 0;
    }
    /* SetMemoryNotValid2(): flag corruption */
    return 1;
}

/* 0x3E330  validate the 8-byte checksum-guarded cell holding a raw 32-bit VALUE (as opposed
 * to validateAddressCopy_float_ADDRESS's float bit-pattern) — same redundancy scheme, same
 * self-heal side effect, confirmed identical from asm apart from what's stored at addr+0..3:
 * checksum = ~(hi16(value)+lo16(value)); valid if it matches EITHER stored copy (addr+4 or
 * addr+6). Returns 0 if intact, 1 if corrupted (+ SetMemoryNotValid2() error flag on the 1
 * path). SIDE EFFECT confirmed from asm: on the VALID path (and only there) it unconditionally
 * rewrites BOTH checksum copies with the freshly recomputed checksum, repairing whichever
 * copy did not individually match (identical scrub behavior to validateAddressCopy_float_
 * ADDRESS). Never touches the value bytes (addr+0..3); no write on the invalid path. The asm
 * also stages a throwaway copy of the 4-byte value on the stack (dead — never read back
 * before the function returns) as part of the getSR-guarded critical section setup; omitted
 * here since it has no effect on the result.
 *
 * Track A: verified vs the emulated ROM (tools/sh2emu.py), 25000 inputs (valid1/valid2/invalid
 * checksum-pair modes, incl. the scrub/no-scrub RAM side effect diffed against cpu.ram), 0
 * mismatches. Test: c/tests/test_mem_accessors.py. */
int validateAddressCopy_32bit_ADDRESS(uint8_t *addr)
{
    uint16_t hi = (uint16_t)(((uint16_t)addr[0] << 8) | addr[1]);
    uint16_t lo = (uint16_t)(((uint16_t)addr[2] << 8) | addr[3]);
    uint16_t checksum = (uint16_t)~(uint16_t)(hi + lo);
    uint16_t copy1 = (uint16_t)(((uint16_t)addr[4] << 8) | addr[5]);
    uint16_t copy2 = (uint16_t)(((uint16_t)addr[6] << 8) | addr[7]);

    if (checksum == copy1 || checksum == copy2) {
        addr[4] = (uint8_t)(checksum >> 8); addr[5] = (uint8_t)checksum;   /* re-sync copy 1 */
        addr[6] = (uint8_t)(checksum >> 8); addr[7] = (uint8_t)checksum;   /* re-sync copy 2 */
        return 0;
    }
    /* SetMemoryNotValid2(): flag corruption */
    return 1;
}

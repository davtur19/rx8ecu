/*
 * rom_be.h  —  portable big-endian ROM accessors for host lifts.
 *
 * The SH-2E target is big-endian; host builds (x86-64/ARM-LE) are usually
 * little-endian, and may fault on misaligned word loads. These helpers decode
 * BE u16/u32/f32 values from a byte pointer with memcpy (alignment-safe, no
 * strict-aliasing violation) followed by an explicit byte swap that compiles
 * to a single bswap/movbe on LE hosts and to nothing on BE hosts.
 *
 * Convention (see c/2DLookup.c, c/3dLookup.c, c/mem_accessors.c):
 *   - `Map1D`/`Map2D` structs and lookup cell arrays passed to the lookup
 *     functions are HOST-ORDER arrays. The BE->host conversion happens once,
 *     when a descriptor is materialized from ROM bytes, using these helpers —
 *     the lookup bodies never cast the ROM image.
 *   - Redundant-cell accessors (c/mem_accessors.c) take `uint8_t *` and use
 *     these helpers so the byte layout matches the BE target exactly.
 */
#ifndef ROM_BE_H
#define ROM_BE_H

#include <stdint.h>
#include <string.h>

#if defined(__BYTE_ORDER__) && (__BYTE_ORDER__ == __ORDER_BIG_ENDIAN__)
#define ROM_BE_NATIVE_BE 1
#else
#define ROM_BE_NATIVE_BE 0
#endif

/* Read a big-endian u16 from (possibly misaligned) bytes. */
static inline uint16_t rom_be16(const uint8_t *p)
{
    uint16_t v;
    memcpy(&v, p, sizeof(v));
#if ROM_BE_NATIVE_BE
    return v;
#else
    return (uint16_t)((uint16_t)(v << 8) | (uint16_t)(v >> 8));
#endif
}

/* Read a big-endian u32 from (possibly misaligned) bytes. */
static inline uint32_t rom_be32(const uint8_t *p)
{
    uint32_t v;
    memcpy(&v, p, sizeof(v));
#if ROM_BE_NATIVE_BE
    return v;
#else
    return ((v & 0x000000FFu) << 24) |
           ((v & 0x0000FF00u) << 8) |
           ((v & 0x00FF0000u) >> 8) |
           ((v & 0xFF000000u) >> 24);
#endif
}

/* Read a big-endian IEEE-754 f32 from (possibly misaligned) bytes. */
static inline float rom_bef32(const uint8_t *p)
{
    uint32_t u = rom_be32(p);
    float f;
    memcpy(&f, &u, sizeof(f));
    return f;
}

/* Write a u16/u32/f32 as big-endian bytes (memcpy: alignment-safe). */
static inline void rom_be16_write(uint8_t *p, uint16_t v)
{
#if !ROM_BE_NATIVE_BE
    v = (uint16_t)((uint16_t)(v << 8) | (uint16_t)(v >> 8));
#endif
    memcpy(p, &v, sizeof(v));
}

static inline void rom_be32_write(uint8_t *p, uint32_t v)
{
#if !ROM_BE_NATIVE_BE
    v = ((v & 0x000000FFu) << 24) |
        ((v & 0x0000FF00u) << 8) |
        ((v & 0x00FF0000u) >> 8) |
        ((v & 0xFF000000u) >> 24);
#endif
    memcpy(p, &v, sizeof(v));
}

static inline void rom_bef32_write(uint8_t *p, float f)
{
    uint32_t u;
    memcpy(&u, &f, sizeof(u));
    rom_be32_write(p, u);
}

#endif /* ROM_BE_H */

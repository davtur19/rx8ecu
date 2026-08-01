/* ============================================================================
 * oracle_get_fault_status.c  —  host test rig for rx8_get_fault_status @0x6743C
 * ============================================================================
 * Compile together with src/rx8_get_fault_status.c and pipe test vectors on
 * stdin; one vector per line:
 *
 *     gs <chan> <blob>  -> <result 2 hex digits>
 *
 *   chan : channel index (0x0000..0xFFFF), r4 to the ROM function
 *   blob : the backup-RAM seed bytes as one big hex string, laid out as
 *          0xFFFFD494[256] | 0xFFFFD638[256] | 0xFFFF8D7C[256]
 *          | 0xFFFFD3F0 u16 | 0xFFFFD96C u32 (774 bytes, 1548 hex chars)
 *
 * The oracle contains NO copy of getFaultStatus — that logic lives solely in
 * src/rx8_get_fault_status.c.  It mirrors the *caller-side* environment:
 *  - the ROM file (argv[1], default roms/stock/60E1D400.bin) is copied into
 *    a MAP_FIXED mirror of the 0x0007E4DC fault-table region, so the
 *    sample's fixed-address ROM dereference works fault-free on the host;
 *  - every RAM window the ROM chain touches (0xFFFFD494/0xFFFFD638 DTC
 *    flags, 0xFFFF8D7C indirect table, 0xFFFFD3F0 eval word, 0xFFFFD96C
 *    enable mask) is backed by the same MAP_FIXED trick as
 *    tests/host_oracle.c and seeded per-vector from the blob.
 *
 * Because getFaultStatus internally `bsr`s the secondary evaluator
 * @0x67494, this rig also implements rx8_get_fault_eval_state() (declared by
 * the sample) as a faithful host model of that ROM sub-check: the nine
 * condition checks of 0x67494 with their exact ROM table/flag semantics
 * (0x67534 stub, 0x67538 DTC-list walk, 0x675AC indirect table, 0x675CA DTC
 * data check, 0x675E6 byte-indexed check and their dtc_data_read_* helpers).
 * ==========================================================================*/
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

#include "rx8_samples.h"

uint8_t rx8_get_fault_status(uint16_t channel);

/* ---- ROM mirror ------------------------------------------------------------
 * The fault-table dereference in the sample uses the ROM's fixed absolute
 * address 0x7E4DC + (chan & 0xFFFF)*4 (max word 0xBE4D8).  Map that span and
 * copy the real bytes in, so `*(const uint32_t*)0x7E4DC` faults-free and
 * matches the emulator (bytes beyond the 512 KiB image read as 0 there). */
#define ROM_MIRROR_BASE   0x70000u
#define ROM_MIRROR_END    0xC0000u

static const unsigned char *g_rom;
static size_t g_romlen;

static uint8_t rb(uint32_t a)
{
    a &= 0xFFFFFFFFu;
    /* Backup/on-chip RAM (0xFFFF8000..0xFFFFFFFF) — mmap'd, seeded per-vec. */
    if (a >= 0xFFFF8000u) {
        return *(volatile uint8_t *)(uintptr_t)a;
    }
    if (a < g_romlen) {
        return g_rom[a];
    }
    return 0;
}

static uint16_t rd16(uint32_t a)
{
    return (uint16_t)(((uint16_t)rb(a) << 8) | rb(a + 1));
}

static uint32_t rd32(uint32_t a)
{
    return ((uint32_t)rb(a) << 24) | ((uint32_t)rb(a + 1) << 16)
         | ((uint32_t)rb(a + 2) << 8) | (uint32_t)rb(a + 3);
}

static int load_rom(const char *path)
{
    FILE *f = fopen(path, "rb");
    long n;
    unsigned char *buf;

    if (!f) {
        perror(path);
        return -1;
    }
    fseek(f, 0, SEEK_END);
    n = ftell(f);
    fseek(f, 0, SEEK_SET);
    buf = (unsigned char *)malloc((size_t)(n > 0 ? n : 1));
    if (!buf || fread(buf, 1, (size_t)n, f) != (size_t)n) {
        fclose(f);
        free(buf);
        return -1;
    }
    fclose(f);
    g_rom = buf;
    g_romlen = (size_t)n;
    return 0;
}

static int map_region(uintptr_t base, size_t len)
{
    long page = sysconf(_SC_PAGESIZE);
    uintptr_t lo = base & ~((uintptr_t)page - 1);
    uintptr_t hi = (base + len + (uintptr_t)page - 1) & ~((uintptr_t)page - 1);
    void *p = mmap((void *)lo, (size_t)(hi - lo), PROT_READ | PROT_WRITE,
                   MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED, -1, 0);
    if (p == MAP_FAILED) {
        perror("mmap");
        return -1;
    }
    return 0;
}

static int setup_memory(void)
{
    /* ROM fault-table span: 0x70000..0xC0000 (zeros beyond the 512 KiB ROM). */
    if (map_region(ROM_MIRROR_BASE, ROM_MIRROR_END - ROM_MIRROR_BASE) != 0) {
        return -1;
    }
    {
        /* The mirror holds the ROM as the emulator sees it: absolute address
         * == file offset (the image loads at 0).  Copy g_rom[0x70000..0x80000)
         * into mirror[0x70000..0x80000); the rest stays zero-filled, matching
         * the emulator's reads beyond the 512 KiB image. */
        size_t skip = ROM_MIRROR_BASE < g_romlen ? ROM_MIRROR_BASE : g_romlen;
        size_t span = ROM_MIRROR_END - ROM_MIRROR_BASE;
        size_t copy = span < (g_romlen - skip) ? span : (g_romlen - skip);
        memcpy((void *)(uintptr_t)ROM_MIRROR_BASE, g_rom + skip, copy);
    }
    /* Backup-RAM windows: 0xFFFF8000 (indirect byte table) and
     * 0xFFFFD000 (DTC flags, eval word, enable mask) up to 0xFFFFFFFF. */
    for (uintptr_t a = 0xFFFF8000u; a < 0x100000000u; a += 0x1000u) {
        if (map_region(a, 0x1000u) != 0) {
            return -1;
        }
    }
    return 0;
}

/* ---- host model of the secondary evaluator @0x67494 -----------------------
 * See the header of src/rx8_get_fault_status.c.  All helpers below are the
 * C shape of the ROM bytes at the stated addresses (60E1D400.bin). */

/* 0x67534 — check_cond_A: `rts` with `mov #0x00,r0` in the delay slot.  This
 * ROM stub always returns 0, so its four bit positions in the eval result
 * (0x80000000/0x20000000/0x04000000/0x02000000/0x01000000) are never set. */
static uint8_t check_cond_a(uint16_t fault_code)
{
    (void)fault_code;
    return 0;
}

/* 0x60EB4 — dtc_data_read_60EB4: entry byte ROM@0x7E338+entry selects which
 * backup-RAM flag decides: bit 0x20 set -> 0xFFFFD494+entry == 1, else
 * 0xFFFFD638+entry == 0xC0. */
static uint8_t dtc_data_read_60eb4(uint16_t entry)
{
    if (rb(0x7E338u + entry) & 0x20u) {
        return (rb(0xFFFFD494u + entry) == 0x01u) ? 1 : 0;
    }
    return (rb(0xFFFFD638u + entry) == 0xC0u) ? 1 : 0;
}

/* 0x67538 — check_cond_B: walk the 16-bit word list whose pointer is
 * ROM@0x7ECD0 + code*4; validate each non-terminator word (0xFFFF sentinel,
 * 0xFFFE skip, > 50 entries bound) until one validates. */
static uint8_t check_cond_b(uint16_t fault_code)
{
    uint32_t p = rd32(0x7ECD0u + (fault_code & 0xFFFFu) * 4u);
    uint16_t n = 0;
    for (;;) {
        uint16_t w = rd16(p + n * 2u);
        if (w == 0xFFFFu) {
            return 0;
        }
        if (n > 50u) {
            return 0;
        }
        if (w != 0xFFFEu && dtc_data_read_60eb4(w) == 1) {
            return 1;
        }
        n++;
    }
}

/* 0x675AC — check_cond_C: word@0x7DAEA + code*2 indexes a byte in the
 * backup-RAM table at 0xFFFF8D7C (byte index = word * 2); nonzero = present.
 * The word read is mov.w (sign-extended) then extu.w, i.e. a plain u16. */
static uint8_t check_cond_c(uint16_t fault_code)
{
    uint16_t idx = rd16(0x7DAEAu + (fault_code & 0xFFFFu) * 2u);
    return (rb((0xFFFF8D7Cu + (uint32_t)idx * 2u) & 0xFFFFFFFFu) != 0u) ? 1 : 0;
}

/* 0x60DEE — dtc_data_read_60DEE: r13 (the "found" latch) is pre-loaded with
 * 1; the list body is unreachable in this ROM (the loop-back condition
 * cmp/ge #0xFF, r11 at 0x60E7C always holds), so the first-byte sentinel
 * test only ever confirms r13 == 1.  Returns 1 for every input. */
static uint8_t dtc_data_read_60dee(uint16_t fault_code)
{
    (void)fault_code;
    return 1;
}

/* 0x675CA — check_cond_D: returns 1 when dtc_data_read_60DEE == 0 (inverted
 * `bf` in the ROM); with the constant-1 reader above it never fires. */
static uint8_t check_cond_d(uint16_t fault_code)
{
    return (dtc_data_read_60dee(fault_code) != 0u) ? 0 : 1;
}

/* 0x60EFE — dtc_data_read_60EFE: reads the backup-RAM word @0xFFFFD3F0 and
 * returns its high byte (idx 0) or low byte (idx 1); other idx -> 0.  The
 * mov.w sign extension is irrelevant: the caller ANDs with a byte and
 * extu.b's the result. */
static uint8_t dtc_data_read_60efe(uint8_t idx)
{
    uint16_t w = rd16(0xFFFFD3F0u);
    if (idx == 0u) {
        return (uint8_t)(w >> 8);
    }
    if (idx == 1u) {
        return (uint8_t)(w & 0xFFu);
    }
    return 0;
}

/* 0x675E6 — check_cond_E: r11 starts at 1 and is cleared if either
 * (dtc_data_read_60EFE(i) & byte@0x7E734 + code*2 + i) is nonzero. */
static uint8_t check_cond_e(uint16_t fault_code)
{
    uint32_t base = 0x7E734u + (fault_code & 0xFFFFu) * 2u;
    uint8_t r = 1;
    if ((dtc_data_read_60efe(0) & rb(base)) != 0) {
        r = 0;
    }
    if ((dtc_data_read_60efe(1) & rb(base + 1)) != 0) {
        r = 0;
    }
    return r;
}

/* 0x67494 — secondary evaluator (getFaultStatus_subcheck in the docs): the
 * nine condition checks, each ORing one bit of the upper word.  Bits from
 * check_cond_A (stub, always 0) and check_cond_D (constant-0 here) never
 * fire; B/C/E are live. */
uint32_t rx8_get_fault_eval_state(uint16_t channel)
{
    uint32_t result = 0;

    if (check_cond_a(channel) != 0) result |= 0x80000000u;
    if (check_cond_b(channel) != 0) result |= 0x40000000u;
    if (check_cond_a(channel) != 0) result |= 0x20000000u;
    if (check_cond_c(channel) != 0) result |= 0x10000000u;
    if (check_cond_d(channel) != 0) result |= 0x08000000u;
    if (check_cond_a(channel) != 0) result |= 0x04000000u;
    if (check_cond_a(channel) != 0) result |= 0x02000000u;
    if (check_cond_a(channel) != 0) result |= 0x01000000u;
    if (check_cond_e(channel) != 0) result |= 0x00800000u;

    return result;
}

/* ---- seed-blob plumbing ---------------------------------------------------- */
static int hexval(int c)
{
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    return -1;
}

static int parse_hex(const char *s, uint8_t *out, size_t nbytes)
{
    size_t i;
    for (i = 0; i < nbytes; i++) {
        int hi = hexval((unsigned char)s[2 * i]);
        int lo = hexval((unsigned char)s[2 * i + 1]);
        if (hi < 0 || lo < 0) {
            return -1;
        }
        out[i] = (uint8_t)((hi << 4) | lo);
    }
    return 0;
}

#define SEED_D494 256u
#define SEED_D638 256u
#define SEED_D8D7C 256u
#define SEED_D3F0 2u
#define SEED_MASK 4u
#define SEED_TOTAL (SEED_D494 + SEED_D638 + SEED_D8D7C + SEED_D3F0 + SEED_MASK)

int main(int argc, char **argv)
{
    const char *rom_path = argc > 1 ? argv[1] : "roms/stock/60E1D400.bin";
    char line[4096];
    uint8_t seed[SEED_TOTAL];

    if (load_rom(rom_path) != 0 || setup_memory() != 0) {
        return 2;
    }

    while (fgets(line, sizeof line, stdin)) {
        unsigned long chan;
        char blob[2 * SEED_TOTAL + 1];

        if (sscanf(line, "gs %lx %1548s", &chan, blob) == 2 &&
            parse_hex(blob, seed, SEED_TOTAL) == 0) {
            unsigned i;
            for (i = 0; i < SEED_D494; i++) {
                *(volatile uint8_t *)(uintptr_t)(0xFFFFD494u + i) = seed[i];
            }
            for (i = 0; i < SEED_D638; i++) {
                *(volatile uint8_t *)(uintptr_t)(0xFFFFD638u + i) = seed[SEED_D494 + i];
            }
            for (i = 0; i < SEED_D8D7C; i++) {
                *(volatile uint8_t *)(uintptr_t)(0xFFFF8D7Cu + i) = seed[SEED_D494 + SEED_D638 + i];
            }
            *(volatile uint8_t *)(uintptr_t)0xFFFFD3F0u = seed[SEED_D494 + SEED_D638 + SEED_D8D7C];
            *(volatile uint8_t *)(uintptr_t)0xFFFFD3F1u = seed[SEED_D494 + SEED_D638 + SEED_D8D7C + 1];
            for (i = 0; i < SEED_MASK; i++) {
                *(volatile uint8_t *)(uintptr_t)(0xFFFFD96Cu + i) =
                    seed[SEED_D494 + SEED_D638 + SEED_D8D7C + SEED_D3F0 + i];
            }

            printf("%02X\n", (unsigned)rx8_get_fault_status((uint16_t)chan));
        } else {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
    }
    return 0;
}

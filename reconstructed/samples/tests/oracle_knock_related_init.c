/* ============================================================================
 * oracle_knock_related_init.c  —  host rig for rx8_knock_related_init @0xC3C8
 * ============================================================================
 * Compile together with samples/src/rx8_knock_related_init.c (see
 * harness_knock_related_init.py) and pipe test vectors on stdin; one vector
 * per line:
 *
 *     knk <b0> <b1> ... <b66>        (67 space-separated hex bytes)
 *            -> <f328> <f32c> ... <f36c> <w37c> <w37e> <u324> <u384> <u385>
 *               <u386> <u389> <u38a> <s323> <s327> ... <s38b>
 *
 * The 67 pre-state bytes cover every RAM cell the function writes (19 cells,
 * byte groups in the order listed below) PLUS 13 store-boundary sentinel
 * bytes that must survive the call untouched:
 *
 *   bytes  0..43  : 11 x f32 pre-states (0xFFFFA328, A32C, A334, A338, A348,
 *                   A350, A354, A360, A364, A368, A36C) — 4 bytes each
 *   bytes 44..47  : 2 x u16 pre-states (0xFFFFA37C, A37E)
 *   bytes 48..53  : 6 x u8  pre-states (0xFFFFA324, A384, A385, A386, A389,
 *                   A38A)
 *   bytes 54..66  : 13 sentinel bytes (0xFFFFA323, A327, A330, A33C, A34C,
 *                   A358, A370, A37B, A380, A383, A387, A388, A38B)
 *
 * The output is the post-state of the same 19 cells (floats/words printed as
 * NUMERIC big-endian values so the little-endian host and the big-endian
 * SH-2E emulator agree bit-for-bit) followed by the 13 sentinel bytes.
 *
 * The ROM calibration block @0x7A164..0x7A1D4 is NOT shipped inline: the
 * page 0x0007A000 is MAP_FIXED-mapped at the same virtual address the ROM
 * fetches and seeded once from the ROM file (big-endian raw bytes; the
 * reconstructed source assembles the u16/f32 values byte-wise).  The literal
 * pool constants of the function itself (10.0 @0x0C4B0, 0xFF @0xC494) live
 * in the ROM code page and are only used on the emulator side; the C model
 * pins them as compile-time constants documented in the source header.
 * $RX8_ROM_PATH (set by the harness) points at roms/stock/60E1D400.bin.
 *
 * Pages mapped:
 *   0x0007A000  ROM calibration block @0x7A164..0x7A1D4
 *   0xFFFFA000  RAM cells 0xFFFFA323..0xFFFFA38B
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
#include <sys/mman.h>
#include <unistd.h>

#include "rx8_samples.h"

/* Prototype is NOT in rx8_samples.h (sample project convention: only the
 * verified "public" leaves are listed there); declared here for the rig. */
void rx8_knock_related_init(void);

#define ROM_CAL_PAGE   0x0007A000u
#define ROM_CAL_ADDR   0x0007A164u
#define ROM_CAL_LEN    0x70u          /* 0x7A164..0x7A1D3                    */
#define RAM_PAGE       0xFFFFA000u

/* The 67 vector addresses, in vector order (see header comment). */
static const uintptr_t VEC[67] = {
    0xFFFFA328u, 0xFFFFA329u, 0xFFFFA32Au, 0xFFFFA32Bu,
    0xFFFFA32Cu, 0xFFFFA32Du, 0xFFFFA32Eu, 0xFFFFA32Fu,
    0xFFFFA334u, 0xFFFFA335u, 0xFFFFA336u, 0xFFFFA337u,
    0xFFFFA338u, 0xFFFFA339u, 0xFFFFA33Au, 0xFFFFA33Bu,
    0xFFFFA348u, 0xFFFFA349u, 0xFFFFA34Au, 0xFFFFA34Bu,
    0xFFFFA350u, 0xFFFFA351u, 0xFFFFA352u, 0xFFFFA353u,
    0xFFFFA354u, 0xFFFFA355u, 0xFFFFA356u, 0xFFFFA357u,
    0xFFFFA360u, 0xFFFFA361u, 0xFFFFA362u, 0xFFFFA363u,
    0xFFFFA364u, 0xFFFFA365u, 0xFFFFA366u, 0xFFFFA367u,
    0xFFFFA368u, 0xFFFFA369u, 0xFFFFA36Au, 0xFFFFA36Bu,
    0xFFFFA36Cu, 0xFFFFA36Du, 0xFFFFA36Eu, 0xFFFFA36Fu,
    0xFFFFA37Cu, 0xFFFFA37Du,
    0xFFFFA37Eu, 0xFFFFA37Fu,
    0xFFFFA324u,
    0xFFFFA384u, 0xFFFFA385u, 0xFFFFA386u, 0xFFFFA389u, 0xFFFFA38Au,
    0xFFFFA323u, 0xFFFFA327u, 0xFFFFA330u, 0xFFFFA33Cu, 0xFFFFA34Cu,
    0xFFFFA358u, 0xFFFFA370u, 0xFFFFA37Bu, 0xFFFFA380u, 0xFFFFA383u,
    0xFFFFA387u, 0xFFFFA388u, 0xFFFFA38Bu,
};

/* Output cell base addresses, in output order (11 floats, 2 words, 6 bytes,
 * 13 sentinel bytes). */
static const uintptr_t OUT_FLT[11] = {
    0xFFFFA328u, 0xFFFFA32Cu, 0xFFFFA334u, 0xFFFFA338u, 0xFFFFA348u,
    0xFFFFA350u, 0xFFFFA354u, 0xFFFFA360u, 0xFFFFA364u, 0xFFFFA368u,
    0xFFFFA36Cu,
};
static const uintptr_t OUT_WRD[2] = { 0xFFFFA37Cu, 0xFFFFA37Eu };
static const uintptr_t OUT_BYT[6] = {
    0xFFFFA324u, 0xFFFFA384u, 0xFFFFA385u, 0xFFFFA386u, 0xFFFFA389u,
    0xFFFFA38Au,
};
static const uintptr_t OUT_SNT[13] = {
    0xFFFFA323u, 0xFFFFA327u, 0xFFFFA330u, 0xFFFFA33Cu, 0xFFFFA34Cu,
    0xFFFFA358u, 0xFFFFA370u, 0xFFFFA37Bu, 0xFFFFA380u, 0xFFFFA383u,
    0xFFFFA387u, 0xFFFFA388u, 0xFFFFA38Bu,
};

static void map_page(uintptr_t addr)
{
    long page = sysconf(_SC_PAGESIZE);
    uintptr_t base = addr & ~((uintptr_t)page - 1);
    void *p = mmap((void *)base, (size_t)page, PROT_READ | PROT_WRITE,
                   MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED, -1, 0);
    if (p == MAP_FAILED) {
        perror("mmap");
        exit(1);
    }
}

/* Numeric read-back.  The C function stores multi-byte values in HOST
 * (little-endian) order, while the emulator's RAM is big-endian; the
 * NUMERIC values agree when each side interprets its own in-memory byte
 * order (native here, big-endian assembly in the harness).  This mirrors
 * oracle_knock_function_init.c (memcpy for the float bits, native u16). */
static uint32_t rd_f32_bits(uintptr_t a)
{
    uint32_t bits;
    memcpy(&bits, (const void *)(uintptr_t)a, 4);
    return bits;
}

static void seed_rom_cal(int fd)
{
    /* Raw byte copy of the calibration block (big-endian in the file; the
     * reconstructed source assembles u16/f32 values byte-wise). */
    unsigned char buf[ROM_CAL_LEN];
    if (pread(fd, buf, ROM_CAL_LEN, ROM_CAL_ADDR) != (ssize_t)ROM_CAL_LEN) {
        perror("pread cal");
        exit(2);
    }
    for (size_t i = 0; i < ROM_CAL_LEN; i++) {
        *(volatile uint8_t *)(uintptr_t)(ROM_CAL_ADDR + i) = buf[i];
    }
}

int main(void)
{
    const char *rom_path = getenv("RX8_ROM_PATH");
    char line[1024];
    int romfd;

    if (!rom_path)
        rom_path = "../../../roms/stock/60E1D400.bin";
    romfd = open(rom_path, O_RDONLY);
    if (romfd < 0) {
        perror(rom_path);
        return 2;
    }

    /* ROM calibration page + RAM cell page. */
    map_page(ROM_CAL_PAGE);
    seed_rom_cal(romfd);
    map_page(RAM_PAGE);

    while (fgets(line, sizeof line, stdin)) {
        unsigned long v[67];
        if (sscanf(line,
                   "knk %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx "
                   "%lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx "
                   "%lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx "
                   "%lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx "
                   "%lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx",
                   &v[0], &v[1], &v[2], &v[3], &v[4], &v[5], &v[6], &v[7],
                   &v[8], &v[9], &v[10], &v[11], &v[12], &v[13], &v[14],
                   &v[15], &v[16], &v[17], &v[18], &v[19], &v[20], &v[21],
                   &v[22], &v[23], &v[24], &v[25], &v[26], &v[27], &v[28],
                   &v[29], &v[30], &v[31], &v[32], &v[33], &v[34], &v[35],
                   &v[36], &v[37], &v[38], &v[39], &v[40], &v[41], &v[42],
                   &v[43], &v[44], &v[45], &v[46], &v[47], &v[48], &v[49],
                   &v[50], &v[51], &v[52], &v[53], &v[54], &v[55], &v[56],
                   &v[57], &v[58], &v[59], &v[60], &v[61], &v[62], &v[63],
                   &v[64], &v[65], &v[66]) != 67) {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }

        /* Seed every pre-state byte. */
        for (int i = 0; i < 67; i++) {
            *(volatile uint8_t *)(uintptr_t)VEC[i] = (uint8_t)v[i];
        }

        rx8_knock_related_init();

        /* Post-state on a single line: 11 floats, 2 words, 6 bytes, 13
         * sentinels (newline only on the very last field). */
        for (int i = 0; i < 11; i++) {
            printf("%08X ", (unsigned)rd_f32_bits(OUT_FLT[i]));
        }
        for (int i = 0; i < 2; i++) {
            printf("%04X ",
                   (unsigned)*(const volatile uint16_t *)(uintptr_t)OUT_WRD[i]);
        }
        for (int i = 0; i < 6; i++) {
            printf("%02X ",
                   (unsigned)*(volatile uint8_t *)(uintptr_t)OUT_BYT[i]);
        }
        for (int i = 0; i < 12; i++) {
            printf("%02X ",
                   (unsigned)*(volatile uint8_t *)(uintptr_t)OUT_SNT[i]);
        }
        printf("%02X\n",
               (unsigned)*(volatile uint8_t *)(uintptr_t)OUT_SNT[12]);
    }
    return 0;
}

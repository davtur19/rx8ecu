/* ============================================================================
 * oracle_leading_trailing_spark_control_2100A.c  —  host rig for
 * rx8_leading_trailing_spark_control_2100A @0x2100A
 * ============================================================================
 * Compile together with samples/src/rx8_leading_trailing_spark_control_2100A.c
 * and pipe test vectors on stdin; one vector per line, whitespace-separated
 * hex tokens:
 *
 *     ltsp <coolant> <c6b4> <b1b2> <b1c7> <b1c9> <b1c4> <b1c2> <c600> <cce1>
 *          <cda0> <b19c> <b240> <lead0> <trail0>
 *                                          -> <b240> <lead> <trail>
 *
 *   coolant : raw IEEE-754 single-precision bits of RAM[0xFFFFAA10]
 *   c6b4    : raw IEEE-754 single-precision bits of RAM[0xFFFFC6B4]
 *   b1b2    : RAM16[0xFFFFB1B2]  gate word (pre-state)
 *   b1c7    : RAM8[0xFFFFB1C7]   gate flag (pre-state)
 *   b1c9    : RAM8[0xFFFFB1C9]   gate flag (pre-state)
 *   b1c4    : RAM8[0xFFFFB1C4]   gate flag (pre-state)
 *   b1c2    : RAM8[0xFFFFB1C2]   gate flag (pre-state)
 *   c600    : RAM8[0xFFFFC600]   engine-off flag
 *   cce1    : RAM8[0xFFFFCCE1]   enable gate
 *   cda0    : RAM8[0xFFFFCDA0]   AC/extra gate
 *   b19c    : RAM8[0xFFFFB19C]   allow-decay gate
 *   b240    : RAM8[0xFFFFB240]   cold/validity flag (pre-state)
 *   lead0   : raw IEEE-754 single-precision bits of RAM[0xFFFFB18C] (pre-state)
 *   trail0  : raw IEEE-754 single-precision bits of RAM[0xFFFFB188] (pre-state)
 *
 * Outputs are the three RAM side-effects the function leaves behind:
 *   b240    = cold/validity flag byte
 *   lead    = raw IEEE-754 bits of the leading  state float RAM[0xFFFFB18C]
 *   trail   = raw IEEE-754 bits of the trailing state float RAM[0xFFFFB188]
 *
 * The oracle re-implements only the *caller-side* set-up: it mmap()s the pages
 * backing the RAM cells AND the ROM calibration page, seeds every byte and
 * prints the three post-state cells.  It contains NO copy of the function
 * logic — that lives solely in the reconstructed source under test.
 *
 * The ROM calibration constants (u8 @0x71BD0, f32 @0x71C54/0x71C58/0x71C74/
 * 0x71C78/0x71C7C) are NOT shipped inline: the ROM page holding them is
 * MAP_FIXED-mapped at the same virtual address the ROM fetches and seeded once
 * from the ROM file with explicit big-endian assembly (the file is big-endian;
 * the host is little-endian, so a raw pointer read of a u16/f32 would
 * byte-swap — this is why the bytes are decoded to numeric values before being
 * stored).  $RX8_ROM_PATH (set by the harness) points at
 * roms/stock/60E1D400.bin.
 *
 * Pages mapped:
 *   0x00071000  ROM calibration block @0x71BD0..0x71C7C
 *   0xFFFFA000  RAM[0xFFFFAA10]  coolant
 *   0xFFFFB000  RAM[0xFFFFB18C/0xFFFFB188/0xFFFFB1B2/0xFFFFB1C2/0xFFFFB1C4/
 *               0xFFFFB1C7/0xFFFFB1C9/0xFFFFB19C/0xFFFFB240]
 *   0xFFFFC000  RAM[0xFFFFC600/0xFFFFC6B4/0xFFFFCCE1/0xFFFFCDA0]
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
#include <sys/mman.h>
#include <unistd.h>

#include "rx8_samples.h"

/* rx8_leading_trailing_spark_control_2100A is not (yet) in rx8_samples.h —
 * the shared header is owned by the samples build.  The reconstructed source
 * itself carries the authoritative definition (src/rx8_leading_trailing_
 * spark_control_2100A.c); this prototype mirrors it exactly. */
void rx8_leading_trailing_spark_control_2100A(void);

#define COOLANT_ADDR   0xFFFFAA10u   /* f32 coolant-temp input      */
#define C6B4_ADDR      0xFFFFC6B4u   /* f32 compare input           */
#define GATE_WORD_ADDR 0xFFFFB1B2u   /* u16 gate word               */
#define B1C7_ADDR      0xFFFFB1C7u   /* u8 gate flag                */
#define B1C9_ADDR      0xFFFFB1C9u   /* u8 gate flag                */
#define B1C4_ADDR      0xFFFFB1C4u   /* u8 gate flag                */
#define B1C2_ADDR      0xFFFFB1C2u   /* u8 gate flag                */
#define ENG_OFF_ADDR   0xFFFFC600u   /* u8 engine-off flag          */
#define ENABLE_ADDR    0xFFFFCCE1u   /* u8 enable gate              */
#define AC_GATE_ADDR   0xFFFFCDA0u   /* u8 AC/extra gate            */
#define ALLOW_DEC_ADDR 0xFFFFB19Cu   /* u8 allow-decay gate         */
#define COLD_FLAG_ADDR 0xFFFFB240u   /* u8 cold/validity flag (out) */
#define LEAD_ADDR      0xFFFFB18Cu   /* f32 leading state (out)     */
#define TRAIL_ADDR     0xFFFFB188u   /* f32 trailing state (out)    */

/* ROM calibration block (offsets == virtual addresses on this ROM image). */
#define ROM_CAL_BASE    0x71BD0u
#define ROM_CAL_ENABLE  0x71BD0u      /* u8  = 1       */
#define ROM_CAL_COLD_HI 0x71C54u      /* f32 = -40.0   */
#define ROM_CAL_HYST    0x71C58u      /* f32 = 3.0     */
#define ROM_CAL_DEC_L   0x71C74u      /* f32 = 0.0667  */
#define ROM_CAL_DEC_T   0x71C78u      /* f32 = 0.0667  */
#define ROM_CAL_1000    0x71C7Cu      /* f32 = 1000.0  */

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

/* Seed the ROM calibration page with the actual stock-60E1D400.bin constants.
 * The file is big-endian, so multi-byte values are assembled by hand and
 * stored as host-endian numeric values; the reconstructed source then reads
 * them back through the very same (mapped) virtual addresses the ROM fetches. */
static void seed_rom_cal(int fd)
{
    unsigned char b[4];
    uint32_t bits;
    float v;

    if (pread(fd, b, 1, ROM_CAL_ENABLE) != 1) { perror("pread 0x71BD0"); exit(2); }
    *(volatile uint8_t *)(uintptr_t)ROM_CAL_ENABLE = b[0];

    /* f32 -40.0 @0x71C54 */
    if (pread(fd, b, 4, ROM_CAL_COLD_HI) != 4) { perror("pread 0x71C54"); exit(2); }
    bits = ((uint32_t)b[0] << 24) | ((uint32_t)b[1] << 16)
         | ((uint32_t)b[2] << 8) | (uint32_t)b[3];
    memcpy(&v, &bits, sizeof v);
    *(volatile float *)(uintptr_t)ROM_CAL_COLD_HI = v;

    /* f32 3.0 @0x71C58 */
    if (pread(fd, b, 4, ROM_CAL_HYST) != 4) { perror("pread 0x71C58"); exit(2); }
    bits = ((uint32_t)b[0] << 24) | ((uint32_t)b[1] << 16)
         | ((uint32_t)b[2] << 8) | (uint32_t)b[3];
    memcpy(&v, &bits, sizeof v);
    *(volatile float *)(uintptr_t)ROM_CAL_HYST = v;

    /* f32 0.0667 @0x71C74 and @0x71C78 (identical values) */
    if (pread(fd, b, 4, ROM_CAL_DEC_L) != 4) { perror("pread 0x71C74"); exit(2); }
    bits = ((uint32_t)b[0] << 24) | ((uint32_t)b[1] << 16)
         | ((uint32_t)b[2] << 8) | (uint32_t)b[3];
    memcpy(&v, &bits, sizeof v);
    *(volatile float *)(uintptr_t)ROM_CAL_DEC_L = v;
    if (pread(fd, b, 4, ROM_CAL_DEC_T) != 4) { perror("pread 0x71C78"); exit(2); }
    bits = ((uint32_t)b[0] << 24) | ((uint32_t)b[1] << 16)
         | ((uint32_t)b[2] << 8) | (uint32_t)b[3];
    memcpy(&v, &bits, sizeof v);
    *(volatile float *)(uintptr_t)ROM_CAL_DEC_T = v;

    /* f32 1000.0 @0x71C7C */
    if (pread(fd, b, 4, ROM_CAL_1000) != 4) { perror("pread 0x71C7C"); exit(2); }
    bits = ((uint32_t)b[0] << 24) | ((uint32_t)b[1] << 16)
         | ((uint32_t)b[2] << 8) | (uint32_t)b[3];
    memcpy(&v, &bits, sizeof v);
    *(volatile float *)(uintptr_t)ROM_CAL_1000 = v;
}

int main(void)
{
    const char *rom_path = getenv("RX8_ROM_PATH");
    char line[256];
    int romfd;

    if (!rom_path)
        rom_path = "../../../roms/stock/60E1D400.bin";
    romfd = open(rom_path, O_RDONLY);
    if (romfd < 0) {
        perror(rom_path);
        return 2;
    }

    map_page(ROM_CAL_BASE);
    seed_rom_cal(romfd);
    close(romfd);
    map_page(COOLANT_ADDR);
    map_page(GATE_WORD_ADDR);
    map_page(ENG_OFF_ADDR);

    while (fgets(line, sizeof line, stdin)) {
        unsigned long coolant, c6b4, b1b2, b1c7, b1c9, b1c4, b1c2;
        unsigned long c600, cce1, cda0, b19c, b240, lead0, trail0;

        if (sscanf(line,
                   "ltsp %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx",
                   &coolant, &c6b4, &b1b2, &b1c7, &b1c9, &b1c4, &b1c2,
                   &c600, &cce1, &cda0, &b19c, &b240, &lead0, &trail0)
            != 14) {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }

        /* Seed the f32 inputs / pre-states as raw bits (the reconstructed
         * source reads them back through the same addresses as float). */
        *(volatile uint32_t *)(uintptr_t)COOLANT_ADDR   = (uint32_t)coolant;
        *(volatile uint32_t *)(uintptr_t)C6B4_ADDR      = (uint32_t)c6b4;
        *(volatile uint32_t *)(uintptr_t)LEAD_ADDR      = (uint32_t)lead0;
        *(volatile uint32_t *)(uintptr_t)TRAIL_ADDR     = (uint32_t)trail0;

        /* Seed the gate bytes / words (byte-exact numeric values). */
        *(volatile uint16_t *)(uintptr_t)GATE_WORD_ADDR = (uint16_t)b1b2;
        *(volatile uint8_t  *)(uintptr_t)B1C7_ADDR      = (uint8_t)b1c7;
        *(volatile uint8_t  *)(uintptr_t)B1C9_ADDR      = (uint8_t)b1c9;
        *(volatile uint8_t  *)(uintptr_t)B1C4_ADDR      = (uint8_t)b1c4;
        *(volatile uint8_t  *)(uintptr_t)B1C2_ADDR      = (uint8_t)b1c2;
        *(volatile uint8_t  *)(uintptr_t)ENG_OFF_ADDR   = (uint8_t)c600;
        *(volatile uint8_t  *)(uintptr_t)ENABLE_ADDR    = (uint8_t)cce1;
        *(volatile uint8_t  *)(uintptr_t)AC_GATE_ADDR   = (uint8_t)cda0;
        *(volatile uint8_t  *)(uintptr_t)ALLOW_DEC_ADDR = (uint8_t)b19c;
        *(volatile uint8_t  *)(uintptr_t)COLD_FLAG_ADDR = (uint8_t)b240;

        rx8_leading_trailing_spark_control_2100A();

        printf("%02X %08X %08X\n",
               (unsigned)*(volatile uint8_t  *)(uintptr_t)COLD_FLAG_ADDR,
               (unsigned)*(volatile uint32_t *)(uintptr_t)LEAD_ADDR,
               (unsigned)*(volatile uint32_t *)(uintptr_t)TRAIL_ADDR);
    }
    return 0;
}

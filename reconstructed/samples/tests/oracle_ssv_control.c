/* ============================================================================
 * oracle_ssv_control.c  —  host rig for rx8_ssv_control @0x225C8
 * ============================================================================
 * Compile together with samples/src/rx8_ssv_control.c and pipe test vectors
 * on stdin; one vector per line, whitespace-separated hex tokens:
 *
 *     ssv <t> <mode> <prevm> <cmd0> <cnt0> <status> <mask> <st> <magic> <src>
 *         <csm> <inp> <latch> <cell> <f754>
 *                                       -> <B324> <B322> <B320> <F754> <B325>
 *                                          <D355> <D387> <CELL>
 *
 *   t      : raw IEEE-754 single-precision bits of the band temperature
 *            (RAM32[0xFFFFAA10]) — shipped as bits so float->hex round-trips
 *   mode   : RAM8[0xFFFFAAE0]
 *   prevm  : RAM8[0xFFFFB325]  pre-state (previous mode)
 *   cmd0   : RAM8[0xFFFFB324]  pre-state (SSV command)
 *   cnt0   : RAM16[0xFFFFB322] pre-state (transition counter)
 *   status : RAM8[0xFFFFBF39]
 *   mask   : SM sensor mask  RAM8[0x6021C]
 *   st     : SM state byte   RAM8[0xFFFFD355]
 *   magic  : SM magic word   RAM16[0xFFFFD350] (== 0xE926)
 *   src    : SM source word  RAM16[0xFFFFD352]
 *   csm    : SM count byte   RAM8[0xFFFFD354]
 *   inp    : SM input byte   RAM8[0xFFFFD3A8]
 *   latch  : SM latch byte   RAM8[0xFFFFD387]
 *   cell   : SM output byte  RAM8[0xFFFFD400] (behind the stored output ptr)
 *   f754   : RAM16[0xFFFFF754] pre-state (status word)
 *
 * The oracle re-implements only the *caller-side* set-up: it mmap()s the
 * pages backing the RAM cells AND the two ROM calibration pages, seeds every
 * byte and prints the eight post-state cells.  It contains NO copy of the
 * function logic — that lives solely in the reconstructed source under test.
 *
 * The calibration constants are NOT shipped inline: the ROM pages holding
 * the SSV cal block (0x72F70..0x72F74) and the hysteresis f32 @0x226D4 are
 * MAP_FIXED-mapped at the same virtual addresses the ROM uses, and seeded
 * once from the ROM file with explicit big-endian assembly (the file is
 * big-endian; the host is little-endian, so a raw pointer read of a u16/f32
 * would byte-swap — this is why the bytes are decoded to numeric values
 * before being stored).  The values are validated by the harness against
 * the ROM.  $RX8_ROM_PATH (set by the harness) points at
 * roms/stock/60E1D400.bin.
 *
 * Pages mapped:
 *   0x00022000  ROM hysteresis f32 @0x226D4
 *   0x00072000  ROM SSV cal block @0x72F70..0x72F74
 *   0x00602000  flash-shadow SM descriptor (mask @0x6021C, ptr @0x60220)
 *   0xFFFFA000  RAM[0xFFFFAA10/0xFFFFAAE0]
 *   0xFFFFB000  RAM[0xFFFFB320..0xFFFFB325], RAM[0xFFFFBF39]
 *   0xFFFFD000  RAM[0xFFFFD350..0xFFFFD400] (SM cells + output cell)
 *   0xFFFFF000  RAM[0xFFFFF754] (status word)
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
#include <sys/mman.h>
#include <unistd.h>

#include "rx8_samples.h"

/* rx8_ssv_control is not (yet) in rx8_samples.h — the shared header is owned
 * by the samples build.  The reconstructed source itself carries the
 * authoritative definition (src/rx8_ssv_control.c); this prototype mirrors
 * it exactly. */
void rx8_ssv_control(void);

#define SSV_TEMP_ADDR   0xFFFFAA10u   /* f32 temperature                       */
#define SSV_MODE_ADDR   0xFFFFAAE0u   /* u8 mode byte                          */
#define SSV_CMD_ADDR    0xFFFFB324u   /* u8 SSV command                        */
#define SSV_CNT_ADDR    0xFFFFB322u   /* u16 transition counter                */
#define SSV_OUT_ADDR    0xFFFFB320u   /* u8 SM result byte                     */
#define SSV_PREV_ADDR   0xFFFFB325u   /* u8 previous mode                      */
#define SSV_STATUS_ADDR 0xFFFFBF39u   /* u8 status byte                        */
#define F754_ADDR       0xFFFFF754u   /* u16 status word                       */
#define SM_MASK_ADDR    0x6021Cu      /* u8 sensor mask                        */
#define SM_PTR_ADDR     0x60220u      /* u32 stored output pointer             */
#define ST_ADDR         0xFFFFD355u   /* u8 SM state byte                      */
#define MAGIC_ADDR      0xFFFFD350u   /* u16 SM magic word                     */
#define SRC_ADDR        0xFFFFD352u   /* u16 SM source word                    */
#define CNT_ADDR        0xFFFFD354u   /* u8 SM count byte                      */
#define INP_ADDR        0xFFFFD3A8u   /* u8 SM input byte                      */
#define LATCH_ADDR      0xFFFFD387u   /* u8 SM latch byte                      */
#define PTR_CELL        0xFFFFD400u   /* u8 SM output byte (ptr target)        */

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

/* Seed the two ROM-calibration pages with the actual stock-60E1D400.bin
 * constants.  The file is big-endian, so multi-byte values are assembled by
 * hand and stored as host-endian numeric values; the reconstructed source
 * then reads them back through the very same (mapped) virtual addresses the
 * ROM fetches.  Offsets here == virtual addresses on this ROM image. */
static void seed_rom_cal(int fd)
{
    unsigned char b[4];
    uint32_t bits;
    float v;

    /* hysteresis delta f32 @0x226D4 = -3.0 */
    if (pread(fd, b, 4, 0x226D4) != 4) { perror("pread 0x226D4"); exit(2); }
    bits = ((uint32_t)b[0] << 24) | ((uint32_t)b[1] << 16)
         | ((uint32_t)b[2] << 8) | (uint32_t)b[3];
    memcpy(&v, &bits, sizeof v);
    *(volatile float *)(uintptr_t)0x226D4u = v;

    /* cal flag u8 @0x72F70 = 0; reload u16 @0x72F72 = 188 */
    if (pread(fd, b, 1, 0x72F70) != 1) { perror("pread 0x72F70"); exit(2); }
    *(volatile uint8_t *)(uintptr_t)0x72F70u = b[0];
    if (pread(fd, b, 2, 0x72F72) != 2) { perror("pread 0x72F72"); exit(2); }
    *(volatile uint16_t *)(uintptr_t)0x72F72u =
        (uint16_t)((b[0] << 8) | b[1]);

    /* on-threshold f32 @0x72F74 = 200.0 */
    if (pread(fd, b, 4, 0x72F74) != 4) { perror("pread 0x72F74"); exit(2); }
    bits = ((uint32_t)b[0] << 24) | ((uint32_t)b[1] << 16)
         | ((uint32_t)b[2] << 8) | (uint32_t)b[3];
    memcpy(&v, &bits, sizeof v);
    *(volatile float *)(uintptr_t)0x72F74u = v;
}

int main(void)
{
    const char *rom_path = getenv("RX8_ROM_PATH");
    char line[512];
    int romfd;

    if (!rom_path)
        rom_path = "../../../roms/stock/60E1D400.bin";
    romfd = open(rom_path, O_RDONLY);
    if (romfd < 0) {
        perror(rom_path);
        return 2;
    }

    /* ROM calibration pages (anonymous, seeded from the file — see above). */
    map_page(0x226D4u);
    map_page(0x72F70u);
    seed_rom_cal(romfd);
    /* RAM / descriptor pages. */
    map_page(0x60200u);
    map_page(SSV_TEMP_ADDR);
    map_page(SSV_CMD_ADDR);
    map_page(ST_ADDR);
    map_page(F754_ADDR);

    while (fgets(line, sizeof line, stdin)) {
        unsigned long t, mode, prevm, cmd0, cnt0, status;
        unsigned long mask, st, magic, src, csm, inp, latch, cell, f754;

        if (sscanf(line,
                   "ssv %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx",
                   &t, &mode, &prevm, &cmd0, &cnt0, &status,
                   &mask, &st, &magic, &src, &csm, &inp, &latch, &cell, &f754)
            != 15) {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }

        /* Seed the RAM pre-states (byte-exact numeric values). */
        *(volatile uint32_t *)(uintptr_t)SSV_TEMP_ADDR   = (uint32_t)t;
        *(volatile uint8_t  *)(uintptr_t)SSV_MODE_ADDR   = (uint8_t)mode;
        *(volatile uint8_t  *)(uintptr_t)SSV_PREV_ADDR   = (uint8_t)prevm;
        *(volatile uint8_t  *)(uintptr_t)SSV_CMD_ADDR    = (uint8_t)cmd0;
        *(volatile uint16_t *)(uintptr_t)SSV_CNT_ADDR    = (uint16_t)cnt0;
        *(volatile uint8_t  *)(uintptr_t)SSV_STATUS_ADDR = (uint8_t)status;
        *(volatile uint16_t *)(uintptr_t)F754_ADDR       = (uint16_t)f754;

        /* Seed the SM descriptor + cells.  The stored output pointer is fixed
         * to PTR_CELL on both sides so *ptr lands in a comparable cell. */
        *(volatile uint8_t  *)(uintptr_t)SM_MASK_ADDR    = (uint8_t)mask;
        *(volatile uint32_t *)(uintptr_t)SM_PTR_ADDR     = (uint32_t)PTR_CELL;
        *(volatile uint8_t  *)(uintptr_t)ST_ADDR         = (uint8_t)st;
        *(volatile uint16_t *)(uintptr_t)MAGIC_ADDR      = (uint16_t)magic;
        *(volatile uint16_t *)(uintptr_t)SRC_ADDR        = (uint16_t)src;
        *(volatile uint8_t  *)(uintptr_t)CNT_ADDR        = (uint8_t)csm;
        *(volatile uint8_t  *)(uintptr_t)INP_ADDR        = (uint8_t)inp;
        *(volatile uint8_t  *)(uintptr_t)LATCH_ADDR      = (uint8_t)latch;
        *(volatile uint8_t  *)(uintptr_t)PTR_CELL        = (uint8_t)cell;

        rx8_ssv_control();

        printf("%02X %04X %02X %04X %02X %02X %02X %02X\n",
               *(volatile uint8_t  *)(uintptr_t)SSV_CMD_ADDR,
               *(volatile uint16_t *)(uintptr_t)SSV_CNT_ADDR,
               *(volatile uint8_t  *)(uintptr_t)SSV_OUT_ADDR,
               *(volatile uint16_t *)(uintptr_t)F754_ADDR,
               *(volatile uint8_t  *)(uintptr_t)SSV_PREV_ADDR,
               *(volatile uint8_t  *)(uintptr_t)ST_ADDR,
               *(volatile uint8_t  *)(uintptr_t)LATCH_ADDR,
               *(volatile uint8_t  *)(uintptr_t)PTR_CELL);
    }
    return 0;
}

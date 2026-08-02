/* ============================================================================
 * oracle_battery_voltage_monitor.c  — host rig for rx8_battery_voltage_monitor
 *                                      @0x26766
 * ============================================================================
 * Compile together with samples/src/rx8_battery_voltage_monitor.c and pipe
 * test vectors on stdin; one vector per line, whitespace-separated hex tokens:
 *
 *     bvm <bat> <tps> <ov0> <cmp0> <intermed> <ref> <cntA0> <cntB0>
 *                                       ->  <ov> <cmp> <cntA> <cntB>
 *
 *   bat       : raw IEEE-754 single-precision bits of RAM32[0xFFFFB600]
 *   tps       : RAM8[0xFFFFA428]
 *   ov0       : RAM8[0xFFFFB6B6]  pre-state (always overwritten by block 1)
 *   cmp0      : RAM16[0xFFFFB67A] pre-state (compensation word)
 *   intermed  : raw f32 bits of   RAM32[0xFFFFB6C4]
 *   ref       : raw f32 bits of   RAM32[0xFFFFB6C8]
 *   cntA0     : RAM16[0xFFFFB6AC] pre-state (counter A)
 *   cntB0     : RAM16[0xFFFFB6AE] pre-state (counter B)
 *
 * Only the caller-side rig is re-implemented: it mmap()s the pages backing the
 * RAM cells AND the ROM calibration page, seeds every byte and prints the four
 * post-state cells.  It contains NO copy of the function logic — that lives
 * solely in the reconstructed source under test.
 *
 * The calibration constants are NOT shipped inline: the ROM page holding the
 * cal block (0x751A2..0x751C4) is MAP_FIXED-mapped at the same virtual
 * addresses the ROM uses and seeded once from the ROM file with explicit
 * big-endian assembly (the file is big-endian; the host is little-endian, so a
 * raw pointer read of a u16/f32 would byte-swap).  $RX8_ROM_PATH (set by the
 * harness) points at roms/stock/60E1D400.bin, offset == virtual address.
 *
 * Pages mapped:
 *   0x00075000  ROM calibration block @0x751A2..0x751C4
 *   0xFFFFA000  RAM8[0xFFFFA428] (TPS / engine-state byte)
 *   0xFFFFB000  RAM32[0xFFFFB600], RAM32[0xFFFFB6C4/0xFFFFB6C8],
 *               RAM16[0xFFFFB67A], RAM8[0xFFFFB6B6],
 *               RAM16[0xFFFFB6AC] & RAM16[0xFFFFB6AE]
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
#include <sys/mman.h>
#include <unistd.h>

#include "rx8_samples.h"

/* rx8_battery_voltage_monitor is not (yet) declared in rx8_samples.h — the
 * shared header is owned by the samples build.  The reconstructed source
 * itself carries the authoritative definition (src/...c); this prototype
 * mirrors it exactly. */
void rx8_battery_voltage_monitor(void);

#define BAT_ADDR      0xFFFFB600u   /* f32 battery voltage (V) */
#define TPS_ADDR      0xFFFFA428u   /* u8  TPS / engine-state byte */
#define OV_FLAG_ADDR  0xFFFFB6B6u   /* u8  charging-fault byte */
#define CMP_ADDR      0xFFFFB67Au   /* u16 compensation word */
#define INTERMED_ADDR 0xFFFFB6C4u   /* f32 ADC-processing intermediate */
#define REF_ADDR      0xFFFFB6C8u   /* f32 reference voltage */
#define CNT_A_ADDR    0xFFFFB6ACu   /* u16 counter A */
#define CNT_B_ADDR    0xFFFFB6AEu   /* u16 counter B */

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

/* Seed the ROM calibration page with the actual stock-60E1D400.bin constants
 * (big-endian, so multi-byte values are assembled by hand). */
static void seed_rom_cal(int fd)
{
    unsigned char b[4];
    uint32_t bits;
    float v;

#define PREAD_N(off, n) (pread(fd, b, n, off) == n)

    /* u16 @0x751A2 = 63 (counter-A threshold) */
    if (!PREAD_N(0x751A2, 2)) { perror("pread 0x751A2"); exit(2); }
    *(volatile uint16_t *)(uintptr_t)0x751A2u =
        (uint16_t)((b[0] << 8) | b[1]);
    /* u16 @0x751A4 = 63 (counter-B threshold) */
    if (!PREAD_N(0x751A4, 2)) { perror("pread 0x751A4"); exit(2); }
    *(volatile uint16_t *)(uintptr_t)0x751A4u =
        (uint16_t)((b[0] << 8) | b[1]);
    /* u16 @0x751A8 = 312 (compensation load value) */
    if (!PREAD_N(0x751A8, 2)) { perror("pread 0x751A8"); exit(2); }
    *(volatile uint16_t *)(uintptr_t)0x751A8u =
        (uint16_t)((b[0] << 8) | b[1]);
    /* f32 @0x751B0 = 10.0  (CAL_BAT_HI)  /  f32 @0x751B4 = 1.0 (CAL_BAT_LO,
     * dead in the reconstructed body but kept to mirror the ROM pool) */
    if (!PREAD_N(0x751B0, 4)) { perror("pread 0x751B0"); exit(2); }
    bits = ((uint32_t)b[0] << 24) | ((uint32_t)b[1] << 16)
         | ((uint32_t)b[2] << 8) | (uint32_t)b[3];
    memcpy(&v, &bits, sizeof v);
    *(volatile float *)(uintptr_t)0x751B0u = v;
    if (!PREAD_N(0x751B4, 4)) { perror("pread 0x751B4"); exit(2); }
    bits = ((uint32_t)b[0] << 24) | ((uint32_t)b[1] << 16)
         | ((uint32_t)b[2] << 8) | (uint32_t)b[3];
    memcpy(&v, &bits, sizeof v);
    *(volatile float *)(uintptr_t)0x751B4u = v;
    /* f32 @0x751C0 = 16.973 (CAL_CRIT)  /  f32 @0x751C4 = 10.938 (CAL_UW) */
    if (!PREAD_N(0x751C0, 4)) { perror("pread 0x751C0"); exit(2); }
    bits = ((uint32_t)b[0] << 24) | ((uint32_t)b[1] << 16)
         | ((uint32_t)b[2] << 8) | (uint32_t)b[3];
    memcpy(&v, &bits, sizeof v);
    *(volatile float *)(uintptr_t)0x751C0u = v;
    if (!PREAD_N(0x751C4, 4)) { perror("pread 0x751C4"); exit(2); }
    bits = ((uint32_t)b[0] << 24) | ((uint32_t)b[1] << 16)
         | ((uint32_t)b[2] << 8) | (uint32_t)b[3];
    memcpy(&v, &bits, sizeof v);
    *(volatile float *)(uintptr_t)0x751C4u = v;
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

    /* ROM calibration page + RAM pages. */
    map_page(0x751A2u);
    seed_rom_cal(romfd);
    map_page(TPS_ADDR);
    map_page(BAT_ADDR);

    while (fgets(line, sizeof line, stdin)) {
        unsigned long bat, tps, ov0, cmp0, intermed, ref, cntA0, cntB0;

        if (sscanf(line,
                   "bvm %lx %lx %lx %lx %lx %lx %lx %lx",
                   &bat, &tps, &ov0, &cmp0, &intermed, &ref, &cntA0, &cntB0)
            != 8) {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }

        /* Seed RAM pre-states (byte-exact numeric values / raw float bits). */
        *(volatile uint32_t *)(uintptr_t)BAT_ADDR      = (uint32_t)bat;
        *(volatile uint8_t  *)(uintptr_t)TPS_ADDR      = (uint8_t)tps;
        *(volatile uint8_t  *)(uintptr_t)OV_FLAG_ADDR       = (uint8_t)ov0;
        *(volatile uint16_t *)(uintptr_t)CMP_ADDR      = (uint16_t)cmp0;
        *(volatile uint32_t *)(uintptr_t)INTERMED_ADDR = (uint32_t)intermed;
        *(volatile uint32_t *)(uintptr_t)REF_ADDR      = (uint32_t)ref;
        *(volatile uint16_t *)(uintptr_t)CNT_A_ADDR    = (uint16_t)cntA0;
        *(volatile uint16_t *)(uintptr_t)CNT_B_ADDR    = (uint16_t)cntB0;

        rx8_battery_voltage_monitor();

        printf("%02X %04X %04X %04X\n",
               *(volatile uint8_t  *)(uintptr_t)OV_FLAG_ADDR,
               *(volatile uint16_t *)(uintptr_t)CMP_ADDR,
               *(volatile uint16_t *)(uintptr_t)CNT_A_ADDR,
               *(volatile uint16_t *)(uintptr_t)CNT_B_ADDR);
    }
    return 0;
}
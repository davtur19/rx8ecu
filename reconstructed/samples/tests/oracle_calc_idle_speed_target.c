/* ============================================================================
 * oracle_calc_idle_speed_target.c  —  host rig for
 * rx8_calc_idle_speed_target
 * ============================================================================
 * Compile together with src/rx8_calc_idle_speed_target.c and pipe test
 * vectors on stdin; one vector per line, whitespace-separated hex tokens
 * (floats shipped as raw IEEE-754 single-precision bits so the round trip
 * through the pipe is exact on both sides):
 *
 *     ids <rpm> <ra> <rb> <eng> <cl> <cm> <ca> <inc> <fa> <fb> <ad> <v1> <v2>
 *                                             -> <tgt> <inc'> <ad'> <fa'> <fb'>
 *
 *   rpm           : u16  RAM[0xFFFFA424] engine speed (raw)
 *   ra, rb        : u8   RAM[0xFFFFA444 / 0xFFFFA445] rotor status
 *   eng           : u8   RAM[0xFFFFC600] engine-running flag
 *   cl            : u8   RAM[0xFFFFAADA] closed-loop flag
 *   cm, ca        : f32  RAM[0xFFFFC12C / 0xFFFFC128] coolant temps (main/alt)
 *   inc           : u8   RAM[0xFFFFA68F] increment-flag pre-state
 *   fa, fb        : u8   RAM[0xFFFFA6A9 / 0xFFFFA6AA] state-flag pre-states
 *   ad            : f32  RAM[0xFFFFA680] adaptive accumulator pre-state
 *   v1, v2        : f32  RAM[0xFFFFA670 / 0xFFFFA674] adaptive references
 *
 * The oracle re-implements only the *caller-side* set-up: it mmap()s the pages
 * backing the RAM cells AND the ROM calibration pages, seeds every byte and
 * prints the five post-state cells (idle target f32 bits, increment flag u8,
 * adaptive f32 bits, the two persisted state flags).  It contains NO copy of
 * the function logic — that lives solely in the reconstructed source under
 * test (including the two inlined ROM leaves 0x3ED0C and 0x23E4).
 *
 * Pages mapped (all above mmap_min_addr on this host):
 *   0x0003E000  ROM cal page (0x3EF78 / 0x3EF7C sensor_range_check constants)
 *   0x00072000  ROM cal page (0x72BBB inc value, 0x72BC0 idle RPM threshold)
 *   0xFFFFA000  RAM[0xFFFFA424..0xFFFFAADA] (all cells of this function)
 *   0xFFFFC000  RAM[0xFFFFC128 / 0xFFFFC12C coolant, 0xFFFFC600 engine flag]
 * ==========================================================================*/
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>
#include <fcntl.h>

/* 0x12F5E — see src/rx8_calc_idle_speed_target.c. */
void rx8_calc_idle_speed_target(void);

/* ROM file backing the calibration pages (overridable; default = repo stock
 * ROM that the harness loads into the emulator). */
#ifndef ROM_PATH
#define ROM_PATH "/home/davide/ailocal/rx8ecu/roms/stock/60E1D400.bin"
#endif

#define RAM_RA_ADDR   0xFFFFA444u   /* u8   rotor A status        */
#define RAM_RB_ADDR   0xFFFFA445u   /* u8   rotor B status        */
#define RAM_RPM_ADDR  0xFFFFA424u   /* u16  engine RPM raw        */
#define RAM_ENG_ADDR  0xFFFFC600u   /* u8   engine-running flag   */
#define RAM_CL_ADDR   0xFFFFAADAu   /* u8   closed-loop flag      */
#define RAM_CM_ADDR   0xFFFFC12Cu   /* f32  coolant temp (main)   */
#define RAM_CA_ADDR   0xFFFFC128u   /* f32  coolant temp (alt)    */
#define RAM_TGT_ADDR  0xFFFFA678u   /* f32  idle target (result)  */
#define RAM_INC_ADDR  0xFFFFA68Fu   /* u8   increment flag        */
#define RAM_FA_ADDR   0xFFFFA6A9u   /* u8   rotor A state flag    */
#define RAM_FB_ADDR   0xFFFFA6AAu   /* u8   rotor B state flag    */
#define RAM_AD_ADDR   0xFFFFA680u   /* f32  adaptive accumulator  */
#define RAM_V1_ADDR   0xFFFFA670u   /* f32  adaptive reference 1  */
#define RAM_V2_ADDR   0xFFFFA674u   /* f32  adaptive reference 2  */

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

static void map_rom_page(int fd, uintptr_t addr)
{
    long page = sysconf(_SC_PAGESIZE);
    uintptr_t base = addr & ~((uintptr_t)page - 1);
    void *p = mmap((void *)base, (size_t)page, PROT_READ,
                   MAP_PRIVATE | MAP_FIXED, fd, (off_t)base);
    if (p == MAP_FAILED) {
        perror("mmap(rom)");
        exit(1);
    }
}

static void seed_f(float *cell, unsigned long bits)
{
    uint32_t u = (uint32_t)bits;
    memcpy(cell, &u, sizeof u);
}

int main(void)
{
    char line[256];
    int fd;

    /* RAM: pages 0xFFFFA000 and 0xFFFFC000 cover every cell of the function. */
    map_page(RAM_RA_ADDR);
    map_page(RAM_ENG_ADDR);

    /* ROM: calibration pages for the idle gate and the sensor_range_check
     * range constants — mapped straight from the stock bin so both sides read
     * byte-identical values. */
    fd = open(ROM_PATH, O_RDONLY);
    if (fd < 0) {
        perror(ROM_PATH);
        return 2;
    }
    map_rom_page(fd, 0x3E000u);
    map_rom_page(fd, 0x72000u);
    close(fd);

    while (fgets(line, sizeof line, stdin)) {
        unsigned long rpm, ra, rb, eng, cl, cm, ca, inc, fa, fb, ad, v1, v2;

        if (sscanf(line,
                   "ids %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx",
                   &rpm, &ra, &rb, &eng, &cl, &cm, &ca,
                   &inc, &fa, &fb, &ad, &v1, &v2) != 13) {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }

        /* Seed the input RAM cells (floats from raw bits, endian-neutral). */
        *(volatile uint16_t *)(uintptr_t)RAM_RPM_ADDR = (uint16_t)rpm;
        *(volatile uint8_t  *)(uintptr_t)RAM_RA_ADDR  = (uint8_t)ra;
        *(volatile uint8_t  *)(uintptr_t)RAM_RB_ADDR  = (uint8_t)rb;
        *(volatile uint8_t  *)(uintptr_t)RAM_ENG_ADDR = (uint8_t)eng;
        *(volatile uint8_t  *)(uintptr_t)RAM_CL_ADDR  = (uint8_t)cl;
        seed_f((float *)(uintptr_t)RAM_CM_ADDR, cm);
        seed_f((float *)(uintptr_t)RAM_CA_ADDR, ca);
        *(volatile uint8_t  *)(uintptr_t)RAM_INC_ADDR = (uint8_t)inc;
        *(volatile uint8_t  *)(uintptr_t)RAM_FA_ADDR  = (uint8_t)fa;
        *(volatile uint8_t  *)(uintptr_t)RAM_FB_ADDR  = (uint8_t)fb;
        seed_f((float *)(uintptr_t)RAM_AD_ADDR, ad);
        seed_f((float *)(uintptr_t)RAM_V1_ADDR, v1);
        seed_f((float *)(uintptr_t)RAM_V2_ADDR, v2);

        rx8_calc_idle_speed_target();

        {
            float tgt = *(volatile float *)(uintptr_t)RAM_TGT_ADDR;
            float acc = *(volatile float *)(uintptr_t)RAM_AD_ADDR;
            uint32_t ut, ua;
            memcpy(&ut, &tgt, sizeof ut);
            memcpy(&ua, &acc, sizeof ua);
            printf("%08X %02X %08X %02X %02X\n",
                   (unsigned)ut,
                   (unsigned)*(volatile uint8_t *)(uintptr_t)RAM_INC_ADDR,
                   (unsigned)ua,
                   (unsigned)*(volatile uint8_t *)(uintptr_t)RAM_FA_ADDR,
                   (unsigned)*(volatile uint8_t *)(uintptr_t)RAM_FB_ADDR);
        }
    }
    return 0;
}

/* ============================================================================
 * oracle_calc_adaptive_fuel_trim.c  —  host rig for
 * rx8_calc_adaptive_fuel_trim
 * ============================================================================
 * Compile together with src/rx8_calc_adaptive_fuel_trim.c and pipe test
 * vectors on stdin; one vector per line, whitespace-separated hex tokens
 * (floats shipped as raw IEEE-754 single-precision bits so the round trip
 * through the pipe is exact on both sides):
 *
 *     atr <rpm> <coolant> <lam> <en> <sel> <flag> <cl> <coolst> <rpmraw> <prev>
 *                                             -> <error> <trim> <status> <final>
 *
 *   rpm, coolant, lam : f32 RAM[0xFFFFB5B8 / 0xFFFFC12C / 0xFFFFB5C4]
 *   en                : u8  RAM[0xFFFFB5A4] adaptive-trim enable
 *   sel               : u8  RAM[0xFFFFB5AC] table select (enable == 0 path)
 *   flag              : u8  RAM[0xFFFFB5AA] table select (enable != 0 path)
 *   cl                : u8  RAM[0xFFFFAADA] closed-loop flag
 *   coolst            : f32 RAM[0xFFFFC084] coolant status
 *   rpmraw            : u16 RAM[0xFFFFA424] engine RPM raw
 *   prev              : u8  RAM[0xFFFFA730] status pre-state (hysteresis)
 *
 * The oracle re-implements only the *caller-side* set-up: it mmap()s the pages
 * backing the RAM cells AND the ROM calibration pages straight from the stock
 * bin (pointed at by $RX8_ROM_PATH), seeds every input byte and prints the
 * four post-state cells.  It contains NO copy of the function logic — that
 * lives solely in the reconstructed source under test (including the inlined
 * ROM leaves 0x2068 table1D_lookup and 0x2404 clamp).
 *
 * Pages mapped (all above mmap_min_addr on this host):
 *   0x00013000  ROM page (0x138B8 hysteresis constant -0.045)
 *   0x0006A000  ROM page (0x6A868 / 0x6A87C 1D table descriptors)
 *   0x00072000  ROM page (0x72C5C rpm_raw 375, 0x72C60/64/68/6C/70 constants,
 *                         0x72C88/0x72CB8 axes, 0x72CAC/0x72CDC u8 cells)
 *   0xFFFFA000  RAM[0xFFFFA424/0xFFFFA718/20/28/30/0xFFFFAADA]
 *   0xFFFFB000  RAM[0xFFFFB5A4/0xFFFFB5AA/0xFFFFB5AC/0xFFFFB5B8/0xFFFFB5C4]
 *   0xFFFFC000  RAM[0xFFFFC084 coolant status, 0xFFFFC12C coolant temp]
 * ==========================================================================*/
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>
#include <fcntl.h>

/* 0x1379C — see src/rx8_calc_adaptive_fuel_trim.c. */
void rx8_calc_adaptive_fuel_trim(void);

#define ROM_HYST_ADDR  0x000138B8u   /* f32 -0.045  (hysteresis)      */
#define ROM_DESC1_ADDR 0x0006A868u   /* 1D descriptor (primary)       */
#define ROM_DESC2_ADDR 0x0006A87Cu   /* 1D descriptor (secondary)     */
#define ROM_CAL_ADDR   0x00072000u   /* constants + axes + cells      */
#define RAM_RPM_ADDR   0xFFFFB5B8u   /* f32  engine speed             */
#define RAM_LAM_ADDR   0xFFFFB5C4u   /* f32  lambda feedback          */
#define RAM_COOL_ADDR   0xFFFFC12Cu  /* f32  coolant temperature      */
#define RAM_COOLST_ADDR 0xFFFFC084u  /* f32  coolant status           */
#define RAM_EN_ADDR     0xFFFFB5A4u  /* u8   enable flag              */
#define RAM_SEL_ADDR    0xFFFFB5ACu  /* u8   table select (en==0)     */
#define RAM_FLAG_ADDR   0xFFFFB5AAu  /* u8   table select (en!=0)     */
#define RAM_CL_ADDR     0xFFFFAADAu  /* u8   closed-loop flag         */
#define RAM_RPMRAW_ADDR 0xFFFFA424u  /* u16  engine RPM raw           */
#define RAM_STAT_ADDR   0xFFFFA730u  /* u8   status (in/out)          */
#define RAM_ERR_ADDR    0xFFFFA728u  /* f32  error output             */
#define RAM_TRIM_ADDR   0xFFFFA720u  /* f32  trim output              */
#define RAM_LEAD_ADDR   0xFFFFA718u  /* f32  final output             */

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

    /* RAM pages covering every cell of the function. */
    map_page(RAM_RPM_ADDR);
    map_page(RAM_CL_ADDR);
    map_page(RAM_COOLST_ADDR);

    /* ROM calibration pages, mapped straight from the stock bin so both sides
     * read byte-identical big-endian constants and tables. */
    map_rom_page(romfd, ROM_HYST_ADDR);
    map_rom_page(romfd, ROM_DESC1_ADDR);
    map_rom_page(romfd, ROM_CAL_ADDR);
    close(romfd);

    while (fgets(line, sizeof line, stdin)) {
        unsigned long rpm, coolant, lam, en, sel, flag, cl, coolst, rpmraw, prev;
        float f;
        uint32_t u;

        if (sscanf(line,
                   "atr %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx",
                   &rpm, &coolant, &lam, &en, &sel, &flag, &cl,
                   &coolst, &rpmraw, &prev) != 10) {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }

        /* Seed the input RAM cells (floats from raw bits, endian-neutral). */
        seed_f((float *)(uintptr_t)RAM_RPM_ADDR, rpm);
        seed_f((float *)(uintptr_t)RAM_LAM_ADDR, lam);
        seed_f((float *)(uintptr_t)RAM_COOL_ADDR, coolant);
        seed_f((float *)(uintptr_t)RAM_COOLST_ADDR, coolst);
        *(volatile uint8_t  *)(uintptr_t)RAM_EN_ADDR   = (uint8_t)en;
        *(volatile uint8_t  *)(uintptr_t)RAM_SEL_ADDR  = (uint8_t)sel;
        *(volatile uint8_t  *)(uintptr_t)RAM_FLAG_ADDR = (uint8_t)flag;
        *(volatile uint8_t  *)(uintptr_t)RAM_CL_ADDR   = (uint8_t)cl;
        *(volatile uint16_t *)(uintptr_t)RAM_RPMRAW_ADDR = (uint16_t)rpmraw;
        *(volatile uint8_t  *)(uintptr_t)RAM_STAT_ADDR = (uint8_t)prev;

        rx8_calc_adaptive_fuel_trim();

        f = *(volatile float *)(uintptr_t)RAM_ERR_ADDR;
        memcpy(&u, &f, sizeof u);
        printf("%08X ", (unsigned)u);
        f = *(volatile float *)(uintptr_t)RAM_TRIM_ADDR;
        memcpy(&u, &f, sizeof u);
        printf("%08X ", (unsigned)u);
        printf("%02X ", (unsigned)*(volatile uint8_t *)(uintptr_t)RAM_STAT_ADDR);
        f = *(volatile float *)(uintptr_t)RAM_LEAD_ADDR;
        memcpy(&u, &f, sizeof u);
        printf("%08X\n", (unsigned)u);
    }
    return 0;
}

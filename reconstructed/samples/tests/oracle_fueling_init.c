/* ============================================================================
 * oracle_fueling_init.c  —  host test rig for rx8_fueling_init @0x753C
 * ============================================================================
 * Compile together with src/rx8_fueling_init.c and pipe test vectors on stdin;
 * one vector per line, whitespace-separated hex tokens:
 *
 *     fuel <49 hex pre-state tokens>        -> <49 hex post-state tokens>
 *
 * The 49 tokens are the initial bytes/words of every cell the fuel-init chain
 * touches (see the LOCS table below — the exact mirror of LOCS in
 * harness_fueling_init.py, in the same order).  The oracle seeds them, runs
 * the reconstructed C under test and prints the 49 post-state cells
 * width-aligned (%0*wX), one line per vector.
 *
 * The oracle contains NO copy of rx8_fueling_init's logic — that lives solely
 * in src/rx8_fueling_init.c.  It mirrors the *caller-side* set-up:
 *
 *   - RAM / MTU pages backing the cells are mmap(MAP_FIXED)'d (same trick as
 *     tests/host_oracle.c): 0xFFFF9000 (all 0xFFFF9Fxx cells), 0xFFFFF400
 *     (0xFFFFF42A/0xFFFFF42E), 0xFFFFF600 (0xFFFFF6xx MTU registers).
 *   - ROM page 0x0006C000 is mmap()ed from the ROM file (env RX8_ROM_PATH,
 *     default repo stock bin) so the sample's rom_u8/rom_u32 reads of the
 *     0x0006CF64 / 0x0006CF68 calibration bytes return the REAL ROM values.
 *   - The two remaining ROM constants — u8@0x0000DA4D (crank-vars leaf table
 *     entry) and f32@0x000080FC (crank_output_update output = 10.0f) — live on
 *     ROM pages BELOW mmap_min_addr (0x10000) and cannot be backed on the
 *     host; they are pinned in the reconstructed source and verified by the
 *     harness check_cal against the emulator's ROM (see rx8_fueling_init.c).
 *
 * ==========================================================================*/
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>
#include <fcntl.h>

/* 0x753C — see src/rx8_fueling_init.c. */
void rx8_fueling_init(void);

#ifndef ROM_PATH
#define ROM_PATH "/home/davide/ailocal/rx8ecu/roms/stock/60E1D400.bin"
#endif

/* ---- the 49 observed cells (mirror of harness LOCS) ----------------------- */
typedef struct {
    uint32_t addr;
    int      width;
} Cell;

static const Cell LOCS[] = {
    /* MTU timer registers */
    {0xFFFFF42A, 1},   /* f42a  u8   timer control (RMW)        */
    {0xFFFFF42C, 1},   /* f42c  u8   sentinel (unwritten)        */
    {0xFFFFF42E, 2},   /* f42e  u16  timer word (RMW)            */
    {0xFFFFF6C4, 1},   /* f6c4  u8   leaf clear cell             */
    {0xFFFFF6D4, 4},   /* f6d4  u32  period register (cal)       */
    {0xFFFFF6D8, 1},   /* f6d8  u8   leaf result cell            */
    {0xFFFFF6E0, 1},   /* f6e0  u8   timer value = 0xC8          */
    {0xFFFFF6E2, 1},   /* f6e2  u8   sentinel (unwritten)        */
    {0xFFFFF6E4, 1},   /* f6e4  u8   timer control 2 (RMW)       */
    {0xFFFFF6EA, 2},   /* f6ea  u16  fuel timing control (RMW)   */
    {0xFFFFF6EC, 1},   /* f6ec  u8   sentinel (unwritten)        */
    /* crank value / state RAM */
    {0xFFFF9F80, 4},   /* 9f80  u32  f32 = 0.0                   */
    {0xFFFF9F84, 4},   /* 9f84  u32  = 0x7FFFFFFF                */
    {0xFFFF9F88, 4},   /* 9f88  u32  = 0x7FFFFFFF                */
    {0xFFFF9F8C, 1},   /* 9f8c  u8   flag = 1                    */
    {0xFFFF9F90, 4},   /* 9f90  u32  f32 = 0.0                   */
    {0xFFFF9F94, 1},   /* 9f94  u8   = 0 (rts delay)             */
    {0xFFFF9F95, 1},   /* 9f95  u8   leaf table index = 0x24     */
    {0xFFFF9F96, 1},   /* 9f96  u8   engine-running flag         */
    {0xFFFF9F97, 1},   /* 9f97  u8   sentinel (unwritten)        */
    {0xFFFF9FA0, 1},   /* 9fa0  u8   flag = 1                    */
    {0xFFFF9FA1, 1},   /* 9fa1  u8   clear (leaf bsr delay)      */
    {0xFFFF9FA2, 1},   /* 9fa2  u8   clear (vars-init bsr delay) */
    {0xFFFF9FA3, 1},   /* 9fa3  u8   flag A = 1 / vars branch    */
    {0xFFFF9FA4, 1},   /* 9fa4  u8   flag B = 0                  */
    {0xFFFF9FA5, 1},   /* 9fa5  u8   flag C = 0                  */
    {0xFFFF9FB0, 4},   /* 9fb0  u32  = 0xFFFFFFFF (mov #0xFF sign-extended) */
    {0xFFFF9FB4, 4},   /* 9fb4  u32  sentinel (unwritten)        */
    {0xFFFF9FBC, 4},   /* 9fbc  u32  f32 = 0.0                   */
    {0xFFFF9FC0, 1},   /* 9fc0  u8   flag D / vars branch cell   */
    {0xFFFF9FC1, 1},   /* 9fc1  u8   clear                       */
    {0xFFFF9FC2, 1},   /* 9fc2  u8   clear                       */
    {0xFFFF9FC3, 1},   /* 9fc3  u8   leaf result copy            */
    {0xFFFF9FC4, 1},   /* 9fc4  u8   flag E = 0                  */
    {0xFFFF9FC5, 1},   /* 9fc5  u8   clear                       */
    {0xFFFF9FC6, 1},   /* 9fc6  u8   sensor control reg C = 0xFF */
    {0xFFFF9FC7, 1},   /* 9fc7  u8   state byte clear            */
    {0xFFFF9FC8, 1},   /* 9fc8  u8   state byte clear            */
    {0xFFFF9FC9, 1},   /* 9fc9  u8   sensor control reg A = 0x00 */
    {0xFFFF9FCA, 1},   /* 9fca  u8   sensor control reg B = 0xFF */
    {0xFFFF9FCB, 1},   /* 9fcb  u8   clear (sensor bsr delay)    */
    {0xFFFF9FCC, 2},   /* 9fcc  u16  = 0xFFFF                    */
    {0xFFFF9FCE, 1},   /* 9fce  u8   flag = 1                    */
    {0xFFFF9FE8, 1},   /* 9fe8  u8   = 0                         */
    {0xFFFF9FF0, 4},   /* 9ff0  u32  f32 = 10.0 (tail target)    */
    {0xFFFF9FF4, 4},   /* 9ff4  u32  f32 = 10.0 (tail target)    */
    {0xFFFF9FF8, 4},   /* 9ff8  u32  f32 = 0.0  (tail target)    */
    {0xFFFF9FFC, 4},   /* 9ffc  u32  f32 = 0.0  (tail target)    */
    {0xFFFF9FEC, 4},   /* 9fec  u32  f32 = 1.0  (tail target)    */
};
#define N_CELLS ((int)(sizeof LOCS / sizeof LOCS[0]))   /* 49 */

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

/* Native multi-byte access (like oracle_immo_state_ready_to_drive_engine_off.c):
 * the ROM's big-endian mov.w/mov.l and the host's native store/load produce the
 * same NUMBER, and the harness compares numeric values.  No cell here is ever
 * touched bytewise when its width is 2/4 (all u16/u32 cells are RMW or fully
 * overwritten through native pointers), so bytewise vs native only matters for
 * the numeric round-trip — which native guarantees. */
static uint32_t rd_cell(uint32_t addr, int w)
{
    switch (w) {
    case 1: return *(volatile uint8_t *)(uintptr_t)addr;
    case 2: return *(volatile uint16_t *)(uintptr_t)addr;
    default: return *(volatile uint32_t *)(uintptr_t)addr;
    }
}

static void wr_cell(uint32_t addr, int w, uint32_t v)
{
    switch (w) {
    case 1: *(volatile uint8_t *)(uintptr_t)addr = (uint8_t)v; break;
    case 2: *(volatile uint16_t *)(uintptr_t)addr = (uint16_t)v; break;
    default: *(volatile uint32_t *)(uintptr_t)addr = (uint32_t)v; break;
    }
}

int main(void)
{
    char line[1024];
    unsigned long vals[N_CELLS];
    int fd;
    const char *rom_path = getenv("RX8_ROM_PATH");
    if (!rom_path)
        rom_path = ROM_PATH;

    /* RAM / MTU pages backing all 49 cells. */
    map_page(0xFFFF9000u);
    map_page(0xFFFFF400u);
    map_page(0xFFFFF600u);

    /* ROM page holding the mmap-able calibration bytes (0x0006CF64/0x6CF68). */
    fd = open(rom_path, O_RDONLY);
    if (fd < 0) {
        perror(rom_path);
        return 2;
    }
    map_rom_page(fd, 0x0006C000u);
    close(fd);

    while (fgets(line, sizeof line, stdin)) {
        char tag[8];
        int n = sscanf(line, "%7s", tag);
        if (n != 1 || strcmp(tag, "fuel") != 0) {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
        n = sscanf(line + 5, "%lx%lx%lx%lx%lx%lx%lx%lx%lx%lx"
                            "%lx%lx%lx%lx%lx%lx%lx%lx%lx%lx"
                            "%lx%lx%lx%lx%lx%lx%lx%lx%lx%lx"
                            "%lx%lx%lx%lx%lx%lx%lx%lx%lx%lx"
                            "%lx%lx%lx%lx%lx%lx%lx%lx%lx",
                   &vals[0], &vals[1], &vals[2], &vals[3], &vals[4],
                   &vals[5], &vals[6], &vals[7], &vals[8], &vals[9],
                   &vals[10], &vals[11], &vals[12], &vals[13], &vals[14],
                   &vals[15], &vals[16], &vals[17], &vals[18], &vals[19],
                   &vals[20], &vals[21], &vals[22], &vals[23], &vals[24],
                   &vals[25], &vals[26], &vals[27], &vals[28], &vals[29],
                   &vals[30], &vals[31], &vals[32], &vals[33], &vals[34],
                   &vals[35], &vals[36], &vals[37], &vals[38], &vals[39],
                   &vals[40], &vals[41], &vals[42], &vals[43], &vals[44],
                   &vals[45], &vals[46], &vals[47], &vals[48]);
        if (n != N_CELLS) {
            fprintf(stderr, "expected %d cells, got %d: %s", N_CELLS, n, line);
            return 2;
        }

        /* Seed every cell through its native width (see rd_cell comment). */
        for (int i = 0; i < N_CELLS; i++)
            wr_cell(LOCS[i].addr, LOCS[i].width, (uint32_t)vals[i]);

        rx8_fueling_init();

        for (int i = 0; i < N_CELLS; i++) {
            uint32_t a = LOCS[i].addr;
            int w = LOCS[i].width;
            printf(i ? " %0*X" : "%0*X", w * 2, (unsigned)rd_cell(a, w));
        }
        putchar('\n');
    }
    return 0;
}

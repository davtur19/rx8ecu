/* ============================================================================
 * oracle_wankel_leading_trailing_split_487dc.c — host rig for
 *                          rx8_wankel_leading_trailing_split_487dc @0x487DC
 * ============================================================================
 * Compile together with samples/src/rx8_wankel_leading_trailing_split_487dc.c
 * and pipe test vectors on stdin; one vector per line, whitespace-separated
 * hex tokens:
 *
 *     split <b563> <b565> <b567> <b569> <b56d> <b56b> <ccd6> <ccd7> <ccde>
 *           <b57c> <b560> <b588> <ccd3> <ccd4> <ccd5> <b584> <b586> <b57e>
 *           <b580> <b582> <cc8c> <cc8d>
 *           <h750> <h751> <h764> <h765> <h768> <h769> <h76c> <h76d>
 *           <h770> <h771> <h778> <h779> <h780> <h781>
 *           <c6ac> <ccd2>
 *                                             -> <CCD2> <C6AC>
 *
 *   bxxx / ccxx : the 22 plain-byte gate cells (RAM8[0xFFFFB5xx] /
 *                 RAM8[0xFFFFCCxx]), in ROM block order — each enables its
 *                 threshold when == 1
 *   hxxx        : the 7 redundant (value, ~value) u8 pairs read through the
 *                 leaf 0x3ED3C at 0xFFFF8750/8764/8768/876C/8770/8778/8780
 *                 (value byte then complement byte, in ROM block order)
 *   c6ac        : pre-state of the fault flag RAM8[0xFFFFC6AC]
 *   ccd2        : pre-state of the output selector RAM8[0xFFFFCCD2]
 *
 * The oracle re-implements only the *caller-side* set-up: it mmap()s the
 * pages backing the RAM cells AND the ROM calibration table, seeds every
 * byte and prints the two post-state bytes.  It contains NO copy of the
 * function logic — that lives solely in the reconstructed source under test.
 *
 * The 29 calibration thresholds cal8[0x7C27F..0x7C29B] are NOT shipped
 * inline: the ROM page backing them is MAP_FIXED-mapped at the same virtual
 * address the ROM uses and seeded once from the ROM file (byte-for-byte; the
 * file is big-endian and every access here is u8, so no byte-swap is needed).
 * $RX8_ROM_PATH (set by the harness) points at roms/stock/60E1D400.bin.
 *
 * Pages mapped (all above mmap_min_addr on this host):
 *   0x0007C000  ROM calibration table (0x7C27F..0x7C29B)
 *   0xFFFF8000  RAM[0xFFFF8750..0xFFFF8781] redundant pairs
 *   0xFFFFB000  RAM[0xFFFFB560..0xFFFFB588] plain gates
 *   0xFFFFC000  RAM[0xFFFFC6AC] fault flag, RAM[0xFFFFCC8C..0xFFFFCCDE]
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <fcntl.h>
#include <sys/mman.h>
#include <unistd.h>

/* rx8_wankel_leading_trailing_split_487dc is not in rx8_samples.h — the
 * shared header is frozen.  The reconstructed source itself carries the
 * authoritative definition (src/rx8_wankel_leading_trailing_split_487dc.c);
 * this prototype mirrors it exactly. */
void rx8_wankel_leading_trailing_split_487dc(void);

#define ROM_CAL_BASE    0x0007C000u   /* page backing cal8[0x7C27F..0x7C29B] */
#define ROM_CAL_FIRST   0x0007C27Fu
#define ROM_CAL_LAST    0x0007C29Bu

#define FAULT_ADDR      0xFFFFC6ACu   /* u8 fault flag (leaf 0x3ED3C output) */
#define SPLIT_ADDR      0xFFFFCCD2u   /* u8 selector byte (output)           */

/* 22 plain gate bytes, in ROM block order (see GATE_ADDRS in the lift test). */
static const uint32_t GATE_ADDRS[22] = {
    0xFFFFB563u, 0xFFFFB565u, 0xFFFFB567u, 0xFFFFB569u, 0xFFFFB56Du,
    0xFFFFB56Bu, 0xFFFFCCD6u, 0xFFFFCCD7u, 0xFFFFCCDEu, 0xFFFFB57Cu,
    0xFFFFB560u, 0xFFFFB588u, 0xFFFFCCD3u, 0xFFFFCCD4u, 0xFFFFCCD5u,
    0xFFFFB584u, 0xFFFFB586u, 0xFFFFB57Eu, 0xFFFFB580u, 0xFFFFB582u,
    0xFFFFCC8Cu, 0xFFFFCC8Du,
};

/* 7 redundant (value, ~value) pair bases, in ROM block order (see RV_GATES
 * in the lift test).  The leaf reads base and base+1. */
static const uint32_t PAIR_ADDRS[7] = {
    0xFFFF8750u, 0xFFFF8764u, 0xFFFF8768u, 0xFFFF876Cu,
    0xFFFF8770u, 0xFFFF8778u, 0xFFFF8780u,
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

/* Seed the ROM calibration page with the actual stock-60E1D400.bin bytes
 * (u8 accesses only, so no endianness handling is needed). */
static void seed_rom_cal(int fd)
{
    unsigned char b[32];
    size_t i;
    if (pread(fd, b, ROM_CAL_LAST - ROM_CAL_FIRST + 1, ROM_CAL_FIRST) !=
        (ssize_t)(ROM_CAL_LAST - ROM_CAL_FIRST + 1)) {
        perror("pread ROM cal");
        exit(2);
    }
    for (i = 0; i <= ROM_CAL_LAST - ROM_CAL_FIRST; i++)
        *(volatile uint8_t *)(uintptr_t)(ROM_CAL_FIRST + i) = b[i];
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

    map_page(ROM_CAL_BASE);
    map_page(0xFFFF8000u);
    map_page(0xFFFFB000u);
    map_page(0xFFFFC000u);
    seed_rom_cal(romfd);

    while (fgets(line, sizeof line, stdin)) {
        unsigned long g[22], p[14], c6ac, ccd2;
        int n = sscanf(line,
                       "split %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx"
                       " %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx"
                       " %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx"
                       " %lx %lx %lx %lx",
                       &g[0], &g[1], &g[2], &g[3], &g[4], &g[5],
                       &g[6], &g[7], &g[8], &g[9], &g[10], &g[11],
                       &g[12], &g[13], &g[14], &g[15], &g[16], &g[17],
                       &g[18], &g[19], &g[20], &g[21],
                       &p[0], &p[1], &p[2], &p[3], &p[4], &p[5],
                       &p[6], &p[7], &p[8], &p[9], &p[10], &p[11],
                       &p[12], &p[13], &c6ac, &ccd2);
        if (n != 38) {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }

        /* Seed the 22 plain gates, the 7 redundant pairs and the pre-states. */
        for (int i = 0; i < 22; i++)
            *(volatile uint8_t *)(uintptr_t)GATE_ADDRS[i] = (uint8_t)g[i];
        for (int i = 0; i < 7; i++) {
            *(volatile uint8_t *)(uintptr_t)PAIR_ADDRS[i]      = (uint8_t)p[2 * i];
            *(volatile uint8_t *)(uintptr_t)(PAIR_ADDRS[i] + 1) = (uint8_t)p[2 * i + 1];
        }
        *(volatile uint8_t *)(uintptr_t)FAULT_ADDR = (uint8_t)c6ac;
        *(volatile uint8_t *)(uintptr_t)SPLIT_ADDR = (uint8_t)ccd2;

        rx8_wankel_leading_trailing_split_487dc();

        printf("%02X %02X\n",
               *(volatile uint8_t *)(uintptr_t)SPLIT_ADDR,
               *(volatile uint8_t *)(uintptr_t)FAULT_ADDR);
    }
    return 0;
}

/* ============================================================================
 * oracle_immo_update_related.c  —  host test rig for
 *                                     rx8_immo_update_related @0x37120
 * ============================================================================
 * Compile together with samples/src/rx8_immo_update_related.c and pipe test
 * vectors on stdin; one vector per line, whitespace-separated hex tokens:
 *
 *     immoupd  <46 seed outputs> <13 seed sources>
 *                                  -> <46 final outputs>
 *
 * The first 59 tokens are the INITIAL values of every RAM cell the function
 * (and its inlined callees sub_37000/eeprom_write_sched/updateE2RAMBasedOn
 * Input/writeToE2RAMArea) can observe or modify; the oracle seeds the mmap()ed
 * page, runs the reconstructed C and prints the 46 FINAL values of the
 * side-effected cells.  It contains NO copy of the function logic — that lives
 * solely in the reconstructed source under test.
 *
 * Cell order (shared with harness_immo_update_related.py):
 *   0..5   u8  0xFFFFC2D1 C2D2 C2D5 C2D6 C2D7 C2D8   immo write-queue
 *   6      u8  0xFFFFC2F8                             E2 write-done flag
 *   7      u8  0xFFFFC511                             scheduler status
 *   8..10  u16 0xFFFFC506 0xFFFFC4FE 0xFFFFC500       scheduler words
 *   11..17 u8  0xFFFFC514 C2FB C50C C50F C516 C515 C510
 *   18..31 u8  E2 value shadow: 0xFFFFC2FE + idx, idx = 0x00,0x0C..0x10,
 *                                0x12..0x14,0x1A..0x1E
 *   32..45 u8  E2 complement shadow: 0xFFFFC3FE + same indices
 *   46..58 u8  seed-only E2 sources: 0xFFFFC2E5..C2F2 and 0xFFFFC242..C244
 *
 * All 59 addresses live in the single 0xFFFFC000 page (above this host's
 * mmap_min_addr 0x10000), so one MAP_FIXED mapping backs everything, exactly
 * as in tests/host_oracle.c.
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

/* Declared here (rx8_samples.h is shared/off-limits for this task). */
void rx8_immo_update_related(void);

typedef struct { const char *name; uintptr_t addr; int width; } cell_t;

/* 46 compared (output) cells, in vector order. */
static const cell_t OUT[] = {
    { "C2D1", 0xFFFFC2D1, 1 }, { "C2D2", 0xFFFFC2D2, 1 },
    { "C2D5", 0xFFFFC2D5, 1 }, { "C2D6", 0xFFFFC2D6, 1 },
    { "C2D7", 0xFFFFC2D7, 1 }, { "C2D8", 0xFFFFC2D8, 1 },
    { "C2F8", 0xFFFFC2F8, 1 }, { "C511", 0xFFFFC511, 1 },
    { "C506", 0xFFFFC506, 2 }, { "C4FE", 0xFFFFC4FE, 2 },
    { "C500", 0xFFFFC500, 2 }, { "C514", 0xFFFFC514, 1 },
    { "C2FB", 0xFFFFC2FB, 1 }, { "C50C", 0xFFFFC50C, 1 },
    { "C50F", 0xFFFFC50F, 1 }, { "C516", 0xFFFFC516, 1 },
    { "C515", 0xFFFFC515, 1 }, { "C510", 0xFFFFC510, 1 },
    { "E2_00", 0xFFFFC2FE, 1 }, { "E2_0C", 0xFFFFC30A, 1 },
    { "E2_0D", 0xFFFFC30B, 1 }, { "E2_0E", 0xFFFFC30C, 1 },
    { "E2_0F", 0xFFFFC30D, 1 }, { "E2_10", 0xFFFFC30E, 1 },
    { "E2_12", 0xFFFFC310, 1 }, { "E2_13", 0xFFFFC311, 1 },
    { "E2_14", 0xFFFFC312, 1 }, { "E2_1A", 0xFFFFC318, 1 },
    { "E2_1B", 0xFFFFC319, 1 }, { "E2_1C", 0xFFFFC31A, 1 },
    { "E2_1D", 0xFFFFC31B, 1 }, { "E2_1E", 0xFFFFC31C, 1 },
    { "C_00", 0xFFFFC3FE, 1 }, { "C_0C", 0xFFFFC40A, 1 },
    { "C_0D", 0xFFFFC40B, 1 }, { "C_0E", 0xFFFFC40C, 1 },
    { "C_0F", 0xFFFFC40D, 1 }, { "C_10", 0xFFFFC40E, 1 },
    { "C_12", 0xFFFFC410, 1 }, { "C_13", 0xFFFFC411, 1 },
    { "C_14", 0xFFFFC412, 1 }, { "C_1A", 0xFFFFC418, 1 },
    { "C_1B", 0xFFFFC419, 1 }, { "C_1C", 0xFFFFC41A, 1 },
    { "C_1D", 0xFFFFC41B, 1 }, { "C_1E", 0xFFFFC41C, 1 },
};

/* 13 seed-only cells (E2 working copies + CAN shadows read by the inlined
 * updateE2RAMBasedOnInput / writeToE2RAMArea). */
static const cell_t SRC[] = {
    { "C2E5", 0xFFFFC2E5, 1 }, { "C2E6", 0xFFFFC2E6, 1 },
    { "C2E7", 0xFFFFC2E7, 1 }, { "C2E8", 0xFFFFC2E8, 1 },
    { "C2E9", 0xFFFFC2E9, 1 }, { "C2EE", 0xFFFFC2EE, 1 },
    { "C2EF", 0xFFFFC2EF, 1 }, { "C2F0", 0xFFFFC2F0, 1 },
    { "C2F1", 0xFFFFC2F1, 1 }, { "C2F2", 0xFFFFC2F2, 1 },
    { "C242", 0xFFFFC242, 1 }, { "C243", 0xFFFFC243, 1 },
    { "C244", 0xFFFFC244, 1 },
};

#define N_OUT (sizeof OUT / sizeof OUT[0])
#define N_SRC (sizeof SRC / sizeof SRC[0])

static void wr_cell(uintptr_t addr, int width, unsigned long v)
{
    if (width == 1)
        *(volatile uint8_t  *)(uintptr_t)addr = (uint8_t)v;
    else
        *(volatile uint16_t *)(uintptr_t)addr = (uint16_t)v;
}

static unsigned long rd_cell(uintptr_t addr, int width)
{
    return (width == 1)
        ? (unsigned long)*(volatile uint8_t  *)(uintptr_t)addr
        : (unsigned long)*(volatile uint16_t *)(uintptr_t)addr;
}

static void map_page(uintptr_t addr)
{
    long page = sysconf(_SC_PAGESIZE);
    uintptr_t base = addr & ~((uintptr_t)page - 1);
    void *p = mmap((void *)base, (size_t)page, PROT_READ | PROT_WRITE,
                   MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED, -1, 0);
    if (p == MAP_FAILED) { perror("mmap"); exit(1); }
}

int main(void)
{
    char line[1024];
    unsigned long val[N_OUT + N_SRC];

    map_page(0xFFFFC000u);   /* covers 0xFFFFC242..0xFFFFC5xx */

    while (fgets(line, sizeof line, stdin)) {
        size_t i;
        if (sscanf(line, "immoupd %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx "
                          "%lx %lx %lx %lx %lx %lx %lx %lx %lx %lx "
                          "%lx %lx %lx %lx %lx %lx %lx %lx %lx %lx "
                          "%lx %lx %lx %lx %lx %lx %lx %lx %lx %lx "
                          "%lx %lx %lx %lx %lx %lx %lx %lx %lx %lx "
                          "%lx %lx %lx %lx %lx %lx %lx %lx %lx",
                   &val[0], &val[1], &val[2], &val[3], &val[4], &val[5],
                   &val[6], &val[7], &val[8], &val[9],
                   &val[10], &val[11], &val[12], &val[13], &val[14],
                   &val[15], &val[16], &val[17], &val[18], &val[19],
                   &val[20], &val[21], &val[22], &val[23], &val[24],
                   &val[25], &val[26], &val[27], &val[28], &val[29],
                   &val[30], &val[31], &val[32], &val[33], &val[34],
                   &val[35], &val[36], &val[37], &val[38], &val[39],
                   &val[40], &val[41], &val[42], &val[43], &val[44],
                   &val[45], &val[46], &val[47], &val[48], &val[49],
                   &val[50], &val[51], &val[52], &val[53], &val[54],
                   &val[55], &val[56], &val[57], &val[58])
            != (int)(N_OUT + N_SRC)) {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }

        /* Seed every observable cell from the vector. */
        for (i = 0; i < N_OUT; i++)
            wr_cell(OUT[i].addr, OUT[i].width, val[i]);
        for (i = 0; i < N_SRC; i++)
            wr_cell(SRC[i].addr, SRC[i].width, val[N_OUT + i]);

        rx8_immo_update_related();

        /* Print the 46 final side-effected cells (u8 %02X, u16 %04X). */
        for (i = 0; i < N_OUT; i++)
            printf("%s%0*X", i ? " " : "",
                   OUT[i].width == 1 ? 2 : 4,
                   (unsigned)rd_cell(OUT[i].addr, OUT[i].width));
        putchar('\n');
    }
    return 0;
}

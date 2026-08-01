/* ============================================================================
 * oracle_cooling_fan_control.c  —  host test rig for
 *                                    rx8_cooling_fan_control @0x17DCC
 * ============================================================================
 * Compile together with samples/src/rx8_cooling_fan_control.c and pipe test
 * vectors on stdin; one vector per line, whitespace-separated hex tokens:
 *
 *     fan <eps> <coolant> <fan_en> <fan_cnt> <cell_hi> <cell_lo> <err>
 *                                                  -> <fan_en'> <fan_cnt'>
 *                                                     <cell_hi'> <cell_lo'> <err'>
 *
 *   eps     : 4 bytes (f32 bits) of the ROM deadband literal at 0x17EC0
 *   coolant : 4 bytes (f32 bits) of RAM[0xFFFFA73C]
 *   fan_en  : pre-state of the fan-enable latch byte RAM[0xFFFFA95C]
 *   fan_cnt : pre-state of the fan speed counter byte RAM[0xFFFFA93B]
 *   cell_hi/cell_lo : pre-state of the redundant u8 cell at RAM[0xFFFF8076..77]
 *   err     : pre-state of the corruption flag byte RAM[0xFFFFC6AC]
 *
 * The oracle re-implements only the *caller-side* set-up: it mmap()s the pages
 * backing the RAM cells AND the ROM eps literal, seeds every byte and prints
 * the five post-state bytes.  It contains NO copy of the function logic — that
 * lives solely in samples/src/rx8_cooling_fan_control.c.  All accesses are
 * byte/raw-bits so host endianness never enters the comparison (the function
 * under test reads the coolant/eps floats and the cell bytes through the very
 * same addresses the ROM uses).
 *
 * Pages mapped (all above mmap_min_addr on this host):
 *   0x00017000  ROM eps literal @0x17EC0
 *   0xFFFF8000  RAM[0xFFFF8076/7] redundant fan-counter shadow cell
 *   0xFFFFA000  RAM[0xFFFFA73C] coolant, RAM[0xFFFFA93B] counter,
 *               RAM[0xFFFFA95C] fan-enable latch
 *   0xFFFFC000  RAM[0xFFFFC6AC] corruption flag
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

extern void rx8_cooling_fan_control(void);

#define ROM_EPS_ADDR   0x00017EC0u
#define COOLANT_ADDR   0xFFFFA73Cu
#define FAN_EN_ADDR    0xFFFFA95Cu
#define FAN_CNT_ADDR   0xFFFFA93Bu
#define CELL_ADDR      0xFFFF8076u
#define ERR_FLAG_ADDR  0xFFFFC6ACu

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

int main(void)
{
    char line[256];

    map_page(ROM_EPS_ADDR);
    map_page(CELL_ADDR);
    map_page(COOLANT_ADDR);     /* also backs FAN_EN_ADDR / FAN_CNT_ADDR */
    map_page(ERR_FLAG_ADDR);

    while (fgets(line, sizeof line, stdin)) {
        unsigned long eps, coolant, fan_en, fan_cnt, cell_hi, cell_lo, err;
        int n = sscanf(line, "fan %lx %lx %lx %lx %lx %lx %lx",
                       &eps, &coolant, &fan_en, &fan_cnt,
                       &cell_hi, &cell_lo, &err);
        if (n != 7) {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }

        /* Seed the ROM eps literal and the four RAM cells (raw bits / bytes,
         * so both sides read identical numbers regardless of endianness). */
        *(volatile uint32_t *)(uintptr_t)ROM_EPS_ADDR   = (uint32_t)eps;
        *(volatile uint32_t *)(uintptr_t)COOLANT_ADDR   = (uint32_t)coolant;
        *(volatile uint8_t  *)(uintptr_t)FAN_EN_ADDR    = (uint8_t)fan_en;
        *(volatile uint8_t  *)(uintptr_t)FAN_CNT_ADDR   = (uint8_t)fan_cnt;
        *(volatile uint8_t  *)(uintptr_t)CELL_ADDR      = (uint8_t)cell_hi;
        *(volatile uint8_t  *)(uintptr_t)(CELL_ADDR + 1) = (uint8_t)cell_lo;
        *(volatile uint8_t  *)(uintptr_t)ERR_FLAG_ADDR  = (uint8_t)err;

        rx8_cooling_fan_control();

        printf("%02X %02X %02X %02X %02X\n",
               *(volatile uint8_t *)(uintptr_t)FAN_EN_ADDR,
               *(volatile uint8_t *)(uintptr_t)FAN_CNT_ADDR,
               *(volatile uint8_t *)(uintptr_t)CELL_ADDR,
               *(volatile uint8_t *)(uintptr_t)(CELL_ADDR + 1),
               *(volatile uint8_t *)(uintptr_t)ERR_FLAG_ADDR);
    }
    return 0;
}

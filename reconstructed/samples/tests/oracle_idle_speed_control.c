/* ============================================================================
 * oracle_idle_speed_control.c  —  host rig for rx8_idle_speed_control
 * ============================================================================
 * Compile together with samples/src/rx8_idle_speed_control.c and pipe test
 * vectors on stdin; one vector per line, whitespace-separated hex tokens:
 *
 *     idle <state> <mode> <ac> <running> <load_comp> <idle_en> <old_status>
 *          <learn> <duty> <o2_bits> <cal_hi> <cal_lo> <cal_o2_bits>
 *                                         -> <idle_act> <fb> <ac_lat> <status>
 *                                            <idle_en> <duty> <learn> <modef>
 *                                            <ac> <c6ac>
 *
 *   state/mode/ac/running/load_comp/idle_en/old_status/learn : the 8 input
 *              RAM bytes (0xFFFFA428 / AAE0 / A979 / A998 / A978 / A96C /
 *              A96A / A970); ac and A975 are seeded with a distinguishable
 *              sentinel (0x55) so an unexpected write is caught.
 *   duty      : u16 pre-state of the IACV duty word (RAM[0xFFFFA96E])
 *   o2_bits   : raw IEEE-754 single-precision bits of the O2 voltage
 *               (RAM[0xFFFFAA10]) — shipped as bits so float->hex round-trips
 *               exactly on both sides of the pipe
 *   cal_hi / cal_lo / cal_o2_bits : the function's three calibration
 *               constants (ROM16[0x78E42]=156, ROM16[0x78E44]=500, f32
 *               @0x78E64=-40.0), read by the harness from the stock bin and
 *               shipped inline so both sides read identical values.
 *
 * The oracle re-implements only the *caller-side* set-up: it mmap()s the
 * pages backing the RAM cells AND the ROM calibration page, seeds every byte
 * and prints the ten post-state cells.  It contains NO copy of the function
 * logic — that lives solely in the reconstructed source under test.
 *
 * The three shared leaves are implemented here to mirror the REAL ROM bytes
 * the emulator executes (see rx8_idle_speed_control.c): add16bitSaturate
 * @0x2460, check_pair_3ED3C @0x3ED3C (incl. its RAM[0xFFFFC6AC]=1 side
 * effect on the fallback path, and the ROM byte pair 0x807C/0x807D read from
 * the ROM image since that address lies below mmap_min_addr), and
 * osTaskScheduler @0x9668 (no writes to any published cell).
 *
 * Pages mapped (all above mmap_min_addr on this host):
 *   0x00078000  ROM calibration page (0x78E42/0x78E44/0x78E64)
 *   0xFFFFA000  RAM[0xFFFFA428..0xFFFFAAE0] (all idle cells + O2)
 *   0xFFFFC000  RAM[0xFFFFC6AC] (check_pair fallback side effect)
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

#include "rx8_samples.h"
#include "rx8_hw.h"

/* rx8_idle_speed_control is not (yet) in rx8_samples.h — the shared header is
 * owned by the samples build.  The reconstructed source itself carries the
 * authoritative definition (src/rx8_idle_speed_control.c); this prototype
 * mirrors it exactly, as do the three leaf prototypes it calls. */
void     rx8_idle_speed_control(void);
uint32_t check_pair_3ED3C(uint32_t addr, uint32_t fallback);
uint16_t add16bitSaturate(uint16_t a, uint16_t b);
void     osTaskScheduler(uint32_t task_id, uint32_t arg);

#define ROM_CAL_PAGE        0x00078000u   /* holds 0x78E42/0x78E44/0x78E64 */
#define RAM_CELL_PAGE       0xFFFFA000u   /* 0xFFFFA428..0xFFFFAAE0       */
#define RAM_FLAG_PAGE       0xFFFFC000u   /* 0xFFFFC6AC                   */

#define CAL_DUTY_HIGH_ADDR  0x00078E42u   /* u16 duty ceiling (156)       */
#define CAL_DUTY_LOW_ADDR   0x00078E44u   /* u16 duty ceiling low (500)   */
#define CAL_O2_FUELCUT_ADDR 0x00078E64u   /* f32 O2 fuel-cut threshold    */

#define ROM_PAIR_ADDR       0x807Cu       /* byte pair read by check_pair */

/* Mirror of the ROM image byte pair @0x807C/0x807D (loaded from the stock
 * bin at startup).  The emulator reads these through its ram->rom fallback;
 * on the host the address is below mmap_min_addr so the oracle keeps the two
 * bytes explicitly. */
static uint8_t rom_pair[2];

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

/* ---- the three shared leaves, mirroring the real ROM bytes ----
 * @0x2460 — add16bitSaturate: r4 = extu.w(a), r5 = extu.w(b),
 *           r0 = (a+b) clamped at 0xFFFF (cmp/hs + mov r5,r4). */
uint16_t add16bitSaturate(uint16_t a, uint16_t b)
{
    uint32_t s = (uint32_t)a + (uint32_t)b;
    return (uint16_t)(s > 0xFFFFu ? 0xFFFFu : s);
}

/* @0x3ED3C — check_pair_3ED3C(addr, fallback):
 *   if (RAM[addr] == ~RAM[addr+1]) return RAM[addr]
 *   else { RAM[0xFFFFC6AC] = 1; return fallback & 0xFF }   (via 0x3F050)
 * The pair bytes are read from the ROM image (the stock values 0x24/0x62 at
 * 0x807C/0x807D are never complementary, so this always returns the
 * fallback = 0). */
uint32_t check_pair_3ED3C(uint32_t addr, uint32_t fallback)
{
    /* The ROM reads the pair at (addr, addr+1); the reconstructed function
     * always passes addr == 0x807C, whose two ROM bytes live in rom_pair. */
    uint8_t a = (addr == ROM_PAIR_ADDR) ? rom_pair[0] : rom_pair[1];
    uint8_t b = rom_pair[1];
    if (a == (uint8_t)~b) {
        return a;
    }
    RX8_IO8(0xFFFFC6AC) = 1;
    return fallback & 0xFF;
}

/* @0x9668 — osTaskScheduler(task_id, slot): posts the RTOS task; with the
 * stock task table the post performs no writes to any published cell, so the
 * oracle models it as a no-op. */
void osTaskScheduler(uint32_t task_id, uint32_t arg)
{
    (void)task_id;
    (void)arg;
}

int main(void)
{
    char line[256];
    unsigned long state, mode, ac, running, load_comp, idle_en, old_status;
    unsigned long learn, duty, o2bits, cal_hi, cal_lo, cal_o2;
    uint32_t u;

    /* Load the ROM byte pair used by check_pair_3ED3C. */
    {
        const char *path = getenv("RX8_ROM");
        FILE *f = path ? fopen(path, "rb") : NULL;
        if (!f) {
            fprintf(stderr, "set RX8_ROM to the stock bin path\n");
            return 2;
        }
        fseek(f, ROM_PAIR_ADDR, SEEK_SET);
        if (fread(rom_pair, 1, 2, f) != 2) {
            fprintf(stderr, "short read of ROM pair @0x%X\n", ROM_PAIR_ADDR);
            return 2;
        }
        fclose(f);
    }

    map_page(ROM_CAL_PAGE);
    map_page(RAM_CELL_PAGE);
    map_page(RAM_FLAG_PAGE);

    while (fgets(line, sizeof line, stdin)) {
        int n = sscanf(line,
                       "idle %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx",
                       &state, &mode, &ac, &running, &load_comp, &idle_en,
                       &old_status, &learn, &duty, &o2bits,
                       &cal_hi, &cal_lo, &cal_o2);
        if (n != 13) {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }

        /* Seed the ROM calibration page exactly as the stock bin has it. */
        *(volatile uint16_t *)(uintptr_t)CAL_DUTY_HIGH_ADDR = (uint16_t)cal_hi;
        *(volatile uint16_t *)(uintptr_t)CAL_DUTY_LOW_ADDR  = (uint16_t)cal_lo;
        u = (uint32_t)cal_o2;
        memcpy((void *)(uintptr_t)CAL_O2_FUELCUT_ADDR, &u, sizeof u);

        /* Seed the input RAM cells (distinguishable sentinels for the cells
         * that must NOT be touched unless the path writes them). */
        RX8_IO8(0xFFFFA428)  = (uint8_t)state;
        RX8_IO8(0xFFFFAAE0)  = (uint8_t)mode;
        RX8_IO8(0xFFFFA979)  = (uint8_t)ac;
        RX8_IO8(0xFFFFA998)  = (uint8_t)running;
        RX8_IO8(0xFFFFA978)  = (uint8_t)load_comp;
        RX8_IO8(0xFFFFA96C)  = (uint8_t)idle_en;
        RX8_IO8(0xFFFFA96A)  = (uint8_t)old_status;
        RX8_IO8(0xFFFFA970)  = (uint8_t)learn;
        RX8_IO8(0xFFFFA975)  = 0x55;          /* sentinel: iacv mode flag */
        RX8_IO8(0xFFFFC6AC)  = 0x00;          /* sentinel: check_pair flag */
        RX8_IO16(0xFFFFA96E) = (uint16_t)duty;
        u = (uint32_t)o2bits;
        memcpy((void *)(uintptr_t)0xFFFFAA10, &u, sizeof u);   /* exact f32 */

        rx8_idle_speed_control();

        printf("%02X %02X %02X %02X %02X %04X %02X %02X %02X %02X\n",
               (unsigned)RX8_IO8(0xFFFFA96B),    /* idle-active  (f24)   */
               (unsigned)RX8_IO8(0xFFFFA968),    /* feedback     (f20)   */
               (unsigned)RX8_IO8(0xFFFFA969),    /* AC latch     (r9)    */
               (unsigned)RX8_IO8(0xFFFFA96A),    /* status       (r10)   */
               (unsigned)RX8_IO8(0xFFFFA96C),    /* idle-enable  (r13)   */
               (unsigned)RX8_IO16(0xFFFFA96E),   /* IACV duty (u16)      */
               (unsigned)RX8_IO8(0xFFFFA970),    /* learn = load_comp    */
               (unsigned)RX8_IO8(0xFFFFA975),    /* iacv mode flag       */
               (unsigned)RX8_IO8(0xFFFFA979),    /* AC request           */
               (unsigned)RX8_IO8(0xFFFFC6AC));   /* check_pair fallback  */
    }
    return 0;
}

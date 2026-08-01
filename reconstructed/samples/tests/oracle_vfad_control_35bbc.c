/* ============================================================================
 * oracle_vfad_control_35bbc.c  —  host rig for rx8_vfad_control_35bbc @0x35BBC
 * ============================================================================
 * Compile together with samples/src/rx8_vfad_control_35bbc.c and pipe test
 * vectors on stdin; one vector per line, whitespace-separated hex tokens:
 *
 *     vfad <boost> <cmd0> <mask> <st> <magic> <src> <cnt> <inp> <latch>
 *          <ptrcell> <f754> <on> <hyst>
 *                                       -> <cmd> <f754> <st> <latch> <ptrcell>
 *
 *   boost   : raw f32 bits of the boost pressure (RAM[0xFFFFB5B8])
 *   cmd0    : pre-state of the VFAD command byte (RAM[0xFFFFC234])
 *   mask/st/magic/src/cnt/inp/latch/ptrcell : pre-states of the 0x5D800
 *             alternating-sensor SM descriptor + on-chip RAM cells
 *   f754    : pre-state of the 16-bit hardware word (RAM[0xFFFFF754])
 *   on/hyst : raw f32 bits of the ROM calibration constants @0x7A5AC / @0x7A5B0
 *
 * The oracle re-implements only the *caller-side* set-up: it mmap()s the
 * pages backing the RAM cells, the SM descriptor and the ROM calibration
 * table, seeds every byte and prints the five post-state cells.  It contains
 * NO copy of the function logic — that lives solely in the reconstructed
 * source under test.
 *
 * Pages mapped (all above mmap_min_addr on this host):
 *   0x00060000  SM descriptor (mask @0x6025C, output ptr @0x60260)
 *   0x0007A000  ROM calibration table (on @0x7A5AC, hyst @0x7A5B0)
 *   0xFFFFB000  RAM[0xFFFFB5B8] boost
 *   0xFFFFC000  RAM[0xFFFFC234] VFAD command
 *   0xFFFFD000  SM cells 0xFFFFD350..0xFFFFD3A8 + output byte @0xFFFFD500
 *   0xFFFFF000  RAM[0xFFFFF754] hardware word
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

/* rx8_vfad_control_35bbc is not (yet) declared in rx8_samples.h — the
 * reconstructed sources are dropped in without touching the shared header. */
void rx8_vfad_control_35bbc(void);

#define BOOST_ADDR    0xFFFFB5B8u   /* f32 boost pressure                 */
#define CMD_ADDR      0xFFFFC234u   /* u8 VFAD command                    */
#define F754_ADDR     0xFFFFF754u   /* u16 hardware word, bit 0x0400      */
#define SM_MASK_ADDR  0x6025Cu      /* u8 sensor mask (SM_BASE + 8)       */
#define SM_PTR_ADDR   0x60260u      /* u32 stored output pointer (SM_BASE+0xC) */
#define ST_ADDR       0xFFFFD355u   /* u8 state byte                      */
#define MAGIC_ADDR    0xFFFFD350u   /* u16 magic word (0x17C8)            */
#define INP_ADDR      0xFFFFD3A8u   /* u8 sensor input byte               */
#define CNT_ADDR      0xFFFFD354u   /* u8 count byte                      */
#define SRC_ADDR      0xFFFFD352u   /* u16 source word                    */
#define LATCH_ADDR    0xFFFFD38Fu   /* u8 output latch                    */
#define PTR_CELL      0xFFFFD500u   /* u8 output byte behind SM_PTR       */
#define ROM_ON_ADDR   0x0007A5ACu   /* f32 on-threshold (5250.0)          */
#define ROM_HYST_ADDR 0x0007A5B0u   /* f32 hysteresis width (188.0)       */

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

    map_page(0x00060000u);
    map_page(0x0007A000u);
    map_page(BOOST_ADDR);
    map_page(CMD_ADDR);
    map_page(ST_ADDR);                  /* page 0xFFFFD000: D350..D3A8, D500 */
    map_page(F754_ADDR);

    while (fgets(line, sizeof line, stdin)) {
        unsigned long boost, cmd0, mask, st, magic, src, cnt, inp;
        unsigned long latch, ptrcell, f754, on, hyst;
        int n = sscanf(line,
                       "vfad %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx",
                       &boost, &cmd0, &mask, &st, &magic, &src, &cnt, &inp,
                       &latch, &ptrcell, &f754, &on, &hyst);
        if (n != 13) {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }

        /* Seed the ROM calibration table exactly as the stock bin has it. */
        *(volatile uint32_t *)(uintptr_t)ROM_ON_ADDR   = (uint32_t)on;
        *(volatile uint32_t *)(uintptr_t)ROM_HYST_ADDR = (uint32_t)hyst;

        /* Seed the SM descriptor (stored output pointer -> PTR_CELL). */
        *(volatile uint8_t  *)(uintptr_t)SM_MASK_ADDR = (uint8_t)mask;
        *(volatile uint32_t *)(uintptr_t)SM_PTR_ADDR  = (uint32_t)PTR_CELL;

        /* Seed the input RAM cells + the SM pre-states. */
        *(volatile uint32_t *)(uintptr_t)BOOST_ADDR   = (uint32_t)boost;
        *(volatile uint8_t  *)(uintptr_t)CMD_ADDR     = (uint8_t)cmd0;
        *(volatile uint8_t  *)(uintptr_t)ST_ADDR      = (uint8_t)st;
        *(volatile uint16_t *)(uintptr_t)MAGIC_ADDR   = (uint16_t)magic;
        *(volatile uint16_t *)(uintptr_t)SRC_ADDR     = (uint16_t)src;
        *(volatile uint8_t  *)(uintptr_t)CNT_ADDR     = (uint8_t)cnt;
        *(volatile uint8_t  *)(uintptr_t)INP_ADDR     = (uint8_t)inp;
        *(volatile uint8_t  *)(uintptr_t)LATCH_ADDR   = (uint8_t)latch;
        *(volatile uint8_t  *)(uintptr_t)PTR_CELL     = (uint8_t)ptrcell;
        *(volatile uint16_t *)(uintptr_t)F754_ADDR    = (uint16_t)f754;

        rx8_vfad_control_35bbc();

        printf("%02X %04X %02X %02X %02X\n",
               *(volatile uint8_t  *)(uintptr_t)CMD_ADDR,
               *(volatile uint16_t *)(uintptr_t)F754_ADDR,
               *(volatile uint8_t  *)(uintptr_t)ST_ADDR,
               *(volatile uint8_t  *)(uintptr_t)LATCH_ADDR,
               *(volatile uint8_t  *)(uintptr_t)PTR_CELL);
    }
    return 0;
}

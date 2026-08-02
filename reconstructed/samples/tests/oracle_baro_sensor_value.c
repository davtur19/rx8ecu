/* ============================================================================
 * oracle_baro_sensor_value.c  —  host rig for rx8_baro_sensor_value @0xD144
 * ============================================================================
 * Compile together with src/rx8_baro_sensor_value.c and pipe test vectors on
 * stdin; one vector per line, whitespace-separated hex tokens:
 *
 *     bsv <bank> <val> <pre0> <pre1>   ->   <mboxA> <mboxB>
 *
 *   bank  : RAM-less register argument r4 (u8, only the low byte is used)
 *   val   : RAM-less register argument r5 (u16, only the low half is used)
 *   pre0  : u16 pre-state of MMIO[0xFFFFE40A] (mailbox-A data word)
 *   pre1  : u16 pre-state of MMIO[0xFFFFE60A] (mailbox-B data word)
 *
 * Output: the two post-state MMIO words, so the harness can check that the
 * selected register was overwritten with the byte-swapped value and the
 * unselected one is left byte-identical (the ROM never touches it).
 *
 * The oracle re-implements only the *caller-side* set-up: it mmap()s the page
 * backing the two MMIO cells (0xFFFFE40A/0xFFFFE60A both live in the 4K page
 * 0xFFFFE000), seeds every byte big-endian exactly like the SH-2E emulator's
 * ram overlay and prints the two post-state words, also assembled big-endian.
 * It contains NO copy of the function logic — that lives solely in the
 * reconstructed source under test.  No ROM calibration page is needed: the
 * three constants of this function (0xE40A, 0xE60A, 0x0000FF00) are 16/32-bit
 * immediates in the ROM body's literal pool, hard-coded here as the two target
 * addresses and the swap expression.
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

#include "rx8_samples.h"

/* rx8_baro_sensor_value is not (yet) declared in rx8_samples.h — the shared
 * header is owned by the samples build.  The reconstructed source itself
 * carries the authoritative definition (src/...c); this prototype mirrors it
 * exactly. */
void rx8_baro_sensor_value(uint8_t bank, uint16_t value);

#define MBOX_A_ADDR  0xFFFFE40Au   /* u16 mailbox-A data word */
#define MBOX_B_ADDR  0xFFFFE60Au   /* u16 mailbox-B data word */

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

/* Big-endian u16 accessors: byte-exact mirrors of the SH-2E `mov.w` store and
 * the emulator's rd(addr, 2), so the host sees the same bytes the emulator
 * does regardless of host endianness. */
static void be16_store(uint32_t addr, uint16_t v)
{
    *(volatile uint8_t *)(uintptr_t)addr       = (uint8_t)(v >> 8);
    *(volatile uint8_t *)(uintptr_t)(addr + 1u) = (uint8_t)(v & 0xFFu);
}

static uint16_t be16_load(uint32_t addr)
{
    return (uint16_t)(((uint16_t)*(volatile uint8_t *)(uintptr_t)addr << 8) |
                      (uint16_t)*(volatile uint8_t *)(uintptr_t)(addr + 1u));
}

int main(void)
{
    char line[128];

    /* Both cells live in the same 4K page; one mmap backs both. */
    map_page(MBOX_A_ADDR);

    while (fgets(line, sizeof line, stdin)) {
        unsigned long bank, val, pre0, pre1;

        if (sscanf(line, "bsv %lx %lx %lx %lx",
                   &bank, &val, &pre0, &pre1) != 4) {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }

        /* Seed the two MMIO pre-states (big-endian bytes). */
        be16_store(MBOX_A_ADDR, (uint16_t)pre0);
        be16_store(MBOX_B_ADDR, (uint16_t)pre1);

        rx8_baro_sensor_value((uint8_t)bank, (uint16_t)val);

        printf("%04X %04X\n",
               (unsigned)be16_load(MBOX_A_ADDR),
               (unsigned)be16_load(MBOX_B_ADDR));
    }
    return 0;
}

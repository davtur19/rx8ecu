/* ============================================================================
 * oracle_iat_sensor.c  —  host rig for rx8_iat_sensor @0x3C214
 * ============================================================================
 * Compile together with samples/src/rx8_iat_sensor.c and pipe test vectors
 * on stdin; one vector per line, whitespace-separated hex tokens:
 *
 *     iat <c5ec> <c5ed> <c5ee> <c5ef> <c5f0> <c5f7> <d201> <c5f8_0> <c5f9_0>
 *                                       -> <c5f4> <c5f5> <c5f6> <c5f8> <c5f9>
 *
 *   c5ec/c5ed/c5ee : compare-channel inputs  RAM8[0xFFFFC5EC/C5ED/C5EE]
 *   c5ef/c5f0      : status arm-threshold inputs RAM8[0xFFFFC5EF/C5F0]
 *   c5f7           : fault-active input      RAM8[0xFFFFC5F7]
 *   d201           : reset-request input     RAM8[0xFFFFD201]
 *   c5f8_0/c5f9_0  : pre-state of the two status bytes (they HOLD LAST VALUE
 *                    when neither the clear nor the arm condition fires)
 *
 * The oracle re-implements only the *caller-side* set-up: it mmap()s the
 * pages backing the RAM cells AND the ROM calibration page (threshold bytes
 * 0x7A9A8/0x7A9A9, seeded from the ROM file), seeds every byte and prints
 * the five post-state cells.  It contains NO copy of the function logic —
 * that lives solely in the reconstructed source under test.
 *
 * Pages mapped (all above mmap_min_addr on this host):
 *   0x0007A000  ROM calibration table (0x7A9A8, 0x7A9A9)
 *   0xFFFFC000  RAM[0xFFFFC5EC..0xFFFFC5F9] (inputs + flags + status)
 *   0xFFFFD000  RAM[0xFFFFD201] (reset request)
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/mman.h>

#include "rx8_samples.h"

/* rx8_iat_sensor is not (yet) in rx8_samples.h — the shared header is owned
 * by the samples build.  The reconstructed source itself carries the
 * authoritative definition (src/rx8_iat_sensor.c); this prototype mirrors
 * it exactly. */
void rx8_iat_sensor(void);

#define IAT_RESET_ADDR    0xFFFFD201u   /* u8 reset request            */
#define IAT_CMP_A_ADDR    0xFFFFC5ECu   /* u8 compare-channel A input  */
#define IAT_CMP_B_ADDR    0xFFFFC5EDu   /* u8 compare-channel B input  */
#define IAT_CMP_C_ADDR    0xFFFFC5EEu   /* u8 compare-channel C input  */
#define IAT_ST1_THR_ADDR  0xFFFFC5EFu   /* u8 status-1 arm-thr input   */
#define IAT_ST2_THR_ADDR  0xFFFFC5F0u   /* u8 status-2 arm-thr input   */
#define IAT_FAULT_ADDR    0xFFFFC5F7u   /* u8 fault-active input       */
#define IAT_FLAG_A_ADDR   0xFFFFC5F4u   /* u8 output flag A            */
#define IAT_FLAG_B_ADDR   0xFFFFC5F5u   /* u8 output flag B            */
#define IAT_FLAG_C_ADDR   0xFFFFC5F6u   /* u8 output flag C            */
#define IAT_ST1_ADDR      0xFFFFC5F8u   /* u8 status byte 1            */
#define IAT_ST2_ADDR      0xFFFFC5F9u   /* u8 status byte 2            */

#define ROM_CAL_PAGE      0x0007A000u   /* page backing 0x7A9A8/0x7A9A9 */
#define ROM_CAL_THR0      0x0007A9A8u
#define ROM_CAL_THR1      0x0007A9A9u

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
    const char *rom_path = getenv("RX8_ROM_PATH");
    char line[128];
    unsigned char b[1];
    int romfd;

    if (!rom_path)
        rom_path = "../../../roms/stock/60E1D400.bin";
    romfd = open(rom_path, O_RDONLY);
    if (romfd < 0) {
        perror(rom_path);
        return 2;
    }

    /* ROM calibration page: seed the two threshold bytes from the bin. */
    map_page(ROM_CAL_PAGE);
    if (pread(romfd, b, 1, ROM_CAL_THR0) != 1) { perror("pread 0x7A9A8"); return 2; }
    *(volatile uint8_t *)(uintptr_t)ROM_CAL_THR0 = b[0];
    if (pread(romfd, b, 1, ROM_CAL_THR1) != 1) { perror("pread 0x7A9A9"); return 2; }
    *(volatile uint8_t *)(uintptr_t)ROM_CAL_THR1 = b[0];
    close(romfd);

    /* RAM pages backing the inputs, flags, status bytes and reset request. */
    map_page(IAT_CMP_A_ADDR);
    map_page(IAT_RESET_ADDR);

    while (fgets(line, sizeof line, stdin)) {
        unsigned long c5ec, c5ed, c5ee, c5ef, c5f0, c5f7, d201, st10, st20;

        if (sscanf(line,
                   "iat %lx %lx %lx %lx %lx %lx %lx %lx %lx",
                   &c5ec, &c5ed, &c5ee, &c5ef, &c5f0, &c5f7, &d201, &st10, &st20)
            != 9) {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }

        /* Seed the input cells + the status-byte pre-states. */
        *(volatile uint8_t *)(uintptr_t)IAT_CMP_A_ADDR   = (uint8_t)c5ec;
        *(volatile uint8_t *)(uintptr_t)IAT_CMP_B_ADDR   = (uint8_t)c5ed;
        *(volatile uint8_t *)(uintptr_t)IAT_CMP_C_ADDR   = (uint8_t)c5ee;
        *(volatile uint8_t *)(uintptr_t)IAT_ST1_THR_ADDR = (uint8_t)c5ef;
        *(volatile uint8_t *)(uintptr_t)IAT_ST2_THR_ADDR = (uint8_t)c5f0;
        *(volatile uint8_t *)(uintptr_t)IAT_FAULT_ADDR   = (uint8_t)c5f7;
        *(volatile uint8_t *)(uintptr_t)IAT_RESET_ADDR   = (uint8_t)d201;
        *(volatile uint8_t *)(uintptr_t)IAT_ST1_ADDR     = (uint8_t)st10;
        *(volatile uint8_t *)(uintptr_t)IAT_ST2_ADDR     = (uint8_t)st20;

        rx8_iat_sensor();

        printf("%02X %02X %02X %02X %02X\n",
               *(volatile uint8_t *)(uintptr_t)IAT_FLAG_A_ADDR,
               *(volatile uint8_t *)(uintptr_t)IAT_FLAG_B_ADDR,
               *(volatile uint8_t *)(uintptr_t)IAT_FLAG_C_ADDR,
               *(volatile uint8_t *)(uintptr_t)IAT_ST1_ADDR,
               *(volatile uint8_t *)(uintptr_t)IAT_ST2_ADDR);
    }
    return 0;
}

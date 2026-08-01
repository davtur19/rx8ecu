/* ============================================================================
 * oracle_knock_sensor_adc_fault.c — host rig for rx8_knock_sensor_adc_fault
 * ============================================================================
 * Compile together with src/rx8_knock_sensor_adc_fault.c and pipe test vectors
 * on stdin; one vector per line, whitespace-separated hex tokens:
 *
 *     knock <adc> <open> <shrt>        -> <out_byte>
 *
 *   adc  : knock-sensor ADC count (16-bit) written to the RAM cell the ROM
 *          reads (0xFFFF9F0E)
 *   open : over-range threshold, written to 0x0006CF7E (the exact ROM
 *          location 60E1D400.bin's literal pool points at)
 *   shrt : under-range threshold, written to 0x0006CF7C
 *
 * The oracle mirrors the *caller-side* set-up only: it mmap()s the pages
 * backing the two RAM cells and the two ROM threshold slots (same MAP_FIXED
 * trick as tests/host_oracle.c), seeds them, runs the reconstructed C and
 * prints the one-byte fault code it wrote to 0xFFFFA325.  It contains NO copy
 * of the function logic — that lives solely in the reconstructed source under
 * test.
 *
 * NOTE: rx8_knock_sensor_adc_fault is declared here rather than in
 * rx8_samples.h (which is off-limits for this task) — the reconstructed name
 * maps to the ROM function at 0xC460 in 60E1D400.bin / 0xC290 in
 * 60E0FC00.bin (see rx8_knock_sensor_adc_fault.c).
 * ==========================================================================*/
#include <stdint.h>
#include <stdio.h>
#include <sys/mman.h>
#include <unistd.h>

#include "rx8_samples.h"

/* 0xC460 (60E1D400.bin) — knock-sensor ADC range check + fault code
 * (see rx8_knock_sensor_adc_fault.c). */
void rx8_knock_sensor_adc_fault(void);

#define ADC_ADDR    0xFFFF9F0Eu   /* u16 knock-sensor ADC sample (RAM) */
#define OUT_ADDR    0xFFFFA325u   /* u8  fault-code byte (RAM)         */
#define OPEN_ADDR   0x0006CF7Eu   /* u16 over-range threshold (ROM)    */
#define SHRT_ADDR   0x0006CF7Cu   /* u16 under-range threshold (ROM)   */

static void map_page(uintptr_t addr)
{
    long page = sysconf(_SC_PAGESIZE);
    uintptr_t base = addr & ~((uintptr_t)page - 1);
    void *p = mmap((void *)base, (size_t)page, PROT_READ | PROT_WRITE,
                   MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED, -1, 0);
    if (p == MAP_FAILED) {
        perror("mmap");
        return;
    }
}

int main(void)
{
    char line[256];

    /* 0x6C000 backs the ROM threshold slots (above this host's mmap_min_addr),
     * 0xFFFF9000 and 0xFFFFA000 back the two RAM cells. */
    map_page(OPEN_ADDR);
    map_page(ADC_ADDR);
    map_page(OUT_ADDR);

    while (fgets(line, sizeof line, stdin)) {
        unsigned long adc, open, shrt;

        if (sscanf(line, "knock %lx %lx %lx", &adc, &open, &shrt) == 3) {
            *(volatile uint16_t *)(uintptr_t)ADC_ADDR  = (uint16_t)adc;
            *(volatile uint16_t *)(uintptr_t)OPEN_ADDR = (uint16_t)open;
            *(volatile uint16_t *)(uintptr_t)SHRT_ADDR = (uint16_t)shrt;
            *(volatile uint8_t  *)(uintptr_t)OUT_ADDR  = 0x55;   /* sentinel */

            rx8_knock_sensor_adc_fault();

            printf("%02X\n", *(volatile uint8_t *)(uintptr_t)OUT_ADDR);
        } else {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
    }
    return 0;
}

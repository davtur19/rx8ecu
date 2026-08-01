/* test_temperature_gauge_0x5AA5C.c
 *
 * Host C companion for temperature_gauge_0x5AA5C (0x5AA5C).
 *
 * The lift reads a status byte at 0xFFFFCD4C and writes a gauge value byte
 * to 0xFFFFD2C4.  Both SFRs are mapped with mmap(MAP_FIXED) on the host
 * (same trick as test_calc_manifold_pressure_error_clamp_10A5C.c).
 *
 * Reference: v = (b & 0x7C) ? 7 : (b & 0x80) ? 6 : 0.
 */

#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

extern void temperature_gauge_0x5AA5C(void);

#define IN_BYTE  0xFFFFCD4Cu  /* input  status byte  */
#define OUT_BYTE 0xFFFFD2C4u  /* output gauge byte   */

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

static uint8_t ref(uint8_t b)
{
    return (b & 0x7C) ? 7 : (b & 0x80) ? 6 : 0;
}

int main(void)
{
    unsigned failures = 0, tests = 0;

    map_page(IN_BYTE);
    map_page(OUT_BYTE);

    printf("=== temperature_gauge_0x5AA5C ===\n");

    /* Exhaustive: all 256 input byte values. */
    for (unsigned b = 0; b < 256; b++) {
        *(volatile uint8_t *)IN_BYTE = (uint8_t)b;
        *(volatile uint8_t *)OUT_BYTE = 0xFF;  /* poison */
        temperature_gauge_0x5AA5C();
        uint8_t got = *(volatile uint8_t *)OUT_BYTE;
        uint8_t exp = ref((uint8_t)b);
        tests++;
        if (got != exp) {
            printf("FAIL: in=0x%02X out=0x%02X expected 0x%02X\n", b, got, exp);
            failures++;
        }
    }

    printf("Results: %u tests, %u failures\n", tests, failures);
    return failures ? 1 : 0;
}

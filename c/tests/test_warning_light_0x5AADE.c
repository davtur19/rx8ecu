/* test_warning_light_0x5AADE.c
 *
 * Host C companion for warning_light_0x5AADE (0x5AADE).
 *
 * The lift reads a status byte at 0xFFFFCD4C and writes a warning-light
 * value byte to 0xFFFFD2C5.  Both SFRs are mapped with mmap(MAP_FIXED).
 *
 * Reference: v = (b & 0x60) ? 0x6D : (b & 0x1C) ? 0x69 : (b & 0x80) ? 0x68 : 0.
 */

#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

extern void warning_light_0x5AADE(void);

#define IN_BYTE  0xFFFFCD4Cu  /* input  status byte       */
#define OUT_BYTE 0xFFFFD2C5u  /* output warning-light byte */

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
    return (b & 0x60) ? 0x6D : (b & 0x1C) ? 0x69 : (b & 0x80) ? 0x68 : 0;
}

int main(void)
{
    unsigned failures = 0, tests = 0;

    map_page(IN_BYTE);
    map_page(OUT_BYTE);

    printf("=== warning_light_0x5AADE ===\n");

    for (unsigned b = 0; b < 256; b++) {
        *(volatile uint8_t *)IN_BYTE = (uint8_t)b;
        *(volatile uint8_t *)OUT_BYTE = 0xFF;  /* poison */
        warning_light_0x5AADE();
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

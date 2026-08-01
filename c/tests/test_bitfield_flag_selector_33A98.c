/* test_bitfield_flag_selector_33A98.c
 *
 * Host C companion for bitfield_flag_selector_33A98 (0x33A98).
 *
 * The lift reads a status byte at 0xFFFFCD4E and writes a select code into
 * the top nibble of byte@0xFFFFC05C.  Both SFRs are mapped with mmap.
 *
 * Reference: v = (b & 0x40) ? 0 : (b & 0x20) ? 1 : (b & 0x80) ? 2 : 3;
 *            out = v << 4.
 */

#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

extern void bitfield_flag_selector_33A98(void);

#define IN_BYTE  0xFFFFCD4Eu  /* input  status byte      */
#define OUT_BYTE 0xFFFFC05Cu  /* output select code byte */

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
    uint8_t v = (b & 0x40) ? 0 : (b & 0x20) ? 1 : (b & 0x80) ? 2 : 3;
    return (uint8_t)(v << 4);
}

int main(void)
{
    unsigned failures = 0, tests = 0;

    map_page(IN_BYTE);
    map_page(OUT_BYTE);

    printf("=== bitfield_flag_selector_33A98 ===\n");

    for (unsigned b = 0; b < 256; b++) {
        *(volatile uint8_t *)IN_BYTE = (uint8_t)b;
        *(volatile uint8_t *)OUT_BYTE = 0xFF;  /* poison */
        bitfield_flag_selector_33A98();
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

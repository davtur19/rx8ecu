/* test_calibration_apply_4B770.c
 *
 * Host C companion for calibration_apply_4B770 (0x4B770).
 *
 * The lift reads three input bytes (0xFFFFD201, 0xFFFFCE00, 0xFFFFCE01)
 * and writes one flag byte (0xFFFFCDFD).  All four live in page 0xFFFFC000
 * (0xFFFFCE00/01, 0xFFFFCDFD) and page 0xFFFFD000 (0xFFFFD201), mapped
 * MAP_FIXED.
 *
 * Reference: v = (b201 != 1 && bCE00 == 0 && bCE01 == 0) ? 1 : 0.
 */

#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

extern void calibration_apply_4B770(void);

#define IN_B201 0xFFFFD201u
#define IN_CE00 0xFFFFCE00u
#define IN_CE01 0xFFFFCE01u
#define OUT     0xFFFFCDFDu

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

static uint8_t ref(uint8_t b201, uint8_t bce00, uint8_t bce01)
{
    return (b201 != 1 && bce00 == 0 && bce01 == 0) ? 1 : 0;
}

int main(void)
{
    unsigned failures = 0, tests = 0;

    map_page(0xFFFFC000);
    map_page(0xFFFFD000);

    printf("=== calibration_apply_4B770 ===\n");

    static const uint8_t iv[] = {0x00, 0x01, 0x02, 0x80, 0xFF};
    for (size_t a = 0; a < sizeof(iv) / sizeof(iv[0]); a++)
        for (size_t b = 0; b < sizeof(iv) / sizeof(iv[0]); b++)
            for (size_t c = 0; c < sizeof(iv) / sizeof(iv[0]); c++) {
                *(volatile uint8_t *)IN_B201 = iv[a];
                *(volatile uint8_t *)IN_CE00 = iv[b];
                *(volatile uint8_t *)IN_CE01 = iv[c];
                *(volatile uint8_t *)OUT = 0xFF;  /* poison */
                calibration_apply_4B770();
                uint8_t got = *(volatile uint8_t *)OUT;
                uint8_t exp = ref(iv[a], iv[b], iv[c]);
                tests++;
                if (got != exp) {
                    printf("FAIL: in=(%02X,%02X,%02X) out=0x%02X expected 0x%02X\n",
                           iv[a], iv[b], iv[c], got, exp);
                    failures++;
                }
            }

    srand(42);
    for (int i = 0; i < 20000; i++) {
        uint8_t a = (uint8_t)rand(), b = (uint8_t)rand(), c = (uint8_t)rand();
        *(volatile uint8_t *)IN_B201 = a;
        *(volatile uint8_t *)IN_CE00 = b;
        *(volatile uint8_t *)IN_CE01 = c;
        *(volatile uint8_t *)OUT = 0xFF;
        calibration_apply_4B770();
        uint8_t got = *(volatile uint8_t *)OUT;
        uint8_t exp = ref(a, b, c);
        tests++;
        if (got != exp) {
            printf("FAIL: in=(%02X,%02X,%02X) out=0x%02X expected 0x%02X\n",
                   a, b, c, got, exp);
            failures++;
            break;
        }
    }

    printf("Results: %u tests, %u failures\n", tests, failures);
    return failures ? 1 : 0;
}

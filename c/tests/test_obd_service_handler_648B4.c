/* test_obd_service_handler_648B4.c
 *
 * Host C companion for obd_service_handler_648B4 (0x648B4).
 *
 * Run-sum update over the two redundant 16-bit cells 0xFFFF8E98 and
 * 0xFFFF8E9A (both in page 0xFFFF8000, mapped MAP_FIXED):
 *
 *   b   = r4 & 0xFF
 *   sum = (s8(byte@0xFFFF8E98) + s8(byte@0xFFFF8E9A) - s8(b)) & 0xFF
 *   word@0xFFFF8E98 = enc8(sum);  word@0xFFFF8E9A = enc8(b)
 *
 * enc8(x) = (x << 8) | ~x  (the 0x2420 value/complement encoder).
 */

#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

extern void obd_service_handler_648B4(uint32_t r4);

#define A 0xFFFF8E98u
#define B 0xFFFF8E9Au

static void map_page(uintptr_t addr)
{
    long page = sysconf(_SC_PAGESIZE);
    uintptr_t base = addr & ~((uintptr_t)page - 1);
    void *p = mmap((void *)base, (size_t)page, PROT_READ | PROT_WRITE,
                   MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED, -1, 0);
    if (p == MAP_FAILED) { perror("mmap"); exit(1); }
}

static uint16_t enc8(uint8_t x) { return (uint16_t)((x << 8) | (uint8_t)~x); }

static int check(uint32_t r4, uint16_t wa, uint16_t wb)
{
    *(volatile uint16_t *)A = wa;
    *(volatile uint16_t *)B = wb;

    uint8_t b = r4 & 0xFFu;
    uint16_t ea = enc8((uint8_t)((int32_t)(int8_t)((wa >> 8) & 0xFF)
                                  + (int32_t)(int8_t)((wb >> 8) & 0xFF)
                                  - (int32_t)(int8_t)b));
    uint16_t eb = enc8(b);

    obd_service_handler_648B4(r4);

    uint16_t ga = *(volatile uint16_t *)A;
    uint16_t gb = *(volatile uint16_t *)B;
    if (ga != ea || gb != eb) {
        printf("FAIL: r4=%08X wa=%04X wb=%04X -> (%04X,%04X) expected (%04X,%04X)\n",
               r4, wa, wb, ga, gb, ea, eb);
        return 1;
    }
    return 0;
}

int main(void)
{
    unsigned failures = 0, tests = 0;
    map_page(0xFFFF8000);
    printf("=== obd_service_handler_648B4 ===\n");

    static const uint8_t vals[] = {0x00, 0x01, 0x7F, 0x80, 0xFE, 0xFF};
    static const uint16_t words[] = {0x0000, 0x00FF, 0x7F80, 0x807F, 0xFFFF, 0xFF00};
    for (size_t a = 0; a < sizeof(vals) / sizeof(vals[0]); a++)
        for (size_t b = 0; b < sizeof(words) / sizeof(words[0]); b++)
            for (size_t c = 0; c < sizeof(words) / sizeof(words[0]); c++) {
                tests++;
                failures += check(vals[a], words[b], words[c]);
            }

    srand(0x648B4);
    for (int i = 0; i < 20000; i++) {
        tests++;
        failures += check((uint32_t)rand(), (uint16_t)rand(), (uint16_t)rand());
    }

    printf("Results: %u tests, %u failures\n", tests, failures);
    return failures ? 1 : 0;
}

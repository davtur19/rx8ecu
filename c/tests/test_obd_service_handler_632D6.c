/* test_obd_service_handler_632D6.c
 *
 * Host C companion for obd_service_handler_632D6 (0x632D6).
 *
 * Pending-flag clear leaf: if byte@0xFFFF87CC == 1 the 16-bit cell at
 * 0xFFFF87CC is rewritten as enc8(0) = 0x00FF; otherwise untouched.
 * The cell is in page 0xFFFF8000 (mapped MAP_FIXED).
 *
 * The cell is accessed as a uint16_t VALUE: byte@0xFFFF87CC is the high byte
 * (>>8) of that value (big-endian ROM semantics), and the host build stores
 * the same value with native host endianness — so all seeding/checking goes
 * through *(volatile uint16_t *) and never through raw byte stores (see
 * obd_dtc_row_update_0x64490 for the same convention).
 */

#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

extern void obd_service_handler_632D6(void);

#define FLAG 0xFFFF87CCu

static void map_page(uintptr_t addr)
{
    long page = sysconf(_SC_PAGESIZE);
    uintptr_t base = addr & ~((uintptr_t)page - 1);
    void *p = mmap((void *)base, (size_t)page, PROT_READ | PROT_WRITE,
                   MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED, -1, 0);
    if (p == MAP_FAILED) { perror("mmap"); exit(1); }
}

static int check(uint8_t flag, uint8_t pad)
{
    /* value with flag as high byte = byte@FLAG in ROM semantics */
    uint16_t seeded = (uint16_t)(((uint16_t)flag << 8) | pad);
    *(volatile uint16_t *)FLAG = seeded;

    obd_service_handler_632D6();

    uint16_t got = *(volatile uint16_t *)FLAG;
    if (flag == 0x01) {
        uint16_t exp = (uint16_t)((0 << 8) | (uint8_t)~0);   /* 0x00FF */
        if (got != exp) {
            printf("FAIL: flag=%02X pad=%02X -> %04X expected %04X\n",
                   flag, pad, got, exp);
            return 1;
        }
    } else if (got != seeded) {
        printf("FAIL: flag=%02X pad=%02X unchanged -> %04X expected %04X\n",
               flag, pad, got, seeded);
        return 1;
    }
    return 0;
}

int main(void)
{
    unsigned failures = 0, tests = 0;
    map_page(0xFFFF8000);
    printf("=== obd_service_handler_632D6 ===\n");

    for (int flag = 0; flag < 256; flag++)
        for (size_t i = 0; i < 4; i++) {
            static const uint8_t pads[] = {0x00, 0x01, 0xAA, 0xFF};
            tests++;
            failures += check((uint8_t)flag, pads[i]);
        }

    srand(0x632D6);
    for (int i = 0; i < 20000; i++) {
        tests++;
        failures += check((uint8_t)rand(), (uint8_t)rand());
    }

    printf("Results: %u tests, %u failures\n", tests, failures);
    return failures ? 1 : 0;
}

/* test_req_queue_69602.c
 *
 * Host C companion for req_queue store (0x69602) / clear (0x69694).
 *
 * Flag array 0xFFFFDE38 (page 0xFFFFD000), value array 0xFFFFDE40
 * (page 0xFFFFD000, spilling into page 0xFFFFE000 for b >= 0x70), and the
 * 32-bit base at 0xFFFFF430 (page 0xFFFFF000) are mapped MAP_FIXED.
 * All 256 indices are covered.
 *
 * Reference:
 *   store: v = (uint32)(r5 * 0x0FA0) + long@0xFFFFF430; flag = 1
 *   clear: flag = 0
 */

#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

extern void req_queue_store_69602(uint32_t r4, uint32_t r5);
extern void req_queue_clear_69694(uint32_t r4);

#define FLAGS  0xFFFFDE38u
#define VALUES 0xFFFFDE40u
#define BASE   0xFFFFF430u

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

static uint32_t rd32(uintptr_t a)
{
    return *(volatile uint32_t *)a;
}

int main(void)
{
    unsigned failures = 0, tests = 0;

    map_page(0xFFFFD000);
    map_page(0xFFFFE000);
    map_page(0xFFFFF000);

    printf("=== req_queue_69602 ===\n");

    srand(42);

    /* store: all 256 indices with varied base + r5 */
    for (unsigned b = 0; b < 256; b++) {
        uint32_t basev = (uint32_t)rand();
        uint32_t r5 = (uint32_t)rand();
        *(volatile uint32_t *)BASE = basev;
        *(volatile uint8_t *)(FLAGS + b) = 0;
        req_queue_store_69602(b, r5);
        uint32_t exp = ((uint32_t)r5 * 0x0FA0u) + basev;
        uint32_t got = rd32(VALUES + b * 4);
        if (got != exp || *(volatile uint8_t *)(FLAGS + b) != 1) {
            printf("FAIL store b=%u r5=%08X base=%08X got=%08X exp=%08X\n",
                   b, r5, basev, got, exp);
            failures++;
            break;
        }
        tests++;
    }

    /* clear: all 256 indices */
    for (unsigned b = 0; b < 256; b++) {
        *(volatile uint8_t *)(FLAGS + b) = 1;
        req_queue_clear_69694(b);
        if (*(volatile uint8_t *)(FLAGS + b) != 0) {
            printf("FAIL clear b=%u\n", b);
            failures++;
            break;
        }
        tests++;
    }

    /* random interleave */
    for (int i = 0; i < 20000; i++) {
        unsigned b = (unsigned)(rand() & 0xFF);
        if (rand() & 1) {
            uint32_t basev = (uint32_t)rand();
            uint32_t r5 = (uint32_t)rand();
            *(volatile uint32_t *)BASE = basev;
            *(volatile uint8_t *)(FLAGS + b) = 0;
            req_queue_store_69602(b, r5);
            uint32_t exp = ((uint32_t)r5 * 0x0FA0u) + basev;
            if (rd32(VALUES + b * 4) != exp || *(volatile uint8_t *)(FLAGS + b) != 1) {
                printf("FAIL rnd store b=%u\n", b);
                failures++;
                break;
            }
        } else {
            *(volatile uint8_t *)(FLAGS + b) = (uint8_t)rand();
            req_queue_clear_69694(b);
            if (*(volatile uint8_t *)(FLAGS + b) != 0) {
                printf("FAIL rnd clear b=%u\n", b);
                failures++;
                break;
            }
        }
        tests++;
    }

    printf("Results: %u tests, %u failures\n", tests, failures);
    return failures ? 1 : 0;
}

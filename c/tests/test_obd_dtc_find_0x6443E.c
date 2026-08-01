/* test_obd_dtc_find_0x6443E.c
 *
 * Host C companion for obd_dtc_find_0x6443E (0x6443E).
 *
 * The DTC table (0xFFFF8930, 21 rows x 0x34) and the row-index word
 * (0xFFFF8D74) all live in page 0xFFFF8000, mapped MAP_FIXED.
 *
 * Reference: first i with byte@row+0x06 == (r4 & 0xFF) && i != currow
 *            returns s8(byte@row+0x08); else 0x08.
 */

#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

extern int32_t obd_dtc_find_0x6443E(uint32_t r4);

#define BASE     0xFFFF8930u
#define STRIDE   0x34u
#define ROWS     0x15u
#define CURROW   0xFFFF8D74u

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

static uint8_t *rowp(uint32_t i) { return (uint8_t *)(BASE + i * STRIDE); }

static int32_t ref(uint32_t r4, uint16_t currow)
{
    for (uint32_t i = 0; i < ROWS; i++) {
        if (rowp(i)[0x06] == (uint8_t)r4 && i != currow)
            return (int32_t)(int8_t)rowp(i)[0x08];
    }
    return 0x08;
}

int main(void)
{
    unsigned failures = 0, tests = 0;

    map_page(0xFFFF8000);

    printf("=== obd_dtc_find_0x6443E ===\n");

    srand(42);
    for (int iter = 0; iter < 5000; iter++) {
        uint16_t currow = (uint16_t)(rand() & (ROWS - 1));
        for (uint32_t i = 0; i < ROWS; i++) {
            rowp(i)[0x06] = (uint8_t)rand();
            rowp(i)[0x08] = (uint8_t)rand();
        }
        *(volatile uint16_t *)CURROW = currow;
        uint32_t r4 = (uint32_t)(rand() & 0xFF);
        /* force a guaranteed hit every 3rd iteration */
        if (iter % 3 == 0) {
            uint32_t i = (uint32_t)(rand() % ROWS);
            if (i != currow) {
                rowp(i)[0x06] = (uint8_t)r4;
            } else {
                rowp((i + 1) % ROWS)[0x06] = (uint8_t)r4;
            }
        }
        tests++;
        int32_t got = obd_dtc_find_0x6443E(r4);
        int32_t exp = ref(r4, currow);
        if (got != exp) {
            printf("FAIL: iter=%d r4=%02X currow=%u got=%d expected=%d\n",
                   iter, r4, currow, got, exp);
            failures++;
            break;
        }
    }

    printf("Results: %u tests, %u failures\n", tests, failures);
    return failures ? 1 : 0;
}

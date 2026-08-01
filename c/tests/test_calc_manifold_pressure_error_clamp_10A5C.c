/* test_calc_manifold_pressure_error_clamp_10A5C.c
 *
 * Behavioral verification for calc_manifold_pressure_error_clamp_10A5C.
 *
 * This function is a pure fixed-point wrapping computation:
 *   result = (sensor_byte * 0x1E0000 - input - 0x50000) % 0x2D00000
 *
 * The wrapping uses conditional add/subtract of 0x2D00000 rather than
 * an actual modulo operator, matching the SH-2E implementation.
 */

#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

/* The lift under test is compiled in by the Makefile (c/<name>.c + test),
 * so declare its prototype here instead of #include-ing the .c (which would
 * be a duplicate definition). */
extern uint32_t calc_manifold_pressure_error_clamp_10A5C(uint32_t input);

/* The lift reads the raw sensor byte from a hardcoded RAM address
 * (0xFFFFA5D4, SH-2 memory-mapped RAM).  On the host that address is not
 * mapped, so map one page there with mmap(MAP_FIXED) and back it with a
 * plain byte so the lift and the reference both observe it. */
#define SENSOR_ADDR 0xFFFFA5D4u

static void map_sensor_ram(void)
{
    long page = sysconf(_SC_PAGESIZE);
    uintptr_t base = (uintptr_t)(SENSOR_ADDR & ~((uintptr_t)page - 1));
    void *p = mmap((void *)base, (size_t)page, PROT_READ | PROT_WRITE,
                   MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED, -1, 0);
    if (p == MAP_FAILED) {
        perror("mmap sensor RAM");
        exit(1);
    }
    *(volatile uint8_t *)SENSOR_ADDR = 0;
}

/* Reference implementation — byte-exact transcription of SH-2E instructions */
static uint32_t ref_calc_manifold_pressure_error_clamp_10A5C(uint32_t input)
{
    uint32_t raw_val, r2, r3, r4, r5, r0;

    /* mov.l @(0xDC,pc),r1  — r1 = 0xFFFFA5D4 (literal pool address)
     * mov.b @r1,r2         — r2 = [0xFFFFA5D4] */
    raw_val = *(volatile uint8_t *)0xFFFFA5D4;
    r2 = raw_val;

    /* mov.l @(0xDC,pc),r3  — r3 = 0x001E0000
     * extu.b r2,r2         — r2 = unsigned byte (already)
     * mov.l @(0xDE,pc),r5  — r5 = 0x02D00000
     * mul.l r3,r2          — macl = r2 * 0x1E0000
     * sts macl,r2          — r2 = macl */
    r3 = 0x001E0000u;
    r5 = 0x02D00000u;
    r2 = (raw_val & 0xFF) * r3;

    /* sub r4,r2            — r2 = r2 - r4 (input) */
    r2 = r2 - input;

    /* mov.l @(0xD8,pc),r4  — r4 = 0xFFFB0000
     * add r2,r4            — r4 = r2 + r4 */
    r4 = 0xFFFB0000u;
    r4 = r2 + r4;

    /* cmp/ge r5,r4         — compare (signed)r4 >= (signed)r5 ?   [SH-2E: signed]
     * bf/s 0x10A7C         — if false, goto negative_check */
    if ((int32_t)r4 >= (int32_t)r5) {
        /* mov.l @(0xD8,pc),r0  — r0 = 0xFD300000
         * bra 0x10A84
         * add r0,r4           — r4 = r4 + r0 */
        r0 = 0xFD300000u;
        r4 = r4 + r0;
    } else {
        /* cmp/pz r4           — compare r4 >= 0 ?
         * bt/s 0x10A84        — if true, goto return
         * add r5,r4           — r4 += r5 (only if r4 < 0) */
        if ((int32_t)r4 < 0) {
            r4 = r4 + r5;
        }
    }

    /* rts
     * mov r4,r0 */
    return r4;
}


/* Test helper: set RAM byte at 0xFFFFA5D4 */
static void set_sensor_byte(uint8_t val)
{
    *(volatile uint8_t *)0xFFFFA5D4 = val;
}


int main(void)
{
    unsigned failures = 0;
    unsigned tests = 0;

    map_sensor_ram();

    printf("=== calc_manifold_pressure_error_clamp_10A5C ===\n");

    /* Test with various sensor byte values and inputs */
    const uint8_t sensor_vals[] = {0x00, 0x01, 0x10, 0x40, 0x80, 0xA0, 0xFF};
    const uint32_t inputs[] = {0x00000000, 0x00000001, 0x00001000, 0x00100000,
                               0x00200000, 0x00500000, 0x01000000, 0x02000000,
                               0x03000000, 0xFFFFFFFF};

    for (size_t si = 0; si < sizeof(sensor_vals)/sizeof(sensor_vals[0]); si++) {
        set_sensor_byte(sensor_vals[si]);
        for (size_t ii = 0; ii < sizeof(inputs)/sizeof(inputs[0]); ii++) {
            uint32_t expected = ref_calc_manifold_pressure_error_clamp_10A5C(inputs[ii]);
            uint32_t actual   = calc_manifold_pressure_error_clamp_10A5C(inputs[ii]);
            tests++;

            if (expected != actual) {
                printf("FAIL: sensor=0x%02X input=0x%08X expected=0x%08X got=0x%08X\n",
                       sensor_vals[si], inputs[ii], expected, actual);
                failures++;
                if (failures >= 5) {
                    printf("Too many failures, aborting.\n");
                    return 1;
                }
            }
        }
    }

    /* Test with random values */
    srand(42);
    for (int i = 0; i < 10000; i++) {
        uint8_t s = (uint8_t)(rand() & 0xFF);
        uint32_t inp = (uint32_t)(((uint64_t)rand() * 0xFFFFFFFFull) / RAND_MAX);
        set_sensor_byte(s);
        uint32_t expected = ref_calc_manifold_pressure_error_clamp_10A5C(inp);
        uint32_t actual   = calc_manifold_pressure_error_clamp_10A5C(inp);
        tests++;

        if (expected != actual) {
            printf("FAIL: sensor=0x%02X input=0x%08X expected=0x%08X got=0x%08X\n",
                   s, inp, expected, actual);
            failures++;
            break;
        }
    }

    printf("Results: %u tests, %u failures\n", tests, failures);
    return failures ? 1 : 0;
}

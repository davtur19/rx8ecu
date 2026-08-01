/* ============================================================================
 * oracle_calibration_apply_4b770.c  —  host test rig for
 *                                      rx8_calibration_apply_4b770 @0x4B770
 * ============================================================================
 * Reads one vector per line on stdin, whitespace-separated hex tokens:
 *
 *     cal <b201> <bce00> <bce01>   -> <flag>
 *
 *   b201/bce00/bce01 : the three input bytes (0x00..0xFF) placed at
 *                      RAM[0xFFFFD201], RAM[0xFFFFCE00], RAM[0xFFFFCE01]
 *   flag             : the calibration flag byte left at RAM[0xFFFFCDFD],
 *                      printed as %02X
 *
 * The oracle contains NO copy of the flag logic — that lives solely in
 * src/rx8_calibration_apply_4b770.c.  It only mirrors the *caller-side*
 * set-up: the 0xFFFFxxxx RAM bytes are backed with mmap(MAP_FIXED) pages
 * (same trick as tests/host_oracle.c and c/tests/test_calibration_apply_4B770.c),
 * so the volatile fixed-address pointers in the sample compile and fault-free
 * on the host.  This is exactly what the ROM does on the SH-2E, where all
 * four addresses are plain on-chip RAM (input page 0xFFFFC000 holds
 * 0xFFFFCE00/01/0xFFFFCDFD; page 0xFFFFD000 holds 0xFFFFD201).
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

#include "rx8_samples.h"

/* rx8_samples.h (shared, untouched by this sample) does not declare the
 * function under test; declare its prototype here instead. */
void rx8_calibration_apply_4b770(void);

/* Same addresses as the ROM mov.w literals (0xD201 @0x4B782, 0xCDFD @0x4B78A,
 * 0xCE00 @0x4B7F8, 0xCE01 @0x4B7FA), sign-extended to the 0xFFFFxxxx window. */
#define IN_B201  0xFFFFD201u
#define IN_CE00  0xFFFFCE00u
#define IN_CE01  0xFFFFCE01u
#define OUT_FLAG 0xFFFFCDFDu

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

int main(void)
{
    char line[256];

    /* Back the pages holding the three input bytes and the flag byte. */
    map_page(IN_B201);      /* page 0xFFFFD000 */
    map_page(IN_CE00);      /* page 0xFFFFC000 (CE00/CE01/flag live here) */

    while (fgets(line, sizeof line, stdin)) {
        unsigned long b201, bce00, bce01;

        if (sscanf(line, "cal %lx %lx %lx", &b201, &bce00, &bce01) == 3) {
            /* Seed the input bytes, run the function, report the flag byte. */
            *(volatile uint8_t *)(uintptr_t)IN_B201 = (uint8_t)b201;
            *(volatile uint8_t *)(uintptr_t)IN_CE00 = (uint8_t)bce00;
            *(volatile uint8_t *)(uintptr_t)IN_CE01 = (uint8_t)bce01;
            rx8_calibration_apply_4b770();
            printf("%02X\n",
                   (unsigned)*(volatile uint8_t *)(uintptr_t)OUT_FLAG);
        } else {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
    }
    return 0;
}

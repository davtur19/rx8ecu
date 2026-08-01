/* ============================================================================
 * oracle_dtc_data_read_60f58.c  —  host test rig for
 *                                    rx8_dtc_data_read_60f58 @0x60F58
 * ============================================================================
 * Compile together with src/rx8_dtc_data_read_60f58.c (see
 * harness_dtc_data_read_60f58.py) and pipe test vectors on stdin; one
 * vector per line, twelve space-separated hex bytes seeding the 12-byte
 * window 0xFFFFD6C6 .. 0xFFFFD6D1:
 *
 *     dtc <c6> <c7> <c8> <c9> <ca> <cb> <cc> <cd> <ce> <cf> <d0> <d1>
 *          -> <c6'> <c7'> <c8'> <c9'> <ca'> <cb'> <cc'> <cd'> <ce'>
 *             <cf'> <d0'> <d1'>
 *
 * (Bytes c8/c9 and cc/cd are the two DTC status halfwords that the function
 * fills with 0xFFFF; c6/c7/d0/d1 are out-of-window sentinels; ca/cb/ce/cf
 * are the in-window odd halfwords the ROM leaves untouched.)
 *
 * The oracle re-implements the caller-side setup only: it mmap()s the page
 * backing the window (same trick as host_oracle.c / oracle_purge_flow_*)
 * and prints the bytes after the call.  It contains NO copy of the function
 * logic — that lives solely in the reconstructed source under test.  The
 * four sentinel bytes must survive the call untouched; they pin the store
 * width and stride and catch any over/under-run.
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

#include "rx8_samples.h"

/* Prototype is NOT in rx8_samples.h (sample project convention: only the
 * verified "public" leaves are listed there); declared here for the rig. */
void rx8_dtc_data_read_60f58(void);

#define WIN_BASE  0xFFFFD6C6u   /* sentinel front | 8-byte window | sentinel back */
#define WIN_LEN   12u

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
    /* Page 0xFFFFD000..0xFFFFDFFF backs the whole 12-byte window. */
    map_page(WIN_BASE);

    char line[256];
    while (fgets(line, sizeof line, stdin)) {
        unsigned long b[WIN_LEN];
        int n = 0;
        char *tok = strtok(line, " \t\r\n");
        while (tok && n < (int)WIN_LEN) {
            b[n++] = strtoul(tok, NULL, 16);
            tok = strtok(NULL, " \t\r\n");
        }
        if (n != (int)WIN_LEN) {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
        for (int i = 0; i < (int)WIN_LEN; i++)
            *(volatile uint8_t *)(uintptr_t)(WIN_BASE + i) = (uint8_t)b[i];

        rx8_dtc_data_read_60f58();

        for (int i = 0; i < (int)WIN_LEN; i++)
            printf("%s%02X", i ? " " : "",
                   *(volatile uint8_t *)(uintptr_t)(WIN_BASE + i));
        putchar('\n');
    }
    return 0;
}

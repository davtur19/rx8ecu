/* ============================================================================
 * oracle_crank_sensor_init.c  —  host test rig for rx8_crank_sensor_init @0x7C30
 * ============================================================================
 * Compile together with src/rx8_crank_sensor_init.c (see
 * harness_crank_sensor_init.py) and pipe test vectors on stdin; one vector per
 * line, seven space-separated hex bytes:
 *
 *     crank <f95> <f96> <f97> <c8> <c9> <ca> <cb>
 *           -> <f95'> <f96'> <f97'> <c8'> <c9'> <ca'> <cb'> <tail>
 *
 *   <f96>  pre-state of the engine-running flag byte at 0xFFFF9F96
 *   <c9>   pre-state of sensor control register A at 0xFFFF9FC9
 *   <ca>   pre-state of sensor control register B at 0xFFFF9FCA
 *   <f95>/<f97>/<c8>/<cb>  sentinel bytes that must survive the call
 *          untouched — they pin the store count and width.
 *   <tail> 1 if the function tail-called crank_mode_switch (the ROM's
 *          `bra 0x0768C` after clearing the flag — i.e. flag pre-state == 1),
 *          0 otherwise.
 *
 * The oracle re-implements the caller-side setup only: it mmap()s the page
 * backing the flag byte and the two control registers (same trick as
 * host_oracle.c) and prints the bytes + tail flag after the call.  It contains
 * NO copy of the function logic — that lives solely in the reconstructed
 * source under test.  rx8_crank_mode_switch() is stubbed here to just record
 * that the tail call happened; the ROM's fixed argument r4 = 0 and the branch
 * target 0x0768C are pinned by the harness on the emulator side.
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

#include "rx8_samples.h"

/* Prototype is NOT in rx8_samples.h (sample project convention: only the
 * verified "public" leaves are listed there); declared here for the rig. */
void rx8_crank_sensor_init(void);

/* Stub of the ROM's tail-called crank-mode state machine @0x0768C.  On the
 * target this is the real ROM function; here it only records the call so the
 * harness can compare the tail-call boundary bit-exactly. */
static int rx8_crank_mode_switch_called = 0;
void rx8_crank_mode_switch(void)
{
    rx8_crank_mode_switch_called = 1;
}

#define FLAG_LO_ADDR  0xFFFF9F95u   /* sentinel: left of the flag byte   */
#define FLAG_ADDR     0xFFFF9F96u   /* engine-running flag (u8)          */
#define FLAG_HI_ADDR  0xFFFF9F97u   /* sentinel: right of the flag byte  */
#define CTRL_A_LO_ADDR 0xFFFF9FC8u  /* sentinel: left of control reg A   */
#define CTRL_A_ADDR   0xFFFF9FC9u   /* sensor control register A (u8)    */
#define CTRL_B_ADDR   0xFFFF9FCAu   /* sensor control register B (u8)    */
#define CTRL_B_HI_ADDR 0xFFFF9FCBu  /* sentinel: right of control reg B  */

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
    /* All seven bytes live in the 0xFFFF9000..0xFFFF9FFF page; one mmap. */
    map_page(FLAG_ADDR);

    char line[256];
    while (fgets(line, sizeof line, stdin)) {
        unsigned long f95, f96, f97, c8, c9, ca, cb;
        if (sscanf(line, "crank %lx %lx %lx %lx %lx %lx %lx",
                   &f95, &f96, &f97, &c8, &c9, &ca, &cb) == 7) {
            *(volatile uint8_t *)(uintptr_t)FLAG_LO_ADDR   = (uint8_t)f95;
            *(volatile uint8_t *)(uintptr_t)FLAG_ADDR      = (uint8_t)f96;
            *(volatile uint8_t *)(uintptr_t)FLAG_HI_ADDR   = (uint8_t)f97;
            *(volatile uint8_t *)(uintptr_t)CTRL_A_LO_ADDR = (uint8_t)c8;
            *(volatile uint8_t *)(uintptr_t)CTRL_A_ADDR    = (uint8_t)c9;
            *(volatile uint8_t *)(uintptr_t)CTRL_B_ADDR    = (uint8_t)ca;
            *(volatile uint8_t *)(uintptr_t)CTRL_B_HI_ADDR = (uint8_t)cb;

            rx8_crank_mode_switch_called = 0;
            rx8_crank_sensor_init();

            printf("%02X %02X %02X %02X %02X %02X %02X %d\n",
                   *(volatile uint8_t *)(uintptr_t)FLAG_LO_ADDR,
                   *(volatile uint8_t *)(uintptr_t)FLAG_ADDR,
                   *(volatile uint8_t *)(uintptr_t)FLAG_HI_ADDR,
                   *(volatile uint8_t *)(uintptr_t)CTRL_A_LO_ADDR,
                   *(volatile uint8_t *)(uintptr_t)CTRL_A_ADDR,
                   *(volatile uint8_t *)(uintptr_t)CTRL_B_ADDR,
                   *(volatile uint8_t *)(uintptr_t)CTRL_B_HI_ADDR,
                   rx8_crank_mode_switch_called);
        } else {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
    }
    return 0;
}

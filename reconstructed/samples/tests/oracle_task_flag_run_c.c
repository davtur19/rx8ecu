/* ============================================================================
 * oracle_task_flag_run_c.c — host test rig for rx8_task_flag_run_c @0x35EE
 * ============================================================================
 * Compile together with src/rx8_task_flag_run_c.c and pipe test vectors on
 * stdin; one vector per line, whitespace-separated hex tokens:
 *
 *     flag <state> <delta>      -> <state_final> <mark>
 *
 *   state : initial kernel state word at 0xFFFF72B8 (before the barrier)
 *   delta : per-vector "task-body edit" the stub ORs into the state word
 *
 * The oracle mirrors the emulator-side set-up of harness_task_flag_run_c.py:
 * it mmap()s the page that backs the RAM words and re-implements ONLY the
 * caller-side stub — the ROM's task body — which the reconstructed function
 * invokes while bit 15 of the state word is held.  It contains NO copy of
 * the barrier logic; that lives solely in src/rx8_task_flag_run_c.c.
 *
 * Memory map used (identical on emulator and host, matching the ROM):
 *   0xFFFF72B8  state word (read/modified by the barrier AND the stub)
 *   0xFFFF72BC  delta      (scratch: the stub's per-vector edit value)
 *   0xFFFF72C0  mark       (scratch: what the stub observed while bit 15
 *                           was held — proves acquire ordering)
 * The two scratch cells are harness-only (the emulator's sparse RAM); the
 * only real location is the state word.
 *
 * NOTE: rx8_task_flag_run_c is declared here rather than in rx8_samples.h
 * (which is off-limits for this task) — the reconstructed name maps to the
 * ROM function at 0x35EE (see rx8_task_flag_run_c.c).
 * ==========================================================================*/
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

#include "rx8_samples.h"

/* 0x35EE — task running-flag barrier (see rx8_task_flag_run_c.c). */
void rx8_task_flag_run_c(void (*task_fn)(void));

#define STATE_ADDR 0xFFFF72B8u
#define DELTA_ADDR 0xFFFF72BCu
#define MARK_ADDR  0xFFFF72C0u
#define TASK_BIT   0x00000004u   /* marker bit the stub always sets */

static volatile uint32_t *state = (volatile uint32_t *)STATE_ADDR;
static volatile uint32_t *delta = (volatile uint32_t *)DELTA_ADDR;
static volatile uint32_t *mark  = (volatile uint32_t *)MARK_ADDR;

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

/* Task body, byte-for-byte behaviourally identical to the SH-2 stub the
 * emulator harness installs at 0x00100000: read the state word (bit 15 is
 * held at this point), OR in the delta and the marker bit, write both back.
 * It deliberately EDITS the state word so the harness can prove the ROM
 * re-reads it after the call (see the source header). */
static void task_stub(void)
{
    uint32_t edited = *state | *delta | TASK_BIT;
    *state = edited;
    *mark = edited;
}

int main(void)
{
    char line[128];

    /* Back the page holding 0xFFFF72B8/BC/C0 (state + harness scratch). */
    map_page(0xFFFF7000u);

    while (fgets(line, sizeof line, stdin)) {
        unsigned long s, d;

        if (sscanf(line, "flag %lx %lx", &s, &d) == 2) {
            *state = (uint32_t)s;
            *delta = (uint32_t)d;
            *mark = 0;
            rx8_task_flag_run_c(task_stub);
            printf("%08lX %08lX\n",
                   (unsigned long)(uint32_t)*state,
                   (unsigned long)(uint32_t)*mark);
        } else {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
    }
    return 0;
}

/* ============================================================================
 * oracle_task_full_context_save.c  —  host test rig for
 *                                     rx8_task_full_context_save @0x3BF4
 * ============================================================================
 * Compile together with src/rx8_task_full_context_save.c and pipe test vectors
 * on stdin; one vector per line, whitespace-separated hex tokens:
 *
 *     save <type> <r5> <status_pre>
 *                              -> <saved_sp> <status> <ctx[0..16]>
 *
 *   type       : task descriptor byte +0 (0x04 selects the FPU push block)
 *   r5         : ABI scratch value the ROM pushes verbatim (context word)
 *   status_pre : pre-state of the status byte the ROM writes 0x04 into
 *
 * The oracle mirrors the emulator-side set-up of
 * harness_task_full_context_save.py: it mmap()s the pages backing the task
 * control block, the task descriptor, the status cell and the kernel stack,
 * and re-implements ONLY the caller-side scaffolding:
 *    - the scheduler dispatch tail-jump @0x3C68  —  STUBBED (returns) on the
 *      emulator side too (`rts; nop` at 0x3C68, c/tests precedent); returning
 *      lets the host C terminate and the oracle print its results.
 *
 * It contains NO copy of the context-save logic itself; that lives solely in
 * the reconstructed source under test (src/rx8_task_full_context_save.c).
 *
 * Memory map used (identical on emulator and host, matching the ROM):
 *   0xFFFFA000  task control block  (saved_sp written at +0x0C)
 *   0xFFFFA100  task descriptor     (type +0, status pointer +0x04 -> 0xFFFF8060)
 *   0xFFFF8060  status cell         (byte <- 0x04)
 *   0xFFFFDF00  kernel stack top    (context block pushed downward)
 * ==========================================================================*/
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

/* 0x3BF4 — RTOS full context save (see src/rx8_task_full_context_save.c). */
void rx8_task_full_context_save(uint8_t *tcb, const uint8_t *desc, uint32_t r5);

/* STUBBED — the ROM tail-branches to the scheduler dispatch @0x3C68 and never
 * returns; returning lets the host C terminate and the oracle print results. */
void rx8_os_dispatch(void)
{
}

#define TCB_ADDR      0xFFFFA000u
#define DESC_ADDR     0xFFFFA100u
#define STATUS_ADDR   0xFFFF8060u
#define STACK_TOP     0xFFFFDF00u

static volatile uint8_t *tcb   = (volatile uint8_t *)TCB_ADDR;
static volatile uint8_t *desc  = (volatile uint8_t *)DESC_ADDR;

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

/* Numeric 32-bit word read.  The reconstructed source writes 32-bit words
 * through native uint32_t pointers; per rx8_hw.h "the numeric value of every
 * 16/32-bit word is identical on both sides", so the oracle reads the numeric
 * value back (NOT a byte-wise big-endian decode).  The emulator's cpu.rd()
 * returns the same numeric word, so bit-exactness holds on either endianness. */
static uint32_t rd32(uintptr_t addr)
{
    return *(volatile uint32_t *)addr;
}

int main(void)
{
    char line[256];

    /* Back the pages holding the TCB, the descriptor, the status cell and the
     * kernel stack.  Anonymous mmap is zero-filled, matching the emulator's
     * untouched sparse overlay. */
    map_page(TCB_ADDR);
    map_page(DESC_ADDR);
    map_page(STATUS_ADDR);
    map_page(STACK_TOP);

    while (fgets(line, sizeof line, stdin)) {
        unsigned long type, r5, status_pre;
        uint32_t saved_sp;
        int i;

        if (sscanf(line, "save %lx %lx %lx", &type, &r5, &status_pre) != 3) {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }

        desc[0] = (uint8_t)type;                      /* descriptor type byte   */
        desc[4] = (uint8_t)(STATUS_ADDR >> 24);       /* status pointer @ +0x04 */
        desc[5] = (uint8_t)(STATUS_ADDR >> 16);
        desc[6] = (uint8_t)(STATUS_ADDR >> 8);
        desc[7] = (uint8_t)STATUS_ADDR;
        *(volatile uint8_t *)STATUS_ADDR = (uint8_t)status_pre;

        rx8_task_full_context_save((uint8_t *)tcb, (const uint8_t *)desc,
                                   (uint32_t)r5);

        saved_sp = rd32(TCB_ADDR + 0x0C);
        printf("%08lX %02lX",
               (unsigned long)saved_sp,
               (unsigned long)*(volatile uint8_t *)STATUS_ADDR);
        for (i = 0; i < 17; i++)
            printf(" %08lX", (unsigned long)rd32(saved_sp + (uint32_t)i * 4));
        putchar('\n');
    }
    return 0;
}
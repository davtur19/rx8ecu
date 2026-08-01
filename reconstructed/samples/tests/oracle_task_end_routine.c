/* ============================================================================
 * oracle_task_end_routine.c  —  host test rig for rx8_task_end_routine @0x3D58
 * ============================================================================
 * Compile together with src/rx8_task_end_routine.c and pipe test vectors on
 * stdin; one vector per line, whitespace-separated hex tokens:
 *
 *     end <flag> <saved_sr> <status_pre> <result_pre> <active> <type>
 *         <refcount> <saved_sp>
 *                                     -> <status> <result> <saved_sr_final>
 *                                        <active> <refcount>
 *
 *   flag       : 0 (skip the running-flag barrier) or non-zero (run it; the
 *                emulator side seeds 0x4B10 with the task-body stub address)
 *   saved_sr   : os_ctrl+16 pre-state  (also the barrier stub's mark cell)
 *   status_pre : os_ctrl+8 pre-state   (also the flag word the barrier reads)
 *   result_pre : os_ctrl+12 pre-state  (also the barrier stub's delta cell)
 *   active/type/refcount/saved_sp : task control block pre-state
 *
 * The oracle mirrors the emulator-side set-up of harness_task_end_routine.py:
 * it mmap()s the pages backing the OS control block and the task block and
 * re-implements ONLY the caller-side scaffolding:
 *    - rx8_task_flag_fetch()  returns the seeded flag value (models the ROM's
 *      32-bit load at 0x4B10, which lies below this host's mmap_min_addr);
 *    - task_flag_run_c()      models the REAL ROM bytes @0x35EE (set bit 15
 *                             of the flag word, call the task body, clear bit
 *                             15) driving the same OR-delta+0x4 task-body stub
 *                             the emulator harness installs at 0x00100000;
 *    - consistency_check()    no-op — STUBBED on the emulator side too
 *                             (c/tests/test_taskEndRoutine.py precedent; the
 *                             real callee @0x3A28 needs caller r6/r7 state no
 *                             taskEndRoutine caller establishes);
 *    - task_dispatcher()      no-op — the ROM tail-jumps here and never
 *                             returns; the stub lets the host C terminate.
 *
 * It contains NO copy of the task-end logic itself; that lives solely in the
 * reconstructed source under test (src/rx8_task_end_routine.c).
 *
 * Memory map used (identical on emulator and host, matching the ROM):
 *   0xFFFF72B0  OS control block (status +8, result +12, saved_sr +16,
 *               current_task +20 = 0xFFFFA000)
 *   0xFFFFA000  task control block (active +0, type +1, refcount +3,
 *               saved_sp +4)
 * ==========================================================================*/
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

#include "rx8_samples.h"

/* 0x3D58 — RTOS task-end routine (see src/rx8_task_end_routine.c). */
void rx8_task_end_routine(void);

/* Accessors / callees the reconstructed source declares external. */
uint32_t rx8_task_flag_fetch(void);
void task_flag_run_c(int arg);
void consistency_check(uint8_t *os_ctrl, int type);
void task_dispatcher(void);

#define OS_CTRL_ADDR    0xFFFF72B0u
#define TASK_BLOCK_ADDR 0xFFFFA000u
#define RUN_BIT         0x00008000u
#define RUN_MASK        0xFFFF7FFFu
#define TASK_BIT        0x00000004u   /* marker bit the task-body stub always sets */

static volatile uint32_t *os  = (volatile uint32_t *)OS_CTRL_ADDR;
static volatile uint8_t  *task = (volatile uint8_t *)TASK_BLOCK_ADDR;

static uint32_t g_flag;   /* what rx8_task_flag_fetch() returns for this vector */

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

/* Models the ROM's `mov.l @r1,r2` flag load at 0x4B10 (see the source header). */
uint32_t rx8_task_flag_fetch(void)
{
    return g_flag;
}

/* Task body, byte-for-byte behaviourally identical to the SH-2 stub the
 * emulator harness installs at 0x00100000: read the flag word (bit 15 is held
 * at this point), OR in the delta (os_ctrl+12, harness scratch) and the marker
 * bit, write both the flag word and the mark cell (os_ctrl+16). */
static void task_body_stub(void)
{
    uint32_t edited = os[8 / 4] | os[12 / 4] | TASK_BIT;
    os[8 / 4] = edited;
    os[16 / 4] = edited;
}

/* Models the REAL ROM bytes @0x35EE (samples/rx8_task_flag_run_c.c): acquire
 * bit 15, call the task body through the 0x4B10 pointer (our stub), release
 * bit 15 re-reading the word so the stub's edits are preserved. */
void task_flag_run_c(int arg)
{
    (void)arg;                              /* the ROM ignores r4 */
    os[8 / 4] = os[8 / 4] | RUN_BIT;        /* acquire                 */
    task_body_stub();                       /* task body (via 0x4B10)  */
    os[8 / 4] = os[8 / 4] & RUN_MASK;       /* release (re-read)       */
}

/* STUBBED on the emulator side too — see the file header. */
void consistency_check(uint8_t *os_ctrl, int type)
{
    (void)os_ctrl;
    (void)type;
}

/* STUBBED — the ROM tail-jumps here and never returns; returning lets the
 * host C terminate and the oracle print its results. */
void task_dispatcher(void)
{
}

int main(void)
{
    char line[256];

    /* Back the pages holding the OS control block + the task block. */
    map_page(OS_CTRL_ADDR);
    map_page(TASK_BLOCK_ADDR);

    while (fgets(line, sizeof line, stdin)) {
        unsigned long flag, saved_sr, status0, result0, active, type_, ref, sp;

        if (sscanf(line, "end %lx %lx %lx %lx %lx %lx %lx %lx",
                   &flag, &saved_sr, &status0, &result0,
                   &active, &type_, &ref, &sp) != 8) {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }

        g_flag = (uint32_t)flag;
        os[16 / 4] = (uint32_t)saved_sr;
        os[20 / 4] = TASK_BLOCK_ADDR;
        os[8 / 4]  = (uint32_t)status0;
        os[12 / 4] = (uint32_t)result0;
        task[0] = (uint8_t)active;
        task[1] = (uint8_t)type_;
        task[3] = (uint8_t)ref;
        *(volatile uint32_t *)(uintptr_t)&task[4] = (uint32_t)sp;

        rx8_task_end_routine();

        printf("%08lX %08lX %08lX %02lX %02lX\n",
               (unsigned long)(uint32_t)os[8 / 4],
               (unsigned long)(uint32_t)os[12 / 4],
               (unsigned long)(uint32_t)os[16 / 4],
               (unsigned long)task[0],
               (unsigned long)task[3]);
    }
    return 0;
}

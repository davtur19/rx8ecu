/* ============================================================================
 * oracle_task_execute_by_index.c — host rig for rx8_task_execute_by_index @0x3854
 * ============================================================================
 * Compile together with src/rx8_task_execute_by_index.c and pipe test vectors
 * on stdin; one vector per line, whitespace-separated hex tokens:
 *
 *   task <idx> <prio> <stp> <sb1> <cnt> <status> <savsr> <ossb> <ossb1>
 *        <f08> <f10> <sr> <hret>
 *      -> <ret> <cnt'> <status'> <h_r4> <h_r5> <h_r6> <f_mark> <f_arg>
 *         <x_mark> <x_r4> <x_r5> <x_r6> <i_mark> <i_r4> <i_r5> <i_r6> <sr'>
 *
 *   idx     : task table index (u16 in the ROM)
 *   prio    : task priority byte (task table entry +2, sign-extended by mov.b)
 *   stp     : task state block pointer (task table entry +4; must point into
 *             the mmap'd 0x00100000 page)
 *   sb1     : task state block gate byte at +1
 *   cnt     : task run counter byte at +3 (pre-state)
 *   status  : OS control block status word at +8 (0xFFFF72B8)
 *   savsr   : OS control block saved SR at +16 (0xFFFF72C0)
 *   ossb    : OS control block state-block pointer at +24 (0x00100200/0x240)
 *   ossb1   : byte at ossb+1 (the gate byte the ROM tests)
 *   f08     : kernel flag word at 0x4B08 (interrupt-priority dispatch)
 *   f10     : kernel flag word at 0x4B10 (task-running-flag barrier)
 *   sr      : the status register at function entry (stc sr,r13)
 *   hret    : value the task-execution-helper stub returns in r0
 *
 * Output (17 hex tokens):
 *   ret      : the function's return value (0 or 4)
 *   cnt'     : run counter byte after the call
 *   status'  : OS status word after the call
 *   h_r4/5/6 : arguments the helper stub observed (os_ctrl, index, prio)
 *   f_mark/f_arg : 0xA5 + arg if task_flag_run_C was reached, else 0/0
 *   x_mark/x_r4/5/6 : 0xA5 + args if task_full_context_save was reached
 *   i_mark/i_r4/5/6 : 0xA5 + args if interrupt_priority_dispatch was reached
 *   sr'      : the final SR state (path-dependent, see the source header)
 *
 * The oracle re-implements ONLY the caller-side set-up: it mmap()s the pages
 * that back the OS control block + marker cells (0xFFFF7000), the task table
 * (re-homed to 0xFFFF6000; the ROM uses 0x4990, see the source header), the
 * task state blocks (0x00100000) and it supplies the four OS-layer callee
 * stubs.  It contains NO copy of the dispatch logic — that lives solely in
 * src/rx8_task_execute_by_index.c.
 *
 * Memory map used (identical on emulator and host):
 *   0xFFFF7000  OS control block (0xFFFF72B0) + marker/scratch cells
 *   0xFFFF6000  re-homed task table
 *   0x00100000  task state blocks + OS context-save block
 * ==========================================================================*/
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

#include "rx8_samples.h"

/* 0x3854 — OS task scheduler dispatcher (see rx8_task_execute_by_index.c). */
int  rx8_task_execute_by_index(int task_index, const uint8_t *task_table,
                               uint32_t kern_flag_4B08, uint32_t kern_flag_4B10);
void rx8_sr_set_state(uint32_t sr);
uint32_t rx8_sr_get_state(void);

#define OS_CTRL_BASE   0xFFFF72B0u   /* +8 status, +16 saved_sr, +24 state   */
#define HELPER_RET     0xFFFF71C0u   /* helper return value (seeded)         */
#define HELPER_REC     0xFFFF71C8u   /* helper observed r4/r5/r6             */
#define FLAGRUN_MARK   0xFFFF71D4u   /* 0xA5 if 0x35EE was reached           */
#define FLAGRUN_ARG    0xFFFF71D8u   /* its r4                                */
#define CTX_MARK       0xFFFF71DCu   /* 0xA5 if 0x3BF4 was reached           */
#define CTX_REC        0xFFFF71E0u   /* its r4/r5/r6                         */
#define IPD_MARK       0xFFFF71ECu   /* 0xA5 if 0x3610 was reached           */
#define IPD_REC        0xFFFF71F0u   /* its r4/r5/r6                         */
#define TABLE_ADDR     0xFFFF6000u   /* re-homed task table (see header)     */

#define MARK_VALUE     0xA5u

static volatile uint32_t *os    = (volatile uint32_t *)OS_CTRL_BASE;
static volatile uint32_t *hret  = (volatile uint32_t *)HELPER_RET;
static volatile uint32_t *hrec  = (volatile uint32_t *)HELPER_REC;
static volatile uint32_t *fmark = (volatile uint32_t *)FLAGRUN_MARK;
static volatile uint32_t *farg  = (volatile uint32_t *)FLAGRUN_ARG;
static volatile uint32_t *xmark = (volatile uint32_t *)CTX_MARK;
static volatile uint32_t *xrec  = (volatile uint32_t *)CTX_REC;
static volatile uint32_t *imark = (volatile uint32_t *)IPD_MARK;
static volatile uint32_t *irec  = (volatile uint32_t *)IPD_REC;

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

/* OS-layer callee stubs — behaviourally identical to the SH-2 stubs the
 * emulator harness installs at 0x39BA/0x35EE/0x3BF4/0x3610. */
uint32_t rx8_task_execute_helper(uint32_t *os_ctrl, uint32_t index,
                                 int32_t priority)
{
    hrec[0] = (uint32_t)(uintptr_t)os_ctrl;
    hrec[1] = index;
    hrec[2] = (uint32_t)priority;
    return *hret;
}

void rx8_task_flag_run_c(int arg)
{
    *farg = (uint32_t)arg;
    *fmark = MARK_VALUE;
}

void rx8_task_full_context_save(uint32_t *os_ctrl, uint32_t saved_sr,
                                uint8_t *state_block)
{
    xrec[0] = (uint32_t)(uintptr_t)os_ctrl;
    xrec[1] = saved_sr;
    xrec[2] = (uint32_t)(uintptr_t)state_block;
    *xmark = MARK_VALUE;
}

void rx8_interrupt_priority_dispatch(int arg1, int arg2, uint32_t status)
{
    irec[0] = (uint32_t)arg1;
    irec[1] = (uint32_t)arg2;
    irec[2] = status;
    *imark = MARK_VALUE;
}

int main(void)
{
    map_page(0xFFFF7000u);
    map_page(0xFFFF6000u);
    map_page(0x00100000u);

    char line[256];
    while (fgets(line, sizeof line, stdin)) {
        unsigned long idx, prio, stp, sb1, cnt, status, savsr;
        unsigned long ossb, ossb1, f08, f10, sr, hretv;
        int n = sscanf(line,
                       "task %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx",
                       &idx, &prio, &stp, &sb1, &cnt, &status, &savsr,
                       &ossb, &ossb1, &f08, &f10, &sr, &hretv);
        if (n != 13) {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }

        /* Seed the task table entry (re-homed copy; same bytes as the ROM's
         * 0x4990 + index*16 layout: u16 priority at +2, u32 state_ptr at +4). */
        uint8_t *tentry = (uint8_t *)TABLE_ADDR
                        + (uint32_t)(uint16_t)idx * 16u;
        tentry[2] = (uint8_t)prio;
        tentry[3] = 0;
        *(volatile uint32_t *)(tentry + 4) = (uint32_t)stp;

        /* Seed the task state block and the OS context-save block. */
        uint8_t *stb = (uint8_t *)(uintptr_t)(uint32_t)stp;
        stb[1] = (uint8_t)sb1;
        stb[3] = (uint8_t)cnt;
        ((uint8_t *)(uintptr_t)(uint32_t)ossb)[1] = (uint8_t)ossb1;

        /* Seed the OS control block: status(+8), saved_sr(+16), state(+24). */
        os[2] = (uint32_t)status;
        os[4] = (uint32_t)savsr;
        os[6] = (uint32_t)ossb;

        /* Seed the helper return cell + clear all marker cells. */
        *hret = (uint32_t)hretv;
        hrec[0] = 0; hrec[1] = 0; hrec[2] = 0;
        *fmark = 0; *farg = 0;
        xrec[0] = 0; xrec[1] = 0; xrec[2] = 0;
        *xmark = 0;
        irec[0] = 0; irec[1] = 0; irec[2] = 0;
        *imark = 0;

        rx8_sr_set_state((uint32_t)sr);
        int ret = rx8_task_execute_by_index((int)(uint16_t)idx,
                                            (const uint8_t *)TABLE_ADDR,
                                            (uint32_t)f08, (uint32_t)f10);

        printf("%08lX %02lX %08lX %08lX %08lX %08lX %08lX %08lX %08lX %08lX "
               "%08lX %08lX %08lX %08lX %08lX %08lX %08lX\n",
               (unsigned long)(uint32_t)ret,
               (unsigned long)stb[3],
               (unsigned long)os[2],
               (unsigned long)hrec[0], (unsigned long)hrec[1],
               (unsigned long)hrec[2],
               (unsigned long)*fmark, (unsigned long)*farg,
               (unsigned long)*xmark, (unsigned long)xrec[0],
               (unsigned long)xrec[1], (unsigned long)xrec[2],
               (unsigned long)*imark, (unsigned long)irec[0],
               (unsigned long)irec[1], (unsigned long)irec[2],
               (unsigned long)rx8_sr_get_state());
    }
    return 0;
}

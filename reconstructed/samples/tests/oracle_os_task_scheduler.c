/* ============================================================================
 * oracle_os_task_scheduler.c  —  host test rig for rx8_os_task_scheduler @0x9668
 * ============================================================================
 * Compile together with src/rx8_os_task_scheduler.c and pipe test vectors on
 * stdin; one vector per line, whitespace-separated hex tokens:
 *
 *     sched <tid> <eidx> <marker> <ac> <func> <a0..a7> <disp_ret>
 *                                       -> <ret> <mark> <r0..r5> <dmark>
 *
 *   tid/eidx  : task table / entry indices
 *   marker    : entry.marker (0xFFFF -> direct call, else dispatch id)
 *   ac        : entry.arg_count (0..4; the ROM frame is 20 bytes)
 *   func      : entry.func_ptr (ROM-address value; echoed into frame[0])
 *   a0..a7    : the 8 argument words the caller offers (only ac are copied)
 *   disp_ret  : return value seeded into the dispatcher stub slot
 *
 * The oracle mirrors the emulator-side set-up of
 * harness_os_task_scheduler.py: it mmap()s the pages backing the caller args,
 * the task pool, the record/mark area and the dispatcher marker cell, and
 * re-implements ONLY the caller-side scaffolding:
 *    - direct_stub()          the task function the ROM calls with r4=&frame[1]
 *                             (the SH-2 stub the emulator installs at 0x00101000);
 *                             writes REC[0]=arg_count, echoes frame[0..ac] and
 *                             marks the running-mark cell with 0xA5.
 *    - rx8_os_dispatcher()    the scheduler dispatcher the ROM tail-calls via
 *                             the constant 0x5F34 (stubbed on the emulator side
 *                             too); writes the marker id to the marker cell and
 *                             returns the seeded disp_ret.
 * It contains NO copy of the scheduler logic itself; that lives solely in the
 * reconstructed source under test (src/rx8_os_task_scheduler.c).
 *
 * Memory map used (identical on emulator and host, matching the ROM):
 *   0xFFFFD000    caller args (8 u32 words read by the copy loop)
 *   0x00120000    task pool (task_id * 0x60, entry at +entry_idx * 8)
 *   0x00101030    record area  (REC[0] = arg_count, then echoed frame words)
 *   0x00101058    running-mark cell (0xA5 when the direct call fired)
 *   0xFFFFA100    dispatcher marker cell (marker id passed to the dispatcher)
 * ==========================================================================*/
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

#include "rx8_hw.h"
#include "rx8_samples.h"

/* 0x9668 — OS task scheduler (see src/rx8_os_task_scheduler.c). */
typedef void (*rx8_os_task_fn)(uint32_t *frame_args);
int rx8_os_task_scheduler(uint8_t task_id, uint16_t entry_idx,
                          const uint32_t *args,
                          const uint32_t *task_table,
                          rx8_os_task_fn direct_fn);

/* The dispatcher the reconstructed source declares external (0x5F34). */
int rx8_os_dispatcher(uint16_t marker, uint32_t *frame);

#define ARGS_ADDR       0xFFFFD000u   /* caller argument words                */
#define POOL_ADDR       0x00120000u   /* task pool base (29 tasks * 0x60)     */
#define POOL_STRIDE     0x60u
#define REC_ADDR        0x00101030u   /* record area (stub output)            */
#define MARK_ADDR       0x00101058u   /* running-mark cell (0xA5 = fired)     */
#define DMARK_ADDR      0xFFFFA100u   /* dispatcher marker cell               */
#define FUNC_ADDR       0x00101000u   /* direct-stub ROM address (value)      */
#define MARK_BIT        0xA5u

static uint32_t g_table[29];
static uint32_t g_ac;        /* arg_count for this vector (stub input)        */
static uint32_t g_disp_ret;  /* dispatcher return for this vector             */

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

/* Task function — the ROM calls it with r4 = &frame[1].  Byte-for-byte
 * behaviourally identical to the SH-2 stub the emulator harness installs at
 * 0x00101000: REC[0] = arg_count, REC[1..ac+1] = frame[0..ac] (the entry
 * function pointer, then the copied args), mark cell = 0xA5. */
static void direct_stub(uint32_t *frame1)
{
    volatile uint32_t *rec = (volatile uint32_t *)REC_ADDR;
    rec[0] = g_ac;
    rec[1] = frame1[-1];                 /* frame[0] = entry.func_ptr        */
    for (uint32_t i = 0; i < g_ac; i++) {
        rec[2 + i] = frame1[i];          /* frame[1..ac] = copied args       */
    }
    *(volatile uint32_t *)MARK_ADDR = MARK_BIT;
}

/* Scheduler dispatcher — the ROM calls it with r4 = marker, r5 = frame and
 * uses the result as a reschedule flag.  Stub mirroring the SH-2 overlay at
 * 0x5F34: write the marker id to the marker cell, return the seeded value.
 *
 * NOTE: the marker cell must receive the SIGN-EXTENDED marker.  The ROM loads
 * the entry marker with `mov.w @r13,r4` (16-bit sign-extending load) before
 * tail-calling 0x5F34, and the SH-2 stub stores the full r4 with `mov.l r4,
 * @r0` — so for markers >= 0x8000 (e.g. 0xFFFE) the ROM writes 0xFFFFFFFE,
 * not 0x0000FFFE.  The host stub sign-extends to match bit-exactly. */
int rx8_os_dispatcher(uint16_t marker, uint32_t *frame)
{
    (void)frame;
    *(volatile uint32_t *)DMARK_ADDR = (uint32_t)(int16_t)marker;
    return (int)g_disp_ret;
}

int main(void)
{
    char line[256];

    /* Back the pages holding the args, the task pool, the record/mark area
     * and the dispatcher marker cell. */
    map_page(ARGS_ADDR);
    map_page(POOL_ADDR);
    map_page(REC_ADDR);
    map_page(DMARK_ADDR);

    /* Task pointer table: g_task_table[tid] -> pool base + tid * 0x60. */
    for (int t = 0; t < 29; t++) {
        g_table[t] = POOL_ADDR + (uint32_t)t * POOL_STRIDE;
    }

    while (fgets(line, sizeof line, stdin)) {
        unsigned long tid, eidx, marker, ac, func;
        unsigned long a[8], disp_ret;

        if (sscanf(line,
                   "sched %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx"
                   " %lx",
                   &tid, &eidx, &marker, &ac, &func,
                   &a[0], &a[1], &a[2], &a[3], &a[4], &a[5], &a[6], &a[7],
                   &disp_ret) != 14) {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }

        /* Seed the caller args, the task entry, the record/mark area and the
         * dispatcher marker cell (emulator harness does the identical set). */
        for (int i = 0; i < 8; i++) {
            *(volatile uint32_t *)(ARGS_ADDR + (uint32_t)i * 4) =
                (uint32_t)a[i];
        }
        {
            uint8_t *entry = (uint8_t *)(uintptr_t)
                (POOL_ADDR + (uint32_t)tid * POOL_STRIDE
                 + (uint32_t)eidx * 8u);
            /* Host-side pool bytes must be little-endian: the reconstructed
             * C reads marker/arg_count/func_ptr as native u16/u32, whereas
             * the emulator seeds the same entry big-endian for the SH-2.
             * (Big-endian seeds made ac=2 read as 0x0200=512, overflowing
             * the 5-word frame and smashing the stack canary.) */
            entry[0] = (uint8_t)(marker & 0xFF);
            entry[1] = (uint8_t)(marker >> 8);
            entry[2] = (uint8_t)(ac & 0xFF);
            entry[3] = (uint8_t)(ac >> 8);
            entry[4] = (uint8_t)(func & 0xFF);
            entry[5] = (uint8_t)(func >> 8);
            entry[6] = (uint8_t)(func >> 16);
            entry[7] = (uint8_t)(func >> 24);
        }
        *(volatile uint32_t *)REC_ADDR = REC_ADDR;   /* pool slot self-ptr    */
        *(volatile uint32_t *)(REC_ADDR + 4) = 0;    /* record words (stub)   */
        *(volatile uint32_t *)(REC_ADDR + 8) = 0;
        *(volatile uint32_t *)(REC_ADDR + 12) = 0;
        *(volatile uint32_t *)(REC_ADDR + 16) = 0;
        *(volatile uint32_t *)(REC_ADDR + 20) = 0;
        *(volatile uint32_t *)MARK_ADDR = MARK_ADDR; /* mark cell self-ptr    */
        *(volatile uint32_t *)DMARK_ADDR = 0;        /* dispatcher marker cell*/

        g_ac = (uint32_t)ac;
        g_disp_ret = (uint32_t)disp_ret;

        {
            int ret = rx8_os_task_scheduler(
                (uint8_t)tid, (uint16_t)eidx,
                (const uint32_t *)(uintptr_t)ARGS_ADDR,
                g_table, direct_stub);

            printf("%08lX %08lX %08lX %08lX %08lX %08lX %08lX %08lX %08lX\n",
                   (unsigned long)(uint32_t)ret,
                   (unsigned long)(uint32_t)*(volatile uint32_t *)MARK_ADDR,
                   (unsigned long)(uint32_t)*(volatile uint32_t *)REC_ADDR,
                   (unsigned long)(uint32_t)*(volatile uint32_t *)(REC_ADDR + 4),
                   (unsigned long)(uint32_t)*(volatile uint32_t *)(REC_ADDR + 8),
                   (unsigned long)(uint32_t)*(volatile uint32_t *)(REC_ADDR + 12),
                   (unsigned long)(uint32_t)*(volatile uint32_t *)(REC_ADDR + 16),
                   (unsigned long)(uint32_t)*(volatile uint32_t *)(REC_ADDR + 20),
                   (unsigned long)(uint32_t)*(volatile uint32_t *)DMARK_ADDR);
        }
    }
    return 0;
}

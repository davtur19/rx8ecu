/* ============================================================================
 * oracle_boot_entry.c  —  host test rig for the RX-8 boot-entry chain
 * ============================================================================
 * Compile together with src/rx8_boot_entry.c and pipe test vectors on stdin;
 * one vector per line, whitespace-separated hex tokens:
 *
 *     sw   <tid> <count> <kern_sr> <kern_sp>   ->  <ret> <sr> <sp> <saved> <ctl>
 *     sec                                 <op> ->  32 trace words
 *     main                                 <op> ->  <vbr> <fpscr> <sp>  32 trace
 *
 * Mode  `sw`   seeds the RTOS kernel parameters (task count, kernel SR and
 *              kernel SP) via the module setters, calls rx_task_context_switch,
 *              then prints the observable post-state:
 *                 ret      = r0 (0 for invalid id, else the init_main-tail
 *                          model result)
 *                 sr       = kernel SR, or unchanged 0x000000F0 for invalid id
 *                 sp       = kernel SP, or unchanged reset SP 0xFFFFDF00
 *                 saved    = [0xFFFF72D8] caller-SP cell (0 for invalid id)
 *                 ctl      = [0xFFFF72B8] RTOS ctl magic (0 for invalid id)
 * Mode  `sec`  calls rx_secondary_boot_main and prints the 8 call-trace cells
 *              (32 dwords, one line).
 * Mode  `main` calls rx_main_entry and prints its register image (vbr, fpscr,
 *              sp) followed by the same 32 trace dwords.
 *
 * The trace cells live at RX8_TRACE_BASE (0xFFFFE000, mmap()ed with MAP_FIXED);
 * the kernel cells at 0xFFFF72D8 / 0xFFFF72B8 are on the 0xFFFF7000 page, also
 * mmap()ed.  The oracle contains NO copy of the function logic — that lives in
 * src/rx8_boot_entry.c; it only mirrors caller-side seeding and reads the post
 * state (same trick as tests/host_oracle.c).
 * ==========================================================================*/
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

/* src/rx8_boot_entry.c API. */
void     rx_boot_kernel_count_set(uint8_t c);
void     rx_boot_kernel_sr_set(uint32_t v);
void     rx_boot_kernel_sp_set(uint32_t v);
uint32_t rx_boot_cpu_vbr_read(void);
uint32_t rx_boot_cpu_fpscr_read(void);
uint32_t rx_boot_cpu_sp_read(void);
uint32_t rx_boot_cpu_sr_read(void);
int      rx_task_context_switch(uint8_t task_id);
void     rx_secondary_boot_main(void);
void     rx_main_entry(void);
void     rx_boot_switch_reset(void);

#define RX8_TRACE_BASE  0xFFFFE000u
#define RX8_SAVED_SP    0xFFFF72D8u
#define RX8_CTL         0xFFFF72B0u

static void map_page(uintptr_t addr)
{
    long page = sysconf(_SC_PAGESIZE);
    uintptr_t base = (uintptr_t)addr & ~((uintptr_t)page - 1);
    void *p = mmap((void *)base, (size_t)page, PROT_READ | PROT_WRITE,
                   MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED, -1, 0);
    if (p == MAP_FAILED) { perror("mmap"); exit(1); }
}

static void print_trace(void)
{
    int c;
    for (c = 0; c < 8; c++) {
        volatile uint32_t *p = (volatile uint32_t *)((uintptr_t)RX8_TRACE_BASE + (uint32_t)c * 16);
        if (c) printf(" ");
        printf("%08X %08X %08X %08X", p[0], p[1], p[2], p[3]);
    }
    printf("\n");
}

int main(void)
{
    char line[256];
    map_page(RX8_TRACE_BASE);     /* trace cells @ 0xFFFFE000 -> 0xFFFF3000 page */
    map_page(RX8_SAVED_SP);       /* kernel cells on the 0xFFFF7000 page          */

    while (fgets(line, sizeof line, stdin)) {
        char op[8];
        unsigned long a, b, c2, d;
        if (sscanf(line, "sw %lx %lx %lx %lx", &a, &b, &c2, &d) == 4) {
            int ret;
            rx_boot_switch_reset();                  /* trampoline r15/SR reset */
            rx_boot_kernel_count_set((uint8_t)b);
            rx_boot_kernel_sr_set((uint32_t)c2);
            rx_boot_kernel_sp_set((uint32_t)d);
            *(volatile uint32_t *)RX8_SAVED_SP = 0;      /* clear context cells  */
            *(volatile uint32_t *)(RX8_CTL + 8) = 0;
            ret = rx_task_context_switch((uint8_t)a);
            printf("%08X %08X %08X %08X %08X\n",
                   (uint32_t)ret,
                   rx_boot_cpu_sr_read(),
                   rx_boot_cpu_sp_read(),
                   *(volatile uint32_t *)RX8_SAVED_SP,
                   *(volatile uint32_t *)(RX8_CTL + 8));
        } else if (sscanf(line, "%7s", op) == 1) {
            if (!strcmp(op, "sec")) {
                rx_secondary_boot_main();
                print_trace();
            } else if (!strcmp(op, "main")) {
                int c;
                rx_main_entry();
                printf("%08X %08X %08X", rx_boot_cpu_vbr_read(),
                       rx_boot_cpu_fpscr_read(), rx_boot_cpu_sp_read());
                for (c = 0; c < 8; c++) {
                    volatile uint32_t *p = (volatile uint32_t *)((uintptr_t)RX8_TRACE_BASE + (uint32_t)c * 16);
                    printf(" %08X %08X %08X %08X", p[0], p[1], p[2], p[3]);
                }
                printf("\n");
            } else {
                fprintf(stderr, "bad op: %s", line);
                return 2;
            }
        } else {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
    }
    return 0;
}
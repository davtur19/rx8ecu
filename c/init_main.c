/*
 * init_main.c  —  RX-8 PCM @ ROM 0x3E10 (60E1D400), hand-reconstructed
 *                  RTOS/System initialization function.
 *
 * This is the main RTOS initialization entry point, reached during boot via
 * secondary_boot_main (0xA038) -> task_context_switch (0x3AD8) -> jmp 0x3E10.
 * It sets up the RTOS control block, initializes the task queue, scans the
 * task table, configures task dependencies, and launches the context-switch
 * engine.  See docs/subsystems/BOOT_SEQUENCE.md §7–8.
 *
 * Parameter r4 = mode byte:
 *   0 = cold start (full init)
 *   1 = warm start (skip some steps)
 *
 * SH-2E calling convention: int args r4, return r0.
 *
 * Original SH-2E (big-endian, ~172 bytes from 0x3E10):
 *
 *   0x3E10: sts.l pr,@-r15         ; save pr
 *   0x3E12: mov r4,r0              ; r0 = mode (r4)
 *   0x3E14: mov.l 0x3e88,r1        ; r1 = ROM data ptr (RAM start?)
 *   0x3E16: mov.l 0x3e80,r14       ; r14 = RTOS control block base = 0xFFFF72B0
 *   0x3E18: mov.l 0x3e84,r2        ; r2 = ptr to initial SR value
 *   0x3E1A: mov.l @r2,r3           ; r3 = *(uint32_t*)r2 (initial SR)
 *   0x3E1C: mov.l r3,@(16,r14)     ; ctl->initial_sr = r3
 *   0x3E1E: mov.b r0,@(1,r14)      ; ctl->mode = r0
 *   0x3E20: mov.l @r1,r3           ; r3 = *(uint32_t*)r1 (RAM base?)
 *   0x3E22: mov #-1,r0             ; r0 = 0xFFFFFFFF
 *   0x3E24: mov.l r3,@(12,r14)     ; ctl->ram_base = r3
 *   0x3E26: mov.w r0,@(4,r14)      ; ctl->field_4 = 0xFFFF (-1)
 *   0x3E28: mov.l 0x3e8c,r3        ; r3 = 0x4990 (task config table ptr)
 *   0x3E2A: mov.l r3,@(24,r14)     ; ctl->task_config = r3
 *   0x3E2C: mov r3,r2              ; r2 = task_config ptr
 *   0x3E2E: mov.l @(4,r2),r3       ; r3 = task_config->field_4
 *   0x3E30: mov.l 0x3e90,r2        ; r2 = task_queue_init
 *   0x3E32: mov.l r3,@(20,r14)     ; ctl->field_20 = r3
 *   0x3E34: jsr @r2                ; task_queue_init(ctl)
 *   0x3E36: mov r14,r4             ; r4 = ctl (delay slot)
 *   0x3E38: mov.l 0x3e94,r3        ; r3 = task_table_scan_init
 *   0x3E3A: jsr @r3                ; task_table_scan_init(ctl)
 *   0x3E3C: mov r14,r4             ; r4 = ctl (delay slot)
 *   0x3E3E: mov.l 0x3e98,r2        ; r2 = task_dependency_handler
 *   0x3E40: jsr @r2                ; task_dependency_handler(ctl)
 *   0x3E42: mov r14,r4             ; r4 = ctl (delay slot)
 *   0x3E44: mov.l 0x3e9c,r3        ; r3 = task_set_current_ptr
 *   0x3E46: jsr @r3                ; task_set_current_ptr(ctl)
 *   0x3E48: mov r14,r4             ; r4 = ctl (delay slot)
 *   0x3E4A: mov.l 0x3ea0,r2        ; r2 = nullsub_2
 *   0x3E4C: jsr @r2                ; nullsub_2()
 *   0x3E4E: nop
 *   0x3E50: mov.l 0x3ea4,r3        ; r3 = nullsub_1
 *   0x3E52: jsr @r3                ; nullsub_1()
 *   0x3E54: nop
 *   0x3E56: mov.l 0x3ea8,r2        ; r2 = clear_task_flag_dc
 *   0x3E58: jsr @r2                ; clear_task_flag_dc(ctl)
 *   0x3E5A: mov r14,r4             ; r4 = ctl (delay slot)
 *   0x3E5C: mov.l 0x3eac,r3        ; r3 = clear_task_flag_dd
 *   0x3E5E: jsr @r3                ; clear_task_flag_dd(ctl)
 *   0x3E60: mov r14,r4             ; r4 = ctl (delay slot)
 *   0x3E62: mov.l 0x3eb0,r3        ; r3 = ptr to RAM flag
 *   0x3E64: mov.l @r3,r2           ; r2 = *r3 (flag value)
 *   0x3E66: tst r2,r2              ; test flag
 *   0x3E68: bt  0x3e70             ; if zero, skip
 *   0x3E6A: mov.l 0x3eb4,r2        ; r2 = task_flag_run_A
 *   0x3E6C: jsr @r2                ; task_flag_run_A()
 *   0x3E6E: nop
 *   0x3E70: mov.l 0x3eb8,r3        ; r3 = nullsub_3
 *   0x3E72: jsr @r3                ; nullsub_3()
 *   0x3E74: nop
 *   0x3E76: mov r14,r4             ; r4 = ctl
 *   0x3E78: mov.l 0x3ebc,r2        ; r2 = 0x3C2A (task_full_context_save)
 *   0x3E7A: jmp @r2                ; goto task_full_context_save(ctl)
 *   0x3E7C: lds.l @r15+,pr         ; restore pr (delay slot — never executed)
 */
#include <stdint.h>

/* ------------------------------------------------------------------ */
/*  ROM data layout                                                    */
/* ------------------------------------------------------------------ */

/* RTOS Control Block structure in RAM (at 0xFFFF72B0) */
struct RtosControlBlock {
    uint8_t  pad_0[1];          /* +0:  (unknown) */
    uint8_t  mode;              /* +1:  init mode (0=cold, 1=warm) */
    uint8_t  pad_2_3[2];        /* +2:  (unknown) */
    uint16_t field_4;           /* +4:  init value 0xFFFF */
    uint8_t  pad_6_11[6];       /* +6:  (unknown) */
    uint32_t ram_base;          /* +12: RAM base address */
    uint32_t initial_sr;        /* +16: initial status register value */
    uint32_t field_20;          /* +20: task config->field_4 copy */
    uint32_t task_config;       /* +24: pointer to task config table @ 0x4990 */
};

/* Pointers to ROM data tables loaded via mov.l @(disp,PC) */
#define CTL_BLOCK_BASE      (*(volatile uint32_t *)0x3E80)  /* = 0xFFFF72B0 */
#define INIT_SR_PTR         (*(uint32_t *)0x3E84)            /* = ptr to init SR value @ 0x4B04 */
#define RAM_BASE_PTR        (*(uint32_t *)0x3E88)            /* = ptr to RAM base @ 0x4938 */
#define TASK_CONFIG_TABLE   (*(uint32_t *)0x3E8C)            /* = ptr to task config @ 0x4990 */

/* Sub-function addresses */
#define TASK_QUEUE_INIT         ((void (*)(struct RtosControlBlock *))(uintptr_t)0x3964)
#define TASK_TABLE_SCAN_INIT    ((void (*)(struct RtosControlBlock *))(uintptr_t)0x3EC0)
#define TASK_DEPENDENCY_HANDLER ((void (*)(struct RtosControlBlock *))(uintptr_t)0x3F10)
#define TASK_SET_CURRENT_PTR    ((void (*)(struct RtosControlBlock *))(uintptr_t)0x3AC0)
#define NULLSUB_2               ((void (*)(void))(uintptr_t)0x3F8C)
#define NULLSUB_1               ((void (*)(void))(uintptr_t)0x3F88)
#define CLEAR_TASK_FLAG_DC      ((void (*)(struct RtosControlBlock *))(uintptr_t)0x3F90)
#define CLEAR_TASK_FLAG_DD      ((void (*)(struct RtosControlBlock *))(uintptr_t)0x3F9C)
#define TASK_FLAG_RUN_A         ((void (*)(void))(uintptr_t)0x3588)
#define NULLSUB_3               ((void (*)(void))(uintptr_t)0x3FA8)
#define TASK_FULL_CONTEXT_SAVE  ((void (*)(struct RtosControlBlock *))(uintptr_t)0x3C2A)

/* The flag checked before calling task_flag_run_A */
#define RAM_FLAG_CHECK          (*(uint32_t *)0x4B14)

/* ------------------------------------------------------------------ */
/*  init_main  —  RTOS initialization entry point                      */
/* ------------------------------------------------------------------ */

/**
 * init_main  —  Initialize the RTOS subsystem.
 *
 * @param mode  0 = cold start (full initialization),
 *               1 = warm start (skip some steps).
 *
 * This function is the C equivalent of the code at 0x3E10.
 * It sets up the RTOS control block, tasks queue, task table,
 * dependency graph, and then enters the context-save/idle state.
 * Called via tail-jump from task_context_switch (0x3AD8) with mode = 0.
 */
void init_main(uint8_t mode)
{
    /* The RTOS control block lives at a fixed RAM address */
    volatile struct RtosControlBlock *ctl =
        (volatile struct RtosControlBlock *)(uintptr_t)CTL_BLOCK_BASE;

    /* --- Initialize control block fields --- */

    /* Read the initial SR value from a ROM pointer */
    uint32_t initial_sr = *(uint32_t *)INIT_SR_PTR;
    ctl->initial_sr = initial_sr;

    /* Store the init mode */
    ctl->mode = mode;

    /* Read the RAM base pointer from a ROM pointer */
    uint32_t ram_base = *(uint32_t *)RAM_BASE_PTR;
    ctl->ram_base = ram_base;

    /* Set field_4 to -1 (0xFFFF) */
    ctl->field_4 = 0xFFFFu;

    /* Load the task configuration table pointer */
    uint32_t task_config = TASK_CONFIG_TABLE;
    ctl->task_config = task_config;

    /* Read field_4 from the task config table */
    const uint32_t *config_ptr = (const uint32_t *)(uintptr_t)task_config;
    ctl->field_20 = config_ptr[1];

    /* --- Call initialization subroutines --- */

    /* Initialize the circular task queue */
    TASK_QUEUE_INIT(ctl);

    /* Scan the task table and initialize each task's control block */
    TASK_TABLE_SCAN_INIT(ctl);

    /* Set up task dependency chains */
    TASK_DEPENDENCY_HANDLER(ctl);

    /* Set the current task pointer to idle/system task */
    TASK_SET_CURRENT_PTR(ctl);

    /* Placeholder nullsub calls */
    NULLSUB_2();
    NULLSUB_1();

    /* Clear task flags */
    CLEAR_TASK_FLAG_DC(ctl);
    CLEAR_TASK_FLAG_DD(ctl);

    /* If a RAM-resident flag is set, trigger task_flag_run_A */
    if (RAM_FLAG_CHECK != 0) {
        TASK_FLAG_RUN_A();
    }

    /* Final placeholder nullsub */
    NULLSUB_3();

    /* Jump to task_full_context_save — this does not return.
     * The context-save function initializes the idle loop and starts
     * the scheduler.  From this point on, the RTOS is running. */
    TASK_FULL_CONTEXT_SAVE(ctl);

    /* NOT REACHED */
}

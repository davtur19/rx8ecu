/*
 * =============================================================================
 * rx8_task_execute_by_index.c  —  OS TASK SCHEDULER: DISPATCH A TASK BY INDEX
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x3854
 * Status      : VERIFIED — behavioural equivalence to the ROM held by
 *               reconstructed/samples/tests/harness_task_execute_by_index.py
 *               (host-gcc vs tools/sh2emu.py over random + edge vectors;
 *               bit-exact return value, RAM side-effects, final SR AND the
 *               four callee call-boundaries; 0 mismatches).
 * Lift (truth): c/task_execute_by_index.c  (task_execute_by_index @ 0x3854)
 *
 * WHAT THIS IS
 * ------------
 * The core task-dispatch helper of the RX-8 PCM OS layer (called from ~14
 * sites).  Given a task index it looks the task up in the kernel task table
 * (16-byte entries at 0x4990), reads the task's run counter, and:
 *   - counter == 0  -> the task is not runnable: return code 4 (and, when the
 *     kernel flag at 0x4B08 is set, poke the interrupt-priority dispatcher
 *     0x3610 with (4, 1, os_ctrl->status) before returning);
 *   - otherwise     -> decrement the counter, call the per-task execution
 *     helper 0x39BA (helper(os_ctrl, index, priority)); when the helper asks
 *     for a context switch ((result) != 0) AND the saved-IPL/status gate
 *     ((saved_sr & 0x00F0) | os_ctrl->status) == 0 AND the context-save
 *     state block's gate byte (+1) == 0, record the switch request
 *     (os_ctrl->status = 0x0100), optionally raise the task-running-flag
 *     barrier 0x35EE (when the kernel flag at 0x4B10 is set) and call the
 *     full-context-save routine 0x3BF4.  Every dispatched path returns 0.
 *
 * ROM BODY (disassembled 60E1D400.bin @ 0x3854; constant pool @ 0x38FA..0x3920:
 *   0x3900 = 0xFFFF72B0 os_ctrl | 0x3904 = 0x4990 task_table |
 *   0x3908 = 0x39BA helper | 0x390C = 0x4B10 flag | 0x3910 = 0x35EE flag_run_C |
 *   0x3914 = 0x3BF4 ctx_save | 0x3918 = 0x4B08 flag | 0x391C = 0x3610 ipd):
 *
 *     2FE6/2FD6/2FC6 mov.l r14,r13,r12,@-r15    ; prologue
 *     0D02   stc  sr,r13                        ; r13 = saved_sr (entry SR)
 *     DE28   mov.l @0x3900,r14                  ; r14 = os_ctrl (0xFFFF72B0)
 *     EC00   mov  #0x00,r12                     ; r12 = 0 (return code)
 *     D328   mov.l @0x3904,r3                   ; r3  = task_table (0x4990)
 *     2FB6/4F22 sts.l pr,r11                    ; push r11, pr
 *     7FFC   add  #0xFC,r15
 *     2F41   mov.w r4,@r15                      ; *(u16)sp = task index
 *     6BF1   mov.w @r15,r11                     ; r11 = (int16)(u16)index
 *     52E4   mov.l @(0x10,r14),r2               ; r2  = os_ctrl->saved_sr (+16)
 *     4B08/4B08 shll2 r11 x2                    ; r11 = index * 16
 *     3B3C   add  r3,r11                        ; r11 = &task_table[index]
 *     54B1   mov.l @(0x4,r11),r4                ; r4  = entry->state_ptr (+4)
 *     420E   ldc  r2,sr                         ; sr  = os_ctrl->saved_sr
 *     8443   mov.b @(0x3,r4),r0                 ; r0  = task->counter (+3)
 *     2008   tst  r0,r0 / 8B02 bf 0x3884        ; counter != 0 -> runnable
 *     ; -- not runnable --
 *     4D0E   ldc  r13,sr / A02A bra 0x38D8 / EC04 mov #0x04,r12
 *     38D8:  D30F mov.l @0x3918,r3 / 6232 mov.l @r3,r2   ; r2 = *(0x4B08)
 *            2228 tst r2,r2 / 8904 bt 0x38EA    ; flag clear -> skip
 *            56E2 mov.l @(0x8,r14),r6           ; r6 = os_ctrl->status
 *            E501 mov #0x01,r5 / D20D mov.l @0x391C,r2
 *            420B jsr @r2 / E404 mov #0x04,r4   ; ipd(4,1,status)
 *     ; -- runnable --
 *     3884:  D320 mov.l @0x3908,r3              ; r3 = 0x39BA (helper)
 *            70FF add #0xFF,r0                  ; r0 = s8(counter) - 1
 *            8043 mov.b r0,@(0x3,r4)            ; task->counter = low byte
 *            84B2 mov.b @(0x2,r11),r0           ; r0 = s8(entry->priority)
 *            65F1 mov.w @r15,r5                 ; r5 = (int16)(u16)index
 *            6603 mov r0,r6 / 430B jsr @r3 / 64E3 mov r14,r4
 *                                                ; helper(os_ctrl,index,prio)
 *            2008 tst r0,r0 / 891C bt 0x38D2    ; result == 0 -> restore, ret
 *            ; -- helper asked for a context switch --
 *            932F mov.w @0x38FA,r3              ; r3 = 0x00F0
 *            23D9 and r13,r3 / 52E2 mov.l @(0x8,r14),r2
 *            232B or r2,r3 / 2338 tst r3,r3     ; (saved_sr&0xF0)|status
 *            8F13 bf/s 0x38CC / 5BE6 mov.l @(0x18,r14),r11
 *                                                ; != 0 -> restore SR, ret
 *            84B1 mov.b @(0x1,r11),r0           ; r0 = state_block[+1]
 *            2008 tst r0,r0 / 8B0F bf 0x38CC    ; != 0 -> restore SR, ret
 *            9226 mov.w @0x38FC,r2 / 1E22 mov.l r2,@(0x8,r14)
 *                                                ; os_ctrl->status = 0x0100
 *            D116 mov.l @0x390C,r1 / 6312 mov.l @r1,r3   ; r3 = *(0x4B10)
 *            2338 tst r3,r3 / 8902 bt 0x38BE    ; flag clear -> skip
 *            D315 mov.l @0x3910,r3 / 430B jsr @r3 / E402 mov #0x02,r4
 *                                                ; task_flag_run_C(2)
 *            38BE: 66B3 mov r11,r6 / D214 mov.l @0x3914,r2
 *            65D3 mov r13,r5 / 420B jsr @r2 / 64E3 mov r14,r4
 *                                                ; ctx_save(os_ctrl,sr,state)
 *            A00F bra 0x38EA                    ; NOTE: NO ldc r13,sr here
 *            38CC/38D2: ldc r13,sr / bra 0x38EA ; restore SR, exit
 *     ; -- exit --
 *     38EA:  60C3 mov r12,r0 / 7F04 add #0x04,r15 / 4F26 lds.l @r15+,pr
 *            6BF6/6CF6/6DF6 mov.l @r15+,r11,r12,r13
 *            000B rts / 6EF6 mov.l @r15+,r14    ; (delay)
 *
 * CALLING CONVENTION
 * ------------------
 * ABI entry (r4 = task index).  The index is stored to the stack with
 * `mov.w` and reloaded twice, so it is truncated to 16 bits.  Returns
 * r0 = 0 (dispatched) or r0 = 4 (task not runnable).
 *
 * DISCREPANCIES vs the c/ lift
 * ----------------------------
 *  * The lift's C body is a structural STUB (`(void)task_index; return 0;`)
 *    — it is NOT a working implementation.  Its header asm trace is accurate
 *    and was used as the starting point; the code below is reconstructed from
 *    the ROM bytes and verified against them.
 *  * The ROM reads the task table at fixed ROM address 0x4990 and two kernel
 *    flag words at fixed RAM addresses 0x4B08 / 0x4B10.  All three lie below
 *    the host's mmap_min_addr, so — following the rx8_task_flag_run_c.c
 *    convention — they are modelled as parameters (`task_table`,
 *    `kern_flag_4B08`, `kern_flag_4B10`).  Bit-exactness is unaffected: the
 *    harness seeds byte-identical values on the emulator side (ram overlay at
 *    0x4990 / 0x4B08 / 0x4B10) and on the host.
 *  * The run counter is decremented on the SIGN-EXTENDED byte
 *    (`add #0xFF` after the sign-extending `mov.b @(3,r4),r0`), i.e.
 *    `task[3] = (uint8_t)((int8_t)task[3] - 1)` — a plain uint8 decrement
 *    differs for counters >= 0x80.
 *  * The priority passed to the execution helper is the SIGN-EXTENDED byte at
 *    table entry +2 (`mov.b` sign-extends; helper r6 = (int8_t)priority).
 *  * The helper's index argument is the sign-extended 16-bit index
 *    (`mov.w @r15,r5`), i.e. `(int16_t)(uint16_t)task_index`.
 *  * The full-context-save path ends with `bra 0x38EA` WITHOUT restoring SR
 *    (every other exit does `ldc r13,sr`): the final SR is path-dependent
 *    (see the harness, which compares it).
 *
 * SR MODEL
 * --------
 * The ROM reads SR once at entry (`stc sr,r13`), switches to the OS control
 * block's saved SR during dispatch (`ldc r2,sr`) and restores the entry SR at
 * every exit except the full-context-save path.  A plain uint32 SR register
 * is kept, exactly like the other samples (cf. rx8_get_sr.c); the harness
 * seeds it per vector and reads it back.
 * =============================================================================
 */
#include <stdint.h>

#include "rx8_samples.h"

/* OS control block (base 0xFFFF72B0; mappable on the host oracle). */
#define OS_CTRL_BASE       0xFFFF72B0u
#define OS_CTRL_STATUS     8u     /* +8  u32 status word                  */
#define OS_CTRL_SAVED_SR   16u    /* +16 u32 saved status register        */
#define OS_CTRL_STATE_BLK  24u    /* +24 u8* full-context-save state blk  */

/* Task table entry layout (16 bytes per entry at 0x4990 on the ROM). */
#define TE_PRIORITY        2u     /* +2  u16 priority (byte +2 is read)   */
#define TE_STATE_PTR       4u     /* +4  u8* task state block             */
#define TE_ENTRY_SIZE      16u    /* table stride                         */

/* Task state block offsets (pointed to by the table entry). */
#define TS_GATE_FLAG       1u     /* +1  u8 context-save gate byte        */
#define TS_COUNTER         3u     /* +3  u8 run counter                   */

/* Kernel flag addresses (fixed RAM; modelled as parameters, see header). */
#define KERN_FLAG_4B08     0x00004B08u   /* interrupt-priority dispatch   */
#define KERN_FLAG_4B10     0x00004B10u   /* task-running-flag barrier     */

/* ---------------------------------------------------------------------------
 * SR register model — same arrangement as rx8_get_sr.c (host harness only;
 * these accessors are NOT part of the firmware contract).
 * ------------------------------------------------------------------------- */
static uint32_t _sr = 0x000000F0u;
void rx8_sr_set_state(uint32_t sr) { _sr = sr; }
uint32_t rx8_sr_get_state(void) { return _sr; }

/* OS-layer callees, reached through the ROM constant pool
 * 0x3908/0x3910/0x3914/0x391C (stubbed by the oracle on both sides). */
extern uint32_t rx8_task_execute_helper(uint32_t *os_ctrl, uint32_t index,
                                        int32_t priority);        /* 0x39BA */
extern void     rx8_task_flag_run_c(int arg);                     /* 0x35EE */
extern void     rx8_task_full_context_save(uint32_t *os_ctrl,
                                           uint32_t saved_sr,
                                           uint8_t *state_block);  /* 0x3BF4 */
extern void     rx8_interrupt_priority_dispatch(int arg1, int arg2,
                                                uint32_t status);  /* 0x3610 */

/* 0x3854  execute the task at table index `task_index`                      */
int rx8_task_execute_by_index(int task_index,
                              const uint8_t *task_table,
                              uint32_t kern_flag_4B08,
                              uint32_t kern_flag_4B10)
{
    volatile uint32_t *os = (volatile uint32_t *)OS_CTRL_BASE;
    const uint8_t *entry;
    uint8_t *task;
    uint32_t saved_sr = _sr;                       /* stc sr,r13           */

    entry = task_table + (uint32_t)(uint16_t)task_index * TE_ENTRY_SIZE;
    task  = (uint8_t *)(uintptr_t)
            *(uint32_t *)(void *)(entry + TE_STATE_PTR);   /* mov.l @(4,r11) */

    _sr = os[OS_CTRL_SAVED_SR / 4];                /* ldc r2,sr (OS saved) */

    /* Run counter == 0 -> not runnable: r12 = 4. */
    if (task[TS_COUNTER] == 0) {                   /* mov.b @(3,r4); tst   */
        _sr = saved_sr;                            /* ldc r13,sr @0x387E   */
        if (kern_flag_4B08 != 0) {                 /* *(u32*)0x4B08        */
            rx8_interrupt_priority_dispatch(4, 1, os[OS_CTRL_STATUS / 4]);
        }
        return 4;
    }

    /* Decrement the run counter (sign-extended-byte semantics). */
    task[TS_COUNTER] = (uint8_t)((int8_t)task[TS_COUNTER] - 1);

    /* Dispatch to the per-task execution helper:
     *   helper(os_ctrl, index, priority)   (r4=os_ctrl, r5=(int16)index,
     *   r6=(int8)priority — both bytes sign-extended by the ROM). */
    if (rx8_task_execute_helper((uint32_t *)(void *)os,
                                (uint32_t)(int16_t)(uint16_t)task_index,
                                (int8_t)entry[TE_PRIORITY]) == 0) {
        _sr = saved_sr;                            /* ldc r13,sr @0x38D2   */
        return 0;
    }

    /* Helper asked for a context switch: gate it on the saved IPL bits and
     * the OS status word, then on the context-save state block gate byte. */
    {
        uint8_t *state = (uint8_t *)(uintptr_t)
                         os[OS_CTRL_STATE_BLK / 4];   /* mov.l @(0x18,r14)  */
        if (((saved_sr & 0x00F0u) | os[OS_CTRL_STATUS / 4]) != 0) {
            _sr = saved_sr;                        /* ldc r13,sr @0x38CC   */
            return 0;
        }
        if (state[TS_GATE_FLAG] != 0) {            /* mov.b @(1,r11); tst  */
            _sr = saved_sr;                        /* ldc r13,sr @0x38CC   */
            return 0;
        }

        os[OS_CTRL_STATUS / 4] = 0x0100u;          /* mov.w #0x0100; mov.l */
        if (kern_flag_4B10 != 0) {                 /* *(u32*)0x4B10        */
            rx8_task_flag_run_c(2);                /* jsr 0x35EE, r4 = 2   */
        }
        rx8_task_full_context_save((uint32_t *)(void *)os, saved_sr,
                                   state);          /* jsr 0x3BF4          */
        /* NOTE: this exit does NOT restore SR (bra 0x38EA, no ldc). */
        return 0;
    }
}

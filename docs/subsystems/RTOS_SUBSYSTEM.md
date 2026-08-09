# RTOS / Task Scheduling Subsystem — RX-8 PCM (60E1D400)

**Target:** 60E1D400.bin (SH-2E, big-endian, Renesas SH7055)
**Scope:** Cooperative multitasking RTOS — queue dispatcher, priority scheduling, context switching, initialization. Reset → RTOS-start chain: see `BOOT_SEQUENCE.md`.

## 1. Architecture Overview

Cooperative (non-preemptive) multitasking RTOS: circular task queue, priority-driven dispatch, dependency management. Tasks run to completion (yield explicitly); interrupts post to the task queue.

| Aspect | Implementation |
|--------|---------------|
| Scheduler | Cooperative, non-preemptive, priority-driven with queue |
| Task queue | Circular buffer, 100 entries, fixed RAM |
| Task table | ROM pointer table @0xDB14, up to 27 tasks + system |
| Dispatch | Direct call (`marker==0xFFFF`) or routed through a dispatcher (marker = dispatch key) |
| Context switch | Full register save/restore with SR management |
| Timing | ATU timer interrupts drive periodic scheduling |

### Memory Map
| Address | Purpose |
|---------|---------|
| 0x00000000 | Exception vector table (32 × 4B) |
| 0x0000DB14 | Task pointer table (uint32_t[]) |
| 0x0000D9E4 | Task descriptor table (8B entries) |
| 0x0000DBDC | Task 1 entry array (scheduling) |
| 0x0000DC64 | Task 0 entry array (init/system) |
| 0x0000A12E..A3D0 | Task stub functions (~30 × 28B) |
| 0xFFFF72B0 | RTOS control block |
| 0xFFFF9304 | Task state/priority tracking base |
| 0x00000400 | Queue head ptr · 0x0404 tail ptr · 0x0414 queue entry base |

## 2. Exception Vector Table

| Vector | Offset | Address | Symbol | Description |
|--------|--------|---------|--------|-------------|
| 0 | 0x0000 | 0x000008B8 | Manual_Reset | Initial PC |
| 1 | 0x0004 | 0xFFFFDFA0 | — | Initial SP |
| 2 | 0x0008 | 0x000008B8 | Manual_Reset | Reserved |
| 4–13 | 0x0010–0x0034 | 0x000008B4 | — | General exception / illegal instruction handler |
| 14–15 | 0x0038–0x003C | 0xFFFFFFFF | — | Unused |

Vectors 4–13 point to trampoline 0x8B4 (unhandled exceptions).

Reset sequence: `Vector0 → Manual_Reset (0x8B8) → bsc_init(0x8CC) → gpio_init(0x8F6) → resetHandler(0x4E0) → infinite loop (0x8C8)`.

## 3. Initialization Chain

### `resetHandler` (0x4E0) — `int resetHandler(int cold_start, uint8_t reason)`
1. Watchdog reset → `resetWatchdog` (0x572, WDT magic writes).
2. HW init: `hw_init_1` (0x0170, Clock/PLL/FRT) · `hw_init_2` (0x041C, BSC/memory) · `hw_init_3` (0x03D4, peripherals).
3. **Cold/warm start**: compares magic `0x5AA5A55A` at `*(uint32_t*)0xFFFFDFFC`; mismatch → cold start, check watchdog (0x5B0).
4. Watchdog recovery: `checkWatchdogTimer_OVRCOUNT(7)` on overflow; reset cause from `0x7FFFC`/`0x7FFF8`; chosen vector r13 = 0x6C8 (default serial loop) / `[0x1000]`=0x12B4 (app entry) / `[0x7FFF8]`=0xD49C (main entry).
5. Final: store magic at 0xFFFFDFFC; `vector_trampoline_set_sp` (0x0040) sets SP=0xFFFFDFA0, tail-jumps to chosen vector. Infinite loop @0x56E.

### `secondary_boot_main` (0xA038) — RTOS start
```
peripheral_init_chain_A (0x4C80) → secondary_peripheral_initializer (0xD7B0)
→ sfr_write_a16c: [0xFFFFA16C]=0 → setSR_PARAM (0x2054, mask 0xE0)
→ setRegister_REG_BIT_VAL (0x4BBC): bit 8 of SFR 0xF74E
→ loadStatusRegister_ADDR (0x2064) → sfr_init_dma_channels (0x4CF8)
→ task_context_switch (0x3AD8) — start RTOS → idle loop (0xA06E)
```
`task_context_switch` (0x3AD8) validates `task_id < [0x4B00]` (count=1), saves caller SP to 0xFFFF72D8, loads kernel SR/SP from [0x4B04]/[0x4938], **tail-jumps to RTOS init 0x3E10**.

### `engine_startup_initialization` (0xAD5A)
Engine-specific startup: sensor states, fuel/ignition defaults, calibration data, before scheduler start.

## 4. RTOS Core — Task Scheduler

### Task Data Structures

**Task pointer table @0xDB14** (ROM, indexed by task_id):

| Index | Pointer | Type | Description |
|-------|---------|------|-------------|
| 0 | 0xDC64 | TaskEntry[] | System init/control tasks |
| 1 | 0xDBDC | TaskEntry[] | Scheduling/timer dispatch tasks |
| 2 | 0x06873C | — | External memory/device handler |
| 3–26 | 0xA12E..0xA3D0 | Stub ptrs | Application task stubs |
| 27+ | (end) | — | Unused |

**TaskEntry** (8 bytes, packed): `{uint16_t marker; uint16_t arg_count; uint32_t func_ptr;}`. `marker==0xFFFF` → call func_ptr directly (stack frame w/ copied args passed as first param); else call dispatcher 0x5F34 with marker as key (returns 0 done / 1 re-queued).

**Task 0 entries @0xDC64:**

| Entry | Marker | Args | Function | Description |
|-------|--------|------|----------|-------------|
| 0 | 0x0002 | 0 | 0xD9C4 | No-op placeholder |
| 1 | 0xFFFF | 1 | 0x11F68 | Direct init step A |
| 2 | 0xFFFF | 0 | 0x11F5C | Direct init step B |
| 3 | 0xFFFF | 0 | 0x11F62 | Direct init step C |
| 4 | 0xFFFF | 2 | 0x11F74 | Direct init step D |

**Task 1 entries @0xDBDC:**

| Entry | Marker | Args | Function | Description |
|-------|--------|------|----------|-------------|
| 0–3 | 0x0000–0x0003 | 1 | 0x666C/0x6676/0x6680/0x668A | Dispatch: fwd arg + handler |
| 4 | 0x0002 | 0 | 0x6694 | Dispatch no-arg |
| 5 | 0x0000 | 1 | 0x66A8 | Dispatch: fwd arg |
| 6–8 | 0x0003/0x0003/0x0000 | 0 | 0x66D0/0x66D6/0x66CA | Dispatch no-arg |
| 9 | 0x0002 | 1 | 0x11F88 | Dispatch: fwd arg |
| 10 | 0x0003 | 1 | 0x121B8 | Dispatch: fwd arg |
| 11 | 0xFFFF | 0 | 0x12198 | Direct-call handler |

### Task Stubs @0xA12E–0xA3D0 (28B each)
Pattern: save PR → `jsr 0x3854` (`task_execute_by_index`) w/ TASK_ID → if r0==0 skip (not ready) → else `jmp 0xA486` (`calledLots`, schedule wrapper) → restore PR.

| Stub | Task ID | Stub | Task ID | Stub | Task ID |
|------|---------|------|---------|------|---------|
| 0xA12E | 7 | 0xA1F2 | 13 | 0xA2B6 | 1 |
| 0xA14A | 8 | 0xA20E | 14 | 0xA2D2 | 38 |
| 0xA166 | 9 | 0xA22A | 15 | 0xA2EE | 9 (dup) |
| 0xA182 | 18 | 0xA246 | 16 | 0xA30A | 46 |
| 0xA19E | 10 | 0xA262 | 66 | 0xA326 | 252 |
| 0xA1BA | 11 | 0xA27E | 188 | 0xA342 | 66 (dup) |
| 0xA1D6 | 12 | 0xA29A | 43 | 0xA35E | 1 (dup) |
| — | — | — | — | 0xA37A | 38 (dup) |
| — | — | — | — | 0xA396 | 9 (dup) |
| — | — | — | — | 0xA3B2 | 0 (special) |
| — | — | — | — | 0xA3CE | 37 |
| — | — | — | — | 0xA3EA | 66 (dup) |

*Duplicate task IDs may indicate shared priority groups or multiple entry points for the same logical task.*

Stub constant pool: `task_execute_by_index` (0x3854) and `task_dispatch_trampoline` (0xA486, aka `calledLots`).

### `osTaskScheduler` (0x9668) — central dispatch
Given task_id, entry_idx, optional args: selects task entry, copies args to stack frame, calls function directly or passes to priority dispatcher. Detail: `docs/functions/osTaskScheduler.md`, `c/osTaskScheduler.c`. Constants: `[0x9780]`=0x0000DB14 (table base) · `[0x9784]`=0x0000FFFF (marker sentinel) · `[0x9788]`=0x00005F34 (dispatcher).

### `task_handler_run_by_index` (0x5F34) — priority dispatcher
`int task_handler_run_by_index(uint16_t marker_id, uint32_t *frame)`. Flow: look up marker in task descriptor table @0xD9E4 (8B entries) → `getSR()` (0x3920) → check task state @0xFFFF9304+marker*3 → empty queue: `task_execute_by_index` (0x3854); pending: `schedule_wrapper` (0xA486); copy args; update counters; `setSR()` (0x3934).
Return: 0 normal · 1 re-queued · 2 queue full/skipped · 3 init skipped (counter not ready).

### `task_handler_init_and_run` (0x6034)
Like 0x5F34 with init steps; for one-shot startup tasks.

### `task_execute_by_index` (0x3854)
`int task_execute_by_index(uint8_t task_id)`: reads RTOS control block (0xFFFF72B0); checks dependency counter; if >0 decrement + ready; may trigger context switch on pending interrupts. Returns 0 = not ready (skip) / non-zero = ready (call dispatch wrapper).

### Circular Task Queue (100 entries)
| Address | Size | Description |
|---------|------|-------------|
| 0x0400 | u16 | Queue head (write) |
| 0x0404 | u16 | Queue tail (read) |
| 0x0414 | 100×8B | Queue entry array |

- `task_scheduler_dispatch` (0x364): read head, dispatch next, counter wraps at 100.
- `task_queue_get_next` (0x3B0): next entry, tail++ wraps at 100.
- `task_queue_pending_count` (0x3E0): `(head - tail) % 100`.

### Context Switching
- `task_context_save_enter` (0x3238): saves r2–r7 to stack, increments context counter (ISR/switch entry).
- `task_context_switch` (0x3AD8): validate priority; save SR/PR; save SP to TCB; load new SP; restore SR; jump to execution point.
- `task_full_context_save` (0x3BF4): full callee-saved register save (idle → task transitions).

### Task State Management
- `task_flag_run_A/B/C` (0x3588/0x35CC/0x35EE): OR flag bit into RTOS control block → call registered handler → clear with AND-NOT. Interrupt handlers use these to trigger task-level processing.
- `task_ready_check` (0x3FB0): validate index vs max; look up ready flag bitmask; return 0 ready / 3 not.
- `task_state_mapper` (0xAC94): maps ECU state (ignition, engine running) → task state code (enables/disables task groups).

### Initialization Functions
- `task_queue_init` (0x3964): read CPU stepping; clear queue; set up dispatch ptrs; init slots to −1.
- `task_table_scan_init` (0x3EC0): iterate tasks; set inactive + default counters; per-task init.
- `task_dependency_handler` (0x3F10): read dependency list; decrement counters; enable dependents when satisfied (through a descriptor table).
- **RTOS init @0x3E10** (reached through boot → `task_context_switch` → jmp 0x3E10; mode r4=0 cold): set up control block @0xFFFF72B0, store mode, read RAM start + descriptor ptr, then `task_queue_init` (0x3964) → `task_table_scan_init` (0x3EC0) → `task_dependency_handler` (0x3F10) → `task_set_current_ptr` (0x3AC0) → nullsubs (0x3F8C, 0x3F88) → `clear_task_flag_dc/dd` (0x3F90, 0x3F9C) → if RAM flag set: `task_flag_run_A` (0x3588) → nullsub_3 (0x3FA8) → jump `task_full_context_save` (0x3C2A).

### Schedule Wrapper `calledLots` (0xA486)
Save SR → save task_id → `setSR_PARAM` (0x2054) → read counter `*(uint8_t*)(0xFFFFA18B + task_id)` → if <0xFF increment → `setSR` (0x2064) → return.

## 5. Task Dispatch Flow

```
Interrupt/timer posts to queue
  → task_scheduler_dispatch (0x364) reads queue, dispatches next
      ├─ System tasks (0-1): osTaskScheduler (0x9668) reads TaskEntry array @0xDC64/0xDBDC
      └─ App tasks (3-26): stub (0xA12E+) → task_execute_by_index (0x3854) check
            → calledLots (0xA486) counter+priority
            → osTaskScheduler (0x9668) or task_handler_run_by_index (0x5F34)
                marker==0xFFFF → direct call · else dispatcher @5F34 (queue mgmt, arg copy, counters)
```

## 6. Interrupt Handling

- `interrupt_priority_dispatch` (0x3610): masks request vs current SR; tests RTOS control block flags; maps to priority levels (5, 6, 7, 8, 3, 0); returns handler index.
- `serial_rx_handler_ch0/1/2` @0x004C, 0x0064, 0x00C0 — SCI RX handlers.
- `atu_timer_init` @0x10AC · `atu_capture_compare_init` @0x4F08.
- `intc_clear_flag_ec26`/`trampoline` @0x5286/0x528E.

## 7. RTOS Constants

| Address | Value | Description |
|---------|-------|-------------|
| 0x9780 | 0x0000DB14 | Task pointer table base |
| 0x9784 | 0x0000FFFF | Direct-call marker sentinel |
| 0x9788 | 0x00005F34 | Priority dispatcher |
| 0x978C | 0xFFFF9304 | Task control block base |
| 0x9790 | 0xFFFFA118 | Task flag table |
| 0x9794 | 0x00002054 | setSR_PARAM |
| 0x9798 | 0x00006034 | task_handler_init_and_run |
| 0x979C | 0x00002064 | setSR |
| 0xA3C4 | 0x00003854 | task_execute_by_index |
| 0xA3C8 | 0x0000A486 | calledLots |
| 0xA3CC | 0x00009668 | osTaskScheduler |
| 0xFFFF72B0 | — | RTOS control block |
| 0xFFFF9304 | — | Task state/priority tracking |
| 0xFFFFA18B | — | Per-task execution counter table |

## 8. Key Functions

| Address | Name | Role |
|---------|------|------|
| 0x08B8 | Manual_Reset | Reset vector entry |
| 0x04E0 | resetHandler | Main init/reset |
| 0x0170 / 0x041C / 0x03D4 | hw_init_1/2/3 | Clock/PLL · BSC · peripherals |
| 0x08CC / 0x08F6 | bsc_init / gpio_init | BSC · GPIO |
| 0xA038 | secondary_boot_main | Second-stage boot + RTOS start |
| 0xA0CE | whileLoop | Idle loop (interrupts off) |
| 0xD97C | fpu_context_save_restore | FPU context |
| 0x364 / 0x3B0 / 0x3E0 | task_scheduler_dispatch / task_queue_get_next / task_queue_pending_count | Queue ops |
| 0x3964 / 0x3EC0 / 0x3F10 / 0x3AC0 | task_queue_init / task_table_scan_init / task_dependency_handler / task_set_current_ptr | Init |
| 0x3AD8 / 0x3238 / 0x3BF4 | task_context_switch / task_context_save_enter / task_full_context_save | Context |
| 0x3D58 | taskEndRoutine? | Task termination |
| 0x3FB0 | task_ready_check | Ready check |
| 0x3854 | task_execute_by_index | Execution by index |
| 0x5F34 / 0x6034 / 0x6396 | task_handler_run_by_index / task_handler_init_and_run / task_dispatch_trampoline | Dispatch |
| 0x3588 / 0x35CC / 0x35EE | task_flag_run_A/B/C | Priority flags |
| 0x3610 | interrupt_priority_dispatch | Priority dispatch |
| 0x9668 | osTaskScheduler | Central scheduler |
| 0xA486 | calledLots | Schedule wrapper |
| 0xA12E+ | Task stubs (~30) | App task entry points |
| 0xAC94 / 0xAECC | task_state_mapper / task_scheduler_check_and_sync | State mapping / sync |
| 0xAD5A | engine_startup_initialization | Engine startup |

## 9. RTOS API Layer (0x4BF3C..0x4C4F8, symbol-inferred)

| Address | Symbol | Likely API |
|---------|--------|------------|
| 0x4BF3C | scheduler_init_4BF3C | scheduler_init() |
| 0x4BF78 | scheduler_execute_4BF78 | scheduler_execute() |
| 0x4BFD8 | scheduler_suspend_4BFD8 | scheduler_suspend() |
| 0x4BFFA | scheduler_resume_4BFFA | scheduler_resume() |
| 0x4C2EC | task_create_4C2EC | task_create() |
| 0x4C3C6 | task_delete_4C3C6 | task_delete() |
| 0x4C3EC | task_suspend_4C3EC | task_suspend() |
| 0x4C4A8 | task_resume_4C4A8 | task_resume() |
| 0x4C4CA | task_yield_4C4CA | task_yield() |
| 0x4C4F8 | task_wait_4C4F8 | task_wait() |

Separate code region — possibly a conventional (OSEK/VDX-inspired) RTOS wrapper layer; relationship to native scheduler (0x364–0x9668) needs analysis.

## 10. Verification Status

| Component | Status |
|-----------|--------|
| osTaskScheduler (0x9668) | **Verified** — C lift, 19 unit tests |
| TaskEntry structure | **Verified** — 8B packed, offsets confirmed |
| Task ptr table @0xDB14 | **Confirmed** from ROM |
| Task 0 entries @0xDC64 | **Dumped** — first 5 valid |
| Task 1 entries @0xDBDC | **Dumped** — 12 entries, mixed dispatch |
| Task stubs @0xA12E+ | **Structure confirmed** — 28B pattern + IDs |
| Queue mgmt (0x364–0x3E0) | **Analyzed** — circular, 100 entries |
| Reset handler (0x4E0) | **Analyzed** — cold/warm start |
| task_handler_run_by_index (0x5F34) | **Analyzed** — marker dispatch |
| Context switch (0x3AD8) | **Analyzed** — register save/restore |
| task_execute_by_index (0x3854) | **Analyzed** — counter gating |
| Higher-level API (0x4BF3C+) | **Identified** — needs analysis |

## 11. Open Questions

1. Relationship between native scheduler (0x364–0x9668) and API layer (0x4BF3C+): two layers of same RTOS, or compatibility wrapper?
2. How are task stubs (0xA12E+) invoked — through `task_scheduler_dispatch` (0x364) queue or directly by init?
3. Task descriptor table @0xD9E4 format beyond 8-byte entry size (dispatch-key config data).

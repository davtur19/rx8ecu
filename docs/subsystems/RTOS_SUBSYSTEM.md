# RTOS / Task Scheduling Subsystem — RX-8 PCM (60E1D400)

**Last updated:** 2026-07-31  
**Target:** 60E1D400.bin (SH-2E, big-endian, Renesas SH7055)  
**Scope:** Cooperative multitasking RTOS — queue dispatcher, priority scheduling,
           context switching, initialization.  See also `BOOT_SEQUENCE.md` for
           the full reset → RTOS-start chain.

---

## 1. Architecture Overview

The ECU runs a **cooperative multitasking RTOS** with a circular task queue,
priority-based dispatching, and dependency management.  Tasks run to completion
(yield explicitly) rather than being preempted.  Interrupts operate outside the
scheduler and can post to the task queue.

### 1.1 Key Design Decisions

| Aspect | Implementation |
|--------|---------------|
| **Scheduler type** | Cooperative, non-preemptive, priority-driven with queue |
| **Task queue** | Circular buffer, 100 entries, at fixed RAM addresses |
| **Task table** | ROM-resident pointer table @ 0xDB14, up to 27 tasks + system |
| **Dispatch** | Two paths: direct call (`marker==0xFFFF`) or routed via dispatcher (marker = dispatch key) |
| **Context switching** | Full register save/restore with SR (status register) management |
| **Timing** | ATU timer interrupts drive periodic scheduling |

### 1.2 Memory Map — Key RTOS Addresses

| Address | Purpose |
|---------|---------|
| `0x0000_0000` | Exception vector table (32 entries × 4 bytes) |
| `0x0000_DB14` | Task pointer table in ROM (array of uint32_t pointers) |
| `0x0000_D9E4` | Task descriptor table (8-byte entries, task config data) |
| `0x0000_DBDC` | Task 1 entry array (system scheduling tasks) |
| `0x0000_DC64` | Task 0 entry array (init/system tasks) |
| `0x0000_A12E..A3D0` | Task stub functions (~30 stubs, each 28 bytes) |
| `0xFFFF_72B0` | RTOS control block (in RAM/peripheral space) |
| `0xFFFF_9304` | Task state/priority tracking base (in RAM/peripheral space) |
| `0x0000_0400` | Task queue head pointer |
| `0x0000_0404` | Task queue tail pointer |
| `0x0000_0414` | Task queue entry base |

---

## 2. Exception Vector Table

The SH-2E reset vector and exception table is at `0x0000_0000`.

### 2.1 Initial Vectors

| Vector | Offset | Address | Symbol | Description |
|--------|--------|---------|--------|-------------|
| 0 | 0x0000 | 0x000008B8 | `Manual_Reset` | Initial Program Counter |
| 1 | 0x0004 | 0xFFFFDFA0 | — | Initial Stack Pointer |
| 2 | 0x0008 | 0x000008B8 | `Manual_Reset` | Reserved |
| 4–13 | 0x0010–0x0034 | 0x000008B4 | — | General exception / illegal instruction handler |
| 14–15 | 0x0038–0x003C | 0xFFFFFFFF | — | Unused |

Vectors 4–13 all point to `0x8B4` which appears to be a trampoline for
unhandled exceptions.  Vectors 14+ fall into code/data space and are not
used as exception vectors.

### 2.2 Reset Sequence

```
Vector 0 (0x0000) → 0x000008B8 → Manual_Reset
  │
  ├─ bsr 0x8CC  → bsc_init()          [Bus State Controller init]
  ├─ bsr 0x8F6  → gpio_init()         [GPIO port init]
  ├─ jsr @(0x99C) → resetHandler(0x4E0)[Main reset handler]
  └─ bra 0x8C8  → infinite loop       [Should not reach]
```

---

## 3. Initialization Chain

### 3.1 `resetHandler` (0x4E0)

**Signature:** `int resetHandler(int cold_start, uint8_t reason)`

The main system initialization function, called from `Manual_Reset`:

1. **Watchdog reset** → `bsr 0x572` (resetWatchdog — WDT magic writes)
2. **Hardware init calls:**
   - `jsr @(0x586)` → `hw_init_1` (0x0170) — Clock/PLL/FRT setup
   - `jsr @(0x588)` → `hw_init_2` (0x041C) — Memory controller/BSC
   - `jsr @(0x58A)` → `hw_init_3` (0x03D4) — Additional peripheral init
3. **Cold vs warm start detection:**
   - Compares a magic value (`0x5AA5A55A`) at `*(uint32_t*)0xFFFFDFFC`
   - If mismatch → cold start, check watchdog (0x5B0), set flag
4. **Watchdog recovery (optional):**
   - If `r4 == 0` (cold start) or watchdog timer overflow detected:
     - Calls `checkWatchdogTimer_OVRCOUNT(7)` → checks if WDT overflowed
     - If overflow, retry watchdog reset
   - Reads from `0x7FFFC` / `0x7FFF8` to determine reset cause;
     the chosen reset vector (r13) is `0x6C8` (default serial loop),
     `[0x1000]` = 0x12B4 (app entry), or `[0x7FFF8]` = 0xD49C (main entry)
5. **Finalization:**
   - Stores the magic value `0x5AA5A55A` at `0xFFFFDFFC` (marks valid boot)
   - `jsr @(0x594)` → 0x0040 `vector_trampoline_set_sp`: sets SP = 0xFFFFDFA0,
     then `jmp @r4` (tail-jump to the chosen reset vector in r13).
   - Infinite loop at `0x56E` (end of init)

### 3.2 `hw_init_1` (0x0170)

Initializes clock system: configures PLL, sets FRT (Free-Running Timer),
writes clock divider ratios to SFR registers.

### 3.3 `hw_init_2` (0x041C)

Initializes Bus State Controller (BSC) — memory timings, wait states,
chip-select areas.

### 3.4 `hw_init_3` (0x03D4)

Initializes additional peripherals: interrupt controller, DMA, etc.

### 3.5 `secondary_boot_main` (0xA038)

Second-stage boot that starts the RTOS:

```
secondary_boot_main:
  jsr @(0xA0F0)   → peripheral_init_chain_A (0x4C80)
  jsr @(0xA0F4)   → secondary_peripheral_initializer (0xD7B0)
  bsr 0xA0DC      → sfr_write_a16c: [0xFFFFA16C] = 0
  jsr @(0xA0F8)   → setSR_PARAM (0x2054) — set SR interrupt mask (0xE0)
  jsr @(0xA0FC)   → setRegister_REG_BIT_VAL (0x4BBC) — bit 8 of SFR 0xF74E
  jsr @(0xA100)   → fpu_nop_stub (0x2064)
  jsr @(0xA104)   → sfr_init_dma_channels (0x4CF8)
  jsr @(0xA108)   → task_context_switch (0x3AD8) — start RTOS
  bra 0xA06E      → infinite loop (idle)
```

`task_context_switch` (0x3AD8) validates `task_id < [0x4B00]` (task count = 1),
saves the caller SP to 0xFFFF72D8, loads kernel SR/SP from [0x4B04]/[0x4938],
then **tail-jumps to init_main (0x3E10)** — the RTOS control-block setup below.

### 3.6 `engine_startup_initialization` (0xAD5A)

Performs engine-specific startup: initializes sensor states, fuel/ignition
defaults, and calibration data. Called during the boot sequence before the
main scheduler starts.

---

## 4. RTOS Core — Task Scheduler

### 4.1 Task Data Structures

#### Task Pointer Table @ 0xDB14 (ROM)

Fixed-size table of 32-bit pointers, indexed by `task_id`.  Each pointer
references either a `TaskEntry` array (for system tasks 0–1) or a task stub
function (for application tasks 3–26).

| Index | Pointer | Type | Description |
|-------|---------|------|-------------|
| 0 | `0xDC64` | `TaskEntry[]` | System init/control tasks |
| 1 | `0xDBDC` | `TaskEntry[]` | Scheduling/timer dispatch tasks |
| 2 | `0x06873C` | — | External memory/device handler |
| 3–26 | `0xA12E..0xA3D0` | Stub pointers | Application task stubs |
| 27+ | (end of table) | — | Unused |

#### `TaskEntry` Structure (8 bytes, packed)

```c
struct TaskEntry {
    uint16_t marker;       // +0: 0xFFFF = direct call, else dispatch key ID
    uint16_t arg_count;    // +2: number of uint32_t arguments to copy
    uint32_t func_ptr;     // +4: function address (when marker==0xFFFF) or handler
} __attribute__((packed));
```

- **`marker == 0xFFFF`**: The function at `func_ptr` is called directly.
  The stack frame (with copied args) is passed as the first parameter.
- **`marker != 0xFFFF`**: The dispatcher at `0x5F34` is called with `marker`
  as a dispatch key.  The dispatcher manages queue insertion, priority,
  and dependency resolution.  Returns 0 (done) or 1 (re-queued).

#### Task 0 Entry Table @ 0xDC64 — System Control Tasks

| Entry | Marker | Args | Function | Description |
|-------|--------|------|----------|-------------|
| 0 | 0x0002 | 0 | `0xD9C4` | **No-op** (rts/nop — placeholder task) |
| 1 | **0xFFFF** | 1 | `0x11F68` | Direct-call init step A |
| 2 | **0xFFFF** | 0 | `0x11F5C` | Direct-call init step B |
| 3 | **0xFFFF** | 0 | `0x11F62` | Direct-call init step C |
| 4 | **0xFFFF** | 2 | `0x11F74` | Direct-call init step D |

#### Task 1 Entry Table @ 0xDBDC — Scheduling Dispatch Tasks

| Entry | Marker | Args | Function | Description |
|-------|--------|------|----------|-------------|
| 0 | 0x0000 | 1 | `0x666C` | Dispatch: forward arg + call handler |
| 1 | 0x0001 | 1 | `0x6676` | Dispatch: forward arg + call handler |
| 2 | 0x0002 | 1 | `0x6680` | Dispatch: forward arg + call handler |
| 3 | 0x0003 | 1 | `0x668A` | Dispatch: forward arg + call handler |
| 4 | 0x0002 | 0 | `0x6694` | Dispatch: no-arg variant |
| 5 | 0x0000 | 1 | `0x66A8` | Dispatch: forward arg + call handler |
| 6 | 0x0003 | 0 | `0x66D0` | Dispatch: no-arg variant |
| 7 | 0x0003 | 0 | `0x66D6` | Dispatch: no-arg variant |
| 8 | 0x0000 | 0 | `0x66CA` | Dispatch: no-arg variant |
| 9 | 0x0002 | 1 | `0x11F88` | Dispatch: forward arg + call handler |
| 10 | 0x0003 | 1 | `0x121B8` | Dispatch: forward arg + call handler |
| 11 | **0xFFFF** | 0 | `0x12198` | Direct-call (standalone handler) |

### 4.2 Task Stubs @ 0xA12E–0xA3D0 (Application Tasks)

Each application task is represented by a **stub function** (28 bytes each).
The stubs follow a consistent pattern:

```
sts.l  pr,@-r15        ; Save link register
mov.l  @(disp,PC),r3   ; Load check function addr (0x3854)
jsr    @r3             ; Call task_execute_by_index(task_id)
mov    #TASK_ID, r4    ; [delay slot] Task identifier number
tst    r0, r0          ; Test return value
bt/s   LABEL_EXIT      ; If zero → task not ready, skip dispatch
nop
mov.l  @(disp,PC),r3   ; Load dispatch function addr (0xA486)
mov    #TASK_ID, r4    ; [delay slot] Task ID for dispatch
jmp    @r3             ; Jump to schedule wrapper
lds.l  @r15+, pr       ; [delay slot] Restore PR (tail-call optimization)
LABEL_EXIT:
lds.l  @r15+, pr       ; Restore PR
rts                    ; Return
```

**Known Task IDs (extracted from stubs):**

| Stub Addr | Task ID | Notes |
|-----------|---------|-------|
| 0xA12E | 7 | Application task A |
| 0xA14A | 8 | Application task B |
| 0xA166 | 9 | Application task C |
| 0xA182 | 18 | Application task D |
| 0xA19E | 10 | Application task E |
| 0xA1BA | 11 | Application task F |
| 0xA1D6 | 12 | Application task G |
| 0xA1F2 | 13 | Application task H |
| 0xA20E | 14 | Application task I |
| 0xA22A | 15 | Application task J |
| 0xA246 | 16 | Application task K |
| 0xA262 | 66 | Application task L |
| 0xA27E | 188 | Application task M |
| 0xA29A | 43 | Application task N |
| 0xA2B6 | 1 | Application task O |
| 0xA2D2 | 38 | Application task P |
| 0xA2EE | 9 | Application task Q (duplicate ID?) |
| 0xA30A | 46 | Application task R |
| 0xA326 | 252 | Application task S |
| 0xA342 | 66 | Application task T (duplicate ID?) |
| 0xA35E | 1 | Application task U (duplicate ID?) |
| 0xA37A | 38 | Application task V (duplicate ID?) |
| 0xA396 | 9 | Application task W (duplicate ID?) |
| 0xA3B2 | 0 | Application task X (special ID 0) |
| 0xA3CE | 37 | Application task Y |
| 0xA3EA | 66 | Application task Z (duplicate ID?) |

*Note: Identical task IDs across different stubs may indicate shared
scheduling priority groups or multiple entry points for the same logical task.*

The stubs reference two key functions via PC-relative constant pool:
1. **`task_execute_by_index`** (0x3854) — checks if the task should execute
2. **`task_dispatch_trampoline`** (0xA486, aka `calledLots`) — dispatches
   the task through the scheduler

### 4.3 `osTaskScheduler` (0x9668) — Central Dispatch

**The core RTOS dispatch function.**  Given a `task_id`, `entry_idx`, and
optional argument array, it selects the appropriate task entry, copies
arguments onto a stack frame, and either calls the function directly or
passes control to the priority dispatcher.

Detailed analysis in `docs/functions/osTaskScheduler.md` and C lift in
`c/osTaskScheduler.c`.

**Constants loaded at runtime:**

| Constant Address | Value | Purpose |
|-----------------|-------|---------|
| `*(uint32_t*)0x9780` | `0x0000DB14` | Task pointer table base |
| `*(uint32_t*)0x9784` | `0x0000FFFF` | Direct-call marker sentinel |
| `*(uint32_t*)0x9788` | `0x00005F34` | Priority dispatcher address |

### 4.4 `task_handler_run_by_index` (0x5F34) — Priority Dispatcher

**`int task_handler_run_by_index(uint16_t marker_id, uint32_t *frame)`**

The dispatcher called from `osTaskScheduler` when `marker != 0xFFFF`.
Manages task queue states, priority levels, and execution counts.

**Flow:**
1. Looks up the marker ID in the **task descriptor table** `@0xD9E4`
   (8-byte entries containing config data for each dispatch key)
2. Calls `getSR()` (0x3920) to get current status register
3. Checks task state from task control block at `0xFFFF9304 + marker*3`
4. If task queue is empty → calls `task_execute_by_index` (0x3854) to run
5. If task is pending → calls `schedule_wrapper` (0xA486) to re-queue
6. Copies arguments from frame to task descriptor
7. Updates task execution counters
8. Calls `setSR()` (0x3934) to restore status register

**Return values:**
- `0` — Normal completion
- `1` — Task was re-queued (caller should reschedule)
- `2` — Task queue full / skipped
- `3` — Task initialization skipped (counter not ready)

### 4.5 `task_handler_init_and_run` (0x6034) — Init + Dispatch

**`int task_handler_init_and_run(uint16_t task_id, uint32_t *frame)`**

Similar to `task_handler_run_by_index` but includes initialization steps.
Used for one-shot startup tasks and initialization sequences.

### 4.6 `task_execute_by_index` (0x3854) — Task State Check

**`int task_execute_by_index(uint8_t task_id)`**

Called by task stubs to determine if the task should execute:
1. Reads the RTOS control block (at `0xFFFF72B0`)
2. Checks the task's dependency counter
3. If counter > 0, decrements and returns non-zero (task is ready)
4. May trigger context switch if interrupts are pending
5. Returns status code for the stub to act on:
   - Result `0` → Task is not ready, skip
   - Result non-zero → Task is ready, call the dispatch wrapper

### 4.7 Circular Task Queue

The scheduler uses a **100-entry circular queue** for pending tasks.

| Address | Size | Description |
|---------|------|-------------|
| `0x0400` | uint16_t | Queue head pointer (write index) |
| `0x0404` | uint16_t | Queue tail pointer (read index) |
| `0x0414` | 100×8 bytes | Queue entry array |

**Key functions:**

- **`task_scheduler_dispatch`** (0x364): Reads head pointer, dispatches
  the next task from the queue.  Increments a counter that wraps at 100.
  Calls dispatch functions based on task flags.

- **`task_queue_get_next`** (0x3B0): Returns the next task entry from
  the queue (increments tail pointer, wraps at 100).

- **`task_queue_pending_count`** (0x3E0): Returns `(head - tail) % 100`
  — the number of tasks pending in the queue.

### 4.8 Context Switching

#### `task_context_save_enter` (0x3238)

Saves the current task's context (registers r2–r7) to the stack,
increments the RTOS context counter.  Called when entering an ISR or
context switch point.

#### `task_context_switch` (0x3AD8)

Performs a full context switch between tasks:
1. Validates the target task priority
2. Saves current SR and PR
3. Saves current stack pointer to task control block
4. Loads new task's stack pointer
5. Restores new task's SR
6. Jumps to new task's execution point

#### `task_full_context_save` (0x3BF4)

Full register context save used during idle → task transitions.
Saves all callee-saved registers and updates the RTOS control block.

### 4.9 Task State Management

#### `task_flag_run_A/B/C` (0x3588 / 0x35CC / 0x35EE)

Three flag-set functions that manage interrupt/task flags:

- **A** (0x3588): Sets and clears flag bit for priority level A
- **B** (0x35CC): Sets and clears flag bit for priority level B  
- **C** (0x35EE): Sets and clears flag bit for priority level C

Each function:
1. ORs a flag bit into the RTOS control block
2. Calls a registered handler function
3. Clears the flag bit with AND-NOT

These are used by interrupt handlers to trigger task-level processing.

#### `task_ready_check` (0x3FB0)

Checks if a specific task is ready to run:
1. Validates the task index against the max count
2. Looks up the task's ready flag in a bitmask table
3. Returns `0` (ready) or `3` (not ready)

#### `task_state_mapper` (0xAC94)

Maps ECU state (ignition on, engine running, etc.) to a task state code.
Used to enable/disable task groups based on operating mode.

### 4.10 Initialization Functions

#### `task_queue_init` (0x3964)

Initializes the circular task queue:
1. Reads the CPU version/stepping from a register
2. Clears the task queue entries
3. Sets up the pointer arrays for task dispatch
4. Initializes all queue slots to `-1` (empty)

#### `task_table_scan_init` (0x3EC0)

Scans the task table and initializes each task's control block:
1. Iterates through all configured tasks
2. For each task, sets initial state (inactive) with default counter values
3. Calls a per-task init function to set initial parameters

#### `task_dependency_handler` (0x3F10)

Manages task dependency chains:
1. Reads a task's dependency list
2. Decrements dependency counters for dependent tasks
3. When all dependencies are satisfied, enables the dependent task
4. Uses the task descriptor table to resolve dependency relationships

#### RTOS Init Function (0x3E10)

The main RTOS initialization entry point, reached during boot via
`secondary_boot_main (0xA038) → task_context_switch (0x3AD8) → jmp 0x3E10`
(see `docs/subsystems/BOOT_SEQUENCE.md`, §7–8).  Mode byte r4 = 0 (cold start).

```
RTOS_Init(mode):
  ┌─ Set up RTOS control block (at 0xFFFF72B0)
  ├─ Store mode byte
  ├─ Read RAM start address from pointer table
  ├─ Read task descriptor table pointer
  ├─ Call task_queue_init()          [0x3964]
  ├─ Call task_table_scan_init()     [0x3EC0]
  ├─ Call task_dependency_handler()  [0x3F10]
  ├─ Call task_set_current_ptr()     [0x3AC0]
  ├─ Call nullsubs (placeholder hooks) [0x3F8C, 0x3F88]
  ├─ Call clear_task_flag_dc/dd()    [0x3F90, 0x3F9C]
  ├─ If a RAM flag is set:
  │    └─ Call task_flag_run_A()    [0x3588]
  ├─ Call nullsub_3()               [0x3FA8]
  └─ Jump to task_full_context_save() [0x3C2A]
```

### 4.11 Schedule Wrapper (0xA486, aka `calledLots`)

```
calledLots(task_id):
  ├─ Save SR (set interrupt priority)
  ├─ Save task_id on stack
  ├─ Call setSR_PARAM(0x2054)  [set status register with priority mask]
  ├─ Read task counter from *(uint8_t*)(0xFFFFA18B + task_id)
  ├─ If counter < 0xFF, increment counter
  ├─ Call setSR(0x2064) [restore status register]
  └─ Return
```

This function is called from task stubs when the task is ready to run.
It manages per-task execution counters and sets interrupt priority.

---

## 5. Task Dispatch Flow (Complete)

```
                   ┌──────────────────────┐
                   │  Interrupt / Timer    │
                   │  fires, posts to      │
                   │  task queue           │
                   └──────┬───────────────┘
                          │
                          ▼
              ┌─────────────────────────┐
              │ task_scheduler_dispatch │
              │ (0x364): Read queue,    │
              │  dispatch next task     │
              └──────┬─────────────────┘
                     │
          ┌──────────┴──────────┐
          ▼                     ▼
   ┌──────────────┐   ┌──────────────────┐
   │ System Tasks │   │ Application Tasks│
   │ (ID 0-1)     │   │ (ID 3-26)        │
   │              │   │                  │
   │ osTaskSched- │   │ Task stub called │
   │ uler (0x9668)│   │ (0xA12E+)        │
   │ reads Task-  │   │ calls 0x3854     │
   │ Entry array  │   │ (task_execute_   │
   │ @ 0xDC64 /   │   │ by_index)        │
   │ 0xDBDC       │   │ │                │
   └──────┬───────┘   └──┬───────────────┘
          │              │
          │              ▼
          │   ┌─────────────────────┐
          │   │ task_execute_by_idx │
          │   │ (0x3854): Check if  │
          │   │ task can run; if    │
          │   │ ready, call dispatch│
          │   │ wrapper (0xA486)    │
          │   └──────┬──────────────┘
          │          │
          ▼          ▼
   ┌────────────────────────────┐
   │ calledLots (0xA486)        │
   │ Increment task counter,    │
   │ manage SR priority         │
   │ Calls setSR/setSR_PARAM    │
   └──────┬─────────────────────┘
          │
          ▼
   ┌────────────────────────────┐
   │ osTaskScheduler (0x9668)   │
   │ or task_handler_run_by_idx │
   │ (0x5F34)                  │
   │                            │
   │ marker==0xFFFF?            │
   │  ├─ Yes: call func directly│
   │  └─ No:  dispatcher @5F34 │
   │           queue mgmt       │
   │           arg copy         │
   │           exec counters    │
   └────────────────────────────┘
```

---

## 6. Interrupt Handling

### 6.1 `interrupt_priority_dispatch` (0x3610)

Priority-based interrupt dispatch function. Determines the IPL (Interrupt
Priority Level) for a given interrupt request:

1. Masks the interrupt request against the current SR
2. Tests individual flag bits from the RTOS control block
3. Maps each flag to a priority level (5, 6, 7, 8, 3, 0)
4. Returns the appropriate handler index

### 6.2 Serial & ATU Interrupts

- **`serial_rx_handler_ch0/1/2`** @ 0x004C, 0x0064, 0x00C0 — SCI receive
  interrupt handlers
- **`atu_timer_init`** @ 0x10AC — ATU timer and interrupt init
- **`atu_capture_compare_init`** @ 0x4F08 — ATU input capture/compare init
- **`intc_clear_flag_ec26/trampoline`** @ 0x5286/0x528E — Interrupt
  controller flag clearing

---

## 7. RTOS Constants Summary

| Address | Value | Description |
|---------|-------|-------------|
| `0x9780` | `0x0000DB14` | Task pointer table base address |
| `0x9784` | `0x0000FFFF` | Direct-call marker sentinel |
| `0x9788` | `0x00005F34` | Priority dispatcher function |
| `0x978C` | `0xFFFF9304` | Task control block base (RAM SFR area) |
| `0x9790` | `0xFFFFA118` | Task flag table (RAM SFR area) |
| `0x9794` | `0x00002054` | `setSR_PARAM` — set SR with priority |
| `0x9798` | `0x00006034` | `task_handler_init_and_run` |
| `0x979C` | `0x00002064` | `setSR` — restore SR from arg |
| `0xA3C4` | `0x00003854` | `task_execute_by_index` |
| `0xA3C8` | `0x0000A486` | Schedule wrapper (`calledLots`) |
| `0xA3CC` | `0x00009668` | `osTaskScheduler` |
| `0xFFFF72B0` | — | RTOS control block structure |
| `0xFFFF9304` | — | Task state/priority tracking |
| `0xFFFFA18B` | — | Per-task execution counter table |

---

## 8. Key Functions Reference

| Address | Name | Role |
|---------|------|------|
| `0x08B8` | `Manual_Reset` | Reset vector entry point |
| `0x04E0` | `resetHandler?` | Main init/reset handler |
| `0x0170` | `hw_init_1` | Clock/PLL init |
| `0x041C` | `hw_init_2` | BSC/memory controller init |
| `0x03D4` | `hw_init_3` | Peripheral init |
| `0x08CC` | `bsc_init` | Bus State Controller init |
| `0x08F6` | `gpio_init` | GPIO port initialization |
| `0x0A038` | `secondary_boot_main` | Second-stage boot + RTOS start |
| `0x0A0CE` | `whileLoop` | Idle loop (disables interrupts, loops) |
| `0x0D97C` | `fpu_context_save_restore` | FPU context save/restore |
| `0x364` | `task_scheduler_dispatch` | Queue-based dispatch |
| `0x3B0` | `task_queue_get_next` | Get next from circular queue |
| `0x3E0` | `task_queue_pending_count` | Count pending tasks |
| `0x3964` | `task_queue_init` | Initialize task queue |
| `0x3EC0` | `task_table_scan_init` | Scan and init task table |
| `0x3F10` | `task_dependency_handler` | Dependency resolution |
| `0x3AC0` | `task_set_current_ptr` | Set current task pointer |
| `0x3AD8` | `task_context_switch` | Full context switch |
| `0x3238` | `task_context_save_enter` | Context save on ISR entry |
| `0x3BF4` | `task_full_context_save` | Full register save |
| `0x3D58` | `taskEndRoutine?` | Task termination handler |
| `0x3FB0` | `task_ready_check` | Check if task is ready |
| `0x3854` | `task_execute_by_index` | Task execution by index |
| `0x5F34` | `task_handler_run_by_index` | Priority dispatcher |
| `0x6034` | `task_handler_init_and_run` | Init + run handler |
| `0x6396` | `task_dispatch_trampoline` | Dispatch trampoline |
| `0x3588` | `task_flag_run_A` | Set/clear priority flag A |
| `0x35CC` | `task_flag_run_B` | Set/clear priority flag B |
| `0x35EE` | `task_flag_run_C` | Set/clear priority flag C |
| `0x3610` | `interrupt_priority_dispatch` | Interrupt priority dispatch |
| `0x9668` | `osTaskScheduler` | Central scheduler dispatch |
| `0xA486` | `calledLots` | Schedule wrapper |
| `0xA12E+` | Task stubs (~30 total) | Application task entry points |
| `0xAC94` | `task_state_mapper` | State → task mapping |
| `0xAECC` | `task_scheduler_check_and_sync` | Scheduler sync/check |
| `0xAD5A` | `engine_startup_initialization` | Engine-specific startup |

---

## 9. RTOS API Summary (from symbol-based inference)

The following function families were identified from symbol analysis and may
constitute a higher-level RTOS API layer (addresses in 0x4BF3C..0x4C4F8
range):

| Address | Symbol | Likely API |
|---------|--------|------------|
| `0x4BF3C` | `scheduler_init_4BF3C` | `scheduler_init()` |
| `0x4BF78` | `scheduler_execute_4BF78` | `scheduler_execute()` |
| `0x4BFD8` | `scheduler_suspend_4BFD8` | `scheduler_suspend()` |
| `0x4BFFA` | `scheduler_resume_4BFFA` | `scheduler_resume()` |
| `0x4C2EC` | `task_create_4C2EC` | `task_create()` |
| `0x4C3C6` | `task_delete_4C3C6` | `task_delete()` |
| `0x4C3EC` | `task_suspend_4C3EC` | `task_suspend()` |
| `0x4C4A8` | `task_resume_4C4A8` | `task_resume()` |
| `0x4C4CA` | `task_yield_4C4CA` | `task_yield()` |
| `0x4C4F8` | `task_wait_4C4F8` | `task_wait()` |

These are located in a separate code region and may be part of a
conventional RTOS wrapper layer (possibly OSEK/VDX-inspired).
Their exact relationship to the native scheduler at 0x364–0x9668
requires further analysis.

---

## 10. Verification Status

| Component | Status |
|-----------|--------|
| `osTaskScheduler` (0x9668) | **Verified** — C lift tested with 19 unit tests |
| `TaskEntry` structure | **Verified** — 8-byte packed, offsets confirmed from ROM |
| Task pointer table @ 0xDB14 | **Confirmed** from ROM binary |
| Task 0 entry table @ 0xDC64 | **Dumped** — first 5 entries valid |
| Task 1 entry table @ 0xDBDC | **Dumped** — 12 entries, mixed dispatch types |
| Task stubs @ 0xA12E+ | **Structure confirmed** — 28-byte pattern with task IDs |
| Queue management (0x364–0x3E0) | **Analyzed** — circular queue, 100 entries |
| Reset handler (0x4E0) | **Analyzed** — cold/warm start detection |
| `task_handler_run_by_index` (0x5F34) | **Analyzed** — marker-based dispatch |
| Context switch (0x3AD8) | **Analyzed** — register save/restore |
| `task_execute_by_index` (0x3854) | **Analyzed** — counter-based task gating |
| Higher-level API (0x4BF3C+) | **Identified** — further analysis needed |

---

## 11. Open Questions

1. **What is the exact relationship between the native scheduler
   (0x364–0x9668) and the higher-level API at 0x4BF3C+?** Are they
   two layers of the same RTOS, or is one a compatibility wrapper?

2. **How are task stubs at 0xA12E+ called?** Do they go through the
   `task_scheduler_dispatch` (0x364) queue, or are they invoked directly
   by the init sequence?

3. **What is the task descriptor table at 0xD9E4?** It appears to contain
   configuration data for dispatch keys (marker IDs), but the exact format
   is not yet decoded beyond the 8-byte entry size.

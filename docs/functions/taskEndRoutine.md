# taskEndRoutine @ 0x3D58

_source: AI (Haiku) draft, unverified_

**Purpose:** RTOS task finalizer. Marks task completion, updates counters, and performs consistency checks before task dequeue.

**Inputs:**
- r13: pointer to task control block (TCB) or task state structure
- r14: pointer to system state/frame buffer

**Outputs / side effects:**
- Updates TCB counter at +3 (increment by 1)
- Writes 0x0100 to system state at +8
- Calls consistency check function
- Clears TCB byte at +0
- Jumps to next task handler function (via r2 @ 0x00003C2A)

**Calls:**
- getSR equivalent @ 0x3920: read interrupt status register (implicit context save)
- FUN_000035ee @ 0x35EE: cleanup/validation function (called conditionally if flag @ 0x00004B10 is set)
- consistencyCheck @ 0x3A28: verify integrity with r4=state, r5=TCB+1
- FUN_00003c2a @ 0x3C2A: next task handler (jmp, not call — tail transfer)

**Behavior:**
1. Save pr to stack
2. Load system state pointer from 0xFFFF7638 (global)
3. Load interrupt SR from state+16, restore it via ldc
4. Check if flag @ 0x00004B10 is non-zero
5. If flag set: call FUN_000035ee with r4=0 (cleanup)
6. Increment TCB+3 byte (task counter/completion count)
7. Write 0x0100 to system state+8 (status flag)
8. Load TCB+1 and call consistencyCheck(state @ r14, tcb+1 @ r5)
9. Clear TCB+0 (mark task slot free)
10. Load and store TCB+4 to system state+12 (task context/return address?)
11. Jump to FUN_00003c2a (next task scheduler)

**Draft C:**
```c
typedef struct {
  u8 state;         // +0: task state (0=free)
  u8 flags;         // +1: task flags
  u8 reserved;      // +2
  u8 counter;       // +3: completion counter
  u32 context;      // +4: saved context/return addr
} TaskControlBlock;

typedef struct {
  u32 reserved[4];  // +0-15
  u32 sr_saved;     // +16: saved SR
  u32 reserved2[1]; // +20
  u32 status;       // +24: task status (write 0x0100)
  u32 task_return;  // +28: task return address
} SystemState;

void taskEndRoutine(TaskControlBlock *tcb) {
  SystemState *sys = (SystemState *)0xFFFF7638;
  
  u32 saved_sr = sys->sr_saved;
  ldc(saved_sr);  // Restore SR
  
  if (*(u32*)0x00004B10 != 0) {
    cleanup(0);
  }
  
  tcb->counter++;
  sys->status = 0x0100;
  consistency_check(sys, tcb->flags);
  tcb->state = 0;
  sys->task_return = tcb->context;
  
  next_task_handler();  // jmp (no return)
}
```

**Confidence:** med
- Task control block structure partially inferred
- System state pointer and offsets educated guesses
- The 0x0100 write purpose unclear (status flag? interrupt level?)
- Tail jump to next handler confirmed from jmp instruction

**Uncertainties:**
- What is the significance of 0x0100 written to system state+8?
- Is the flag at 0x00004B10 a global task-enabled flag or per-task?
- What does FUN_000035ee do when called with r4=0?
- What is task context stored at TCB+4 used for?

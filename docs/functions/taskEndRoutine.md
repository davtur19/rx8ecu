# taskEndRoutine @ 0x3D58
**Purpose:** RTOS task finalizer. Mark the task as complete. Update the counters. Perform consistency checks before the task dequeue.
**Inputs:** r13: pointer to the task control block (TCB) or task state structure ; r14: pointer to the system state/frame buffer
**Out:** Updates the TCB counter at +3 (increment by 1) ; Writes 0x0100 to the system state at +8 ; Calls the consistency check function ; Clears the TCB byte at +0 ; Jumps to the next task handler function (with r2 @ 0x00003C2A)
**Calls:** getSR equivalent @ 0x3920: read the interrupt status register (implicit context save) ; FUN_000035ee @ 0x35EE: cleanup/validation function (called conditionally if flag @ 0x00004B10 is set) ; consistencyCheck @ 0x3A28: verify integrity with r4=state, r5=TCB+1 ; FUN_00003c2a @ 0x3C2A: next task handler (jmp, not call — tail transfer)
Save pr to the stack ; Load the system state pointer from 0xFFFF7638 (global) ; Load the interrupt SR from state+16, restore it with ldc ; Check if flag @ 0x00004B10 is non-zero ; If the flag is set: call FUN_000035ee
with r4=0 (cleanup) ; Increment the TCB+3 byte (task counter/completion count) ; Write 0x0100 to system state+8 (status flag) ; Load TCB+1 and call consistencyCheck(state @ r14, tcb+1 @ r5) ; Clear TCB+0
(mark the task slot free) ; Load and store TCB+4 to system state+12 (task context/return address?) ; Jump to FUN_00003c2a (next task scheduler)
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
**Status:** med — the TCB structure is partially inferred; the state pointer/offsets are educated guesses; the 0x0100 write purpose is unclear; the tail jump to the next handler is confirmed (jmp).
**Uncertainties:** Meaning of 0x0100 at system state+8? Is flag @0x4B10 global or per-task? What does FUN_000035ee(r4=0) do? Task context at TCB+4?

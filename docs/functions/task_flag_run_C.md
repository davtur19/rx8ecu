# task_flag_run_C @ 0x35EE

**Track-A verification:** emulator (bit set/clear tests)

## Overview

Sets or clears bit 15 of the OS running-flag word at 0xFFFF72B8.
Called by the task scheduler to mark that the RTOS (or a specific
task context) is active (`nullsub` variant) or inactive (this variant).

The three functions `task_flag_run_A` (0x3588), `task_flag_run_B` (0x35CC),
and `task_flag_run_C` (0x35EE) form a set — each sets/clears a different
bit in the same 32-bit register to indicate which of three scheduler
entry points is currently active.

## Logic

```c
void task_flag_run_C(uint32_t flag_bit) {
    volatile uint32_t *reg = (volatile uint32_t*)0xFFFF72B8;
    uint32_t bit15 = 0x8000;
    if (flag_bit & bit15)
        *reg |= bit15;
    else
        *reg &= ~bit15;
}
```

## Verification

- [x] Disassembly confirmed against capstone + Ghidra
- [x] C code written (`c/task_flag_run_C.c`)
- [x] Emulator test: `test_task_flag_run_C.py` — set/clear bit 15 via nullsub call, all pass

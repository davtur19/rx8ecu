# consistencyCheck @ 0x3A28

**Track-A verification:** C code written, emulator test pending

## Overview

This is a task consistency / health-check counter table. The scheduler calls this on every task
switch to verify each task's "I'm alive" counter against its expected value. On
mismatch the counter is incremented (or restored from a saved shadow). If it drifts
too far, an exception handler fires.

Each entry in the table (indexed by task_id × 8) has:
- A 16-bit counter value (at `counter_ptr[0]`)
- A 16-bit expected value (at `counter_ptr[1]`)

## Logic

```c
int32_t consistencyCheck(struct TaskConsistencyCtx *ctx, int8_t task_id) {
    int32_t idx = task_id;
    struct ConsEntry *entry = base + idx * 8;
    volatile int16_t *counter = entry->counter_ptr;
    int16_t cur = *counter;
    int16_t expected = *(counter + 1);

    if (cur == expected) {
        // healthy: reset to -1, clear bitmap bit
        *counter = -1;
        bitmap[idx >> 3] &= mask[idx & 7];
        if (task_id == ctx->current_task)
            return 1;   // calls exception handler
        return 0;
    }

    // mismatch: restore shadow or increment
    if (cur == entry->shadow_expected)
        *counter = entry->shadow_save;
    else
        *counter = cur + 1;

    if (task_id == ctx->current_task) {
        ctx->diag_field = diag_table[*counter];
        return 1;
    }
    return 0;
}
```

### Memory Map

| Address   | Content                                      |
|-----------|----------------------------------------------|
| ctx+0     | `current_task` (int8)                        |
| ctx+6     | `diag_field` (int16)                         |
| ctx+0x20  | `table_base` — pointer to entry array        |
| entry+0   | `save_value` (uint16)                        |
| entry+2   | `expected_shadow` (uint16)                   |
| entry+4   | `counter_ptr` — pointer to counter+expected  |
| 0xFFFF72E0 | Bitmap of seen tasks (8-bit stride)         |
| 0xFFFF7234 | Diagnostic lookup table base                |

## Verification

- [x] Disassembly confirmed against capstone + Ghidra
- [x] C code written (`c/consistencyCheck.c`) — full C implementation with struct definitions
- [ ] Emulator test pending (needs RAM structure setup with task context + counter table at ROM pool addresses)

# osTaskScheduler @ 0x9668

**Last updated:** 2026-07-30 (verified against 60E1D400.bin)

**Source:** Ghidra disassembly, hand-traced — C lift in `c/osTaskScheduler.c`

---

## Summary
RTOS task-scheduler entry point. Given a `task_id`, an `entry_idx` into that
task's table, and an optional argument array, it either calls the target
function directly or routes through a dispatcher.  Returns 0 (normal) or 1
(reschedule requested).

---

## Signature
```c
int osTaskScheduler(uint8_t  task_id,    // r4
                    uint16_t entry_idx,  // r5
                    const uint32_t *args); // r6
```

- **Length:** 110 bytes (0x9668 – 0x96D6)
- **Callers:** stubs at 0xA12E–0xA288 (indirectly through 0x3854 → 0xA486)

---

## Data Constants (loaded from ROM)

| Address | Value | Purpose |
|---------|-------|---------|
| 0x9780  | `0x0000DB14` | Pointer to task table in RAM |
| 0x9784  | `0xFFFF`     | **DIRECT_CALL_MARKER** |
| 0x9788  | `0x00005F34` | Address of dispatcher function |

---

## TaskEntry Structure (8 bytes, packed)
```c
struct TaskEntry {
    uint16_t marker;      // +0: 0xFFFF = direct call, else dispatch key
    uint16_t arg_count;   // +2: number of uint32_t arguments
    uint32_t func_ptr;    // +4: function address (when marker == 0xFFFF)
} __attribute__((packed));
```

---

## Control Flow

1. **Load task table pointer** from `*(uint32_t*)0x9780` → 0xDB14.
2. **Index** by `task_id * 4` → pointer to a `TaskEntry` array.
3. **Advance** by `entry_idx * 8` bytes (each entry is 8 bytes).
4. **Read** `marker`, `arg_count`, `func_ptr` from the selected entry.
5. **Allocate 8-word frame** on stack (`frame[0] = func_ptr`).
6. **Copy** `arg_count` words from `args[]` into `frame[1..arg_count]`.
7. **Branch:**
   - **If `marker == 0xFFFF`:** call `func_ptr(&frame[1])`, return 0.
   - **Else:** call dispatcher@0x5F34(marker, frame); if it returns non-zero,
     return 1 (reschedule), else 0.

---

## C Implementation
See `c/osTaskScheduler.c` (full C lift with SH-2E asm header).

---

## Structural Tests
`c/tests/test_osTaskScheduler.c` — 19 tests covering:
- TaskEntry layout (sizeof, field offsets via memcpy)
- Direct-call path (marker == 0xFFFF)
- Dispatcher path (marker != 0xFFFF, return value passthrough)
- Argument copy loop (correct values, bounds, arg_count=0 edge case)

All 19 tests pass on x86-64 host.

---

## Key Differences from Old (AI-Draft) Analysis

| Old (0x9630 draft) | Verified (0x9668) |
|---|---|
| `r5` = task operation code, scaled by 10 | `r5` = entry index, scaled by 8 |
| Queue base from 0xD87C | Task table pointer from `*(uint32_t*)0x9780` → 0xDB14 |
| Unclear validation function at 0x5F1C | Identified dispatcher at 0x5F34 with marker-based dispatch |
| Structure guessed as 10+ byte entries | Confirmed 8-byte `TaskEntry` |

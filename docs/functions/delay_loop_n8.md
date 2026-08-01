# delay_loop_n8 (0x239C)

**Status: Track A — verified** (emulated ROM, 1000 random inputs + edge cases)

**Former names:** `mul16_unsigned` (Ghidra/IDA — **incorrect**, see below)

## Purpose

Simple busy-wait timing delay: idles for `n × 8` iterations.  The trip count is
`param_1 * 8` (the argument is multiplied by 8 via `shll2; shll`).  Used as a
small-integer µ-delay dispatched through function-pointer tables.

## Why "mul16_unsigned" is wrong

The `shll2; shll` sequence multiplied `r4` by 8, and the caller typically
zero-extends the argument (`extu.w r4,r4`).  An automated tool (IDA/Ghidra)
likely matched the pattern and guessed "16-bit unsigned multiply", but the
function has no `mulu.w`, `mulu.l`, `dmuls.l`, or any multiply instruction.
The only operation is a counter loop — a classic embedded busy-wait.

## Calling Convention

| Register | Direction | Meaning                |
|----------|-----------|------------------------|
| r4       | in        | Loop count multiplier  |
| (none)   | out       | No meaningful return   |

## Implementation

10 instructions, 20 bytes:
```
0x239C:  mov     #0x00,r5     ; r5 = 0
0x239E:  shll2   r4           ; r4 <<= 2
0x23A0:  shll    r4           ; r4 <<= 1  (total ×8)
0x23A2:  cmp/hs  r4,r5        ; T = (r5 >= r4)
0x23A4:  bt      0x23AC       ; skip if r5 >= r4
0x23A6:  add     #0x01,r5     ; r5++
0x23A8:  cmp/hs  r4,r5        ; T = (r5 >= r4)
0x23AA:  bf      0x23A6       ; loop back if r5 < r4
0x23AC:  rts
0x23AE:  nop
```

## C Equivalent

```c
void delay_loop_n8(uint16_t n)
{
    uint32_t count = (uint32_t)n * 8u;
    uint32_t i = 0;
    while (i < count) {
        i++;
    }
}
```

## Related

- `delay?` (0x59808) — mode-select wrapper around the delay mechanism

# checksum_complement_add (0x2034)

**Status: Track A — verified** (emulated ROM, 100000 random inputs + edge cases)

## Purpose

This function validates the integrity of a 32-bit redundant-storage cell. The cell contains a
(value, ~value) pair.  It returns the checksum residual:
```
result = (~value - (value >> 16)) & 0xFFFF
```
A valid pair — where `value == (data << 16) | (~data & 0xFFFF)` — yields
`result == 0`.  Any non-zero result indicates data corruption.

## Calling Convention

| Register | Direction | Meaning                     |
|----------|-----------|-----------------------------|
| r4       | in        | Pointer to 32-bit cell      |
| r0       | out       | Checksum residual (uint16)  |

## Implementation

7 instructions, 14 bytes:
```
0x2034:  mov.l   @r4,r3       ; r3 = *r4
0x2036:  mov     r3,r0        ; r0 = r3
0x2038:  shlr16  r3           ; r3 >>= 16
0x203A:  not     r0,r0        ; r0 = ~r0
0x203C:  sub     r3,r0        ; r0 -= r3
0x203E:  rts
0x2040:  extu.w  r0,r0        ; (delay) r0 &= 0xFFFF
```

## C Equivalent

```c
uint16_t checksum_complement_add(uint32_t value)
{
    return (uint16_t)((~value - (value >> 16)) & 0xFFFFu);
}
```

## Related

- `encode()` (0x2420) — packs uint8_t as (val << 8) | ~val  (16-bit cell)
- `complement_shift_u16` (0x2430) — packs uint16_t as (val << 16) | ~val (32-bit cell)
- mem_accessors.c redundant-cell family (0x3E0DC, 0x3E11C, …)

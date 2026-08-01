# faultEnableStatus2 @ 0x5E2BC

_source: AI (Haiku) draft, unverified_

**Purpose:** Check if a specific fault enable status flag is set for a given fault condition.

**Inputs:**
- r4: Index into fault enable status table (0–N)
- r5: Bit mask to check against the retrieved byte

**Outputs:**
- r0: Boolean result (1 if bits in r5 are set in the retrieved value, 0 otherwise)

**Calls:**
- None

**Behavior:**

1. Load table address 0x0007CB14 into r0
2. Zero-extend r5 to 8 bits (ensure upper bits clear)
3. Zero-extend r4 to 16 bits
4. Load byte from table at offset r4: `byte_value = ram[0x0007CB14 + r4]`
5. Zero-extend loaded byte to 16 bits
6. Perform bitwise AND: `result = byte_value & r5`
7. Test result (tst r5, r3): Sets T flag if result != 0
8. Copy T flag to r4 via movt (T → r4)
9. Move r4 to r0 as return value

**Draft C:**

```c
uint8_t faultEnableStatus2(uint8_t fault_index, uint8_t bit_mask) {
    uint8_t *table = (uint8_t *)0x0007CB14;
    uint8_t value = table[fault_index];
    return (value & bit_mask) ? 1 : 0;
}
```

**Confidence:** high
- Clear straightforward bit-check operation
- Table location and indexing unambiguous
- Uncertainties: semantic meaning of individual bits in the fault enable status byte

# updateMemoryAtAddress_16bit_ADDR_VAL @ 0x3E208

_source: AI (Haiku) draft, unverified_

**Purpose:** Write a 16-bit value to RAM along with its complement checksum (mirror of 8-bit version for 16-bit data).

**Inputs:**
- `r4`: target address in RAM
- `r5`: value to write (16-bit)

**Outputs / side effects:**
- Writes value at [r4], complement checksum at [r4+2]
- Returns r0 = 0 (success code)

**Calls:** (none)

**Behavior:**

1. Zero-extend r5 (value) → r3
2. Shift r3 left by 16 bits: r3 = r3 << 16  (places value in high word)
3. Compute NOT of r5 (value) → r2, zero-extend → r2  (complement)
4. Add r2 to r3: r3 = r3 + r2  (combine value in high word + complement in low word)
5. Write 32-bit result to [r4]: mov.l r3, @r4
6. Return r0 = 0

**Draft C:**

```c
int updateMemoryAtAddress_16bit_ADDR_VAL(uint16_t *addr, uint16_t value)
{
    uint32_t data = ((uint32_t)value << 16) | ((~value) & 0xFFFF);
    *(uint32_t*)addr = data;
    return 0;
}
```

Or more explicitly:

```c
int updateMemoryAtAddress_16bit_ADDR_VAL(uint16_t *addr, uint16_t value)
{
    addr[0] = value;
    addr[1] = (~value) & 0xFFFF;
    return 0;
}
```

**Confidence:** high (mirrors 8-bit structure exactly; confirms checksum encoding pattern)

**Uncertainties:**
- Same as 8-bit: no interrupt masking in this function (caller responsibility?)
- Whether return value is ever checked

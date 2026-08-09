# updateMemoryAtAddress_16bit_ADDR_VAL @ 0x3E208
**Purpose:** Write a 16-bit value to RAM together with its complement checksum (mirror of the 8-bit version for 16-bit data).
**Inputs:** `r4`: target address in RAM ; `r5`: value to write (16-bit)
**Out:** Writes the value at [r4], the complement checksum at [r4+2] ; Returns r0 = 0 (success code)
**Calls:** (none)
Zero-extend r5 (value) → r3 ; Shift r3 left by 16 bits: r3 = r3 << 16 (places the value in the high word) ; Compute NOT of r5 (value) → r2, zero-extend → r2 (complement) ; Add r2 to r3: r3 = r3 + r2 (combine
the value in the high word + the complement in the low word) ; Write the 32-bit result to [r4]: mov.l r3, @r4 ; Return r0 = 0
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
**Status:** high (mirrors the 8-bit structure exactly; confirms the checksum encoding pattern)
**Uncertainties:** Same as 8-bit: no interrupt masking in this function (caller responsibility?) ; Whether the return value is ever checked

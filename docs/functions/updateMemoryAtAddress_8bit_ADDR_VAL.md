# updateMemoryAtAddress_8bit_ADDR_VAL @ 0x3E1F8
**Purpose:** Write an 8-bit value to RAM together with its complement checksum (no interrupt masking in this stub).
**Inputs:** `r4`: target address in RAM ; `r5`: value to write (8-bit)
**Out:** Writes the value at [r4], the complement checksum at [r4+1] ; Returns r0 = 0 (success code)
**Calls:** (none)
Zero-extend r5 (value) → r3 ; Shift r3 left by 8 bits: r3 = r3 << 8 (places the value in the high byte) ; Compute NOT of r5 (value) → r2, zero-extend → r2 (complement) ; Add r2 to r3: r3 = r3 + r2 (combine
the value in the high byte + the complement in the low byte) ; Write the 16-bit result to [r4]: mov.w r3, @r4 ; Return r0 = 0
**Draft C:**
```c
int updateMemoryAtAddress_8bit_ADDR_VAL(uint8_t *addr, uint8_t value)
{
    uint16_t data = ((uint16_t)value << 8) | ((~value) & 0xFF);
    *(uint16_t*)addr = data;
    return 0;
}
```
Or more explicitly:
```c
int updateMemoryAtAddress_8bit_ADDR_VAL(uint8_t *addr, uint8_t value)
{
    addr[0] = value;
    addr[1] = (~value) & 0xFF;
    return 0;
}
```
**Status:** high (simple direct encoding; matches the readValue_8bit checksum layout exactly)
**Uncertainties:** Whether the caller is responsible for interrupt masking (this function does not call getSR/setSR unlike the read functions) ; Whether the caller ever checks the return value (r0=0)

# setImmoLight @ 0x25DF4
**Purpose:** Controls the immobilizer warning lamp (MIL-style indicator) by manipulating a hardware register via bit-set/clear operations; manages CPU interrupt state during register access.
**Inputs:** `r4`: lamp state (0x01 = on, 0x00 = off)
**Out:** Modifies hardware register at 0xF754 (likely an I/O port or control register): ; If r4 == 1: sets bits 64 (0x40) and 32 (0x20) ; If r4 == 0: clears bits 64 and 32 ; Refreshes register state by calling `loadStatusRegister` (0x25E80) ; Saves/restores SR (interrupt mask) via helper calls
**Calls:** `setSR_PARAM(r4, r5)` @ 0x2054: Save SR and disable interrupts ; `setRegister_REG_BIT_VAL(reg, bit, val)` @ 0x4BBC: Set or clear a bit in a register ; `loadStatusRegister_ADDR(sr)` @ 0x2064: Restore SR and sync HW state
Save r10-r14 to stack ; Load helper function addresses: ; r10 ← setSR_PARAM (0x2054) ; r11 ← loadStatusRegister_ADDR (0x2064) ; r14 ← setRegister_REG_BIT_VAL (0x4BBC) ; Load register constants: ; r12
← register address 0xF754 (masked as 0x00E0) ; r13 ← register address 0xF754 (full) ; Test r4 (lamp state): ; If r4 == 1 (lamp ON): ; Call setSR_PARAM to save interrupt state (stack frame at r15+20) ;
Call setRegister_REG_BIT_VAL(0xF754, 0x40, 1) — set bit 64 ; Call loadStatusRegister_ADDR(saved_sr) ; Call setSR_PARAM to save again (stack frame at r15+16) ; Call setRegister_REG_BIT_VAL(0xF754,
0x20, 1) — set bit 32 ; Call loadStatusRegister_ADDR(saved_sr) ; If r4 == 0 (lamp OFF): ; Call setSR_PARAM (stack frame at r15+12) ; Call setRegister_REG_BIT_VAL(0xF754, 0x20, 0) — clear bit 32 ; Call
loadStatusRegister_ADDR(saved_sr) ; Call setSR_PARAM (stack frame at r15+8) ; Call setRegister_REG_BIT_VAL(0xF754, 0x40, 0) — clear bit 64 ; Call loadStatusRegister_ADDR(saved_sr) ; Restore r10-r14
and return
**Draft C:**
```c
void setImmoLight(uint8_t state) {
    volatile uint16_t *reg = (uint16_t *)0xF754;
    if (state == 1) {
        // Lamp ON: set bits 6 and 5
        uint32_t sr = setSR_PARAM(0x00E0);
        setRegister_REG_BIT_VAL(0xF754, 0x40, 1);  // bit 64 (bit 6)
        loadStatusRegister_ADDR(sr);
        sr = setSR_PARAM(0x00E0);
        setRegister_REG_BIT_VAL(0xF754, 0x20, 1);  // bit 32 (bit 5)
        loadStatusRegister_ADDR(sr);
    } else {
        // Lamp OFF: clear bits 6 and 5
        uint32_t sr = setSR_PARAM(0x00E0);
        setRegister_REG_BIT_VAL(0xF754, 0x20, 0);  // bit 32 (bit 5)
        loadStatusRegister_ADDR(sr);
        sr = setSR_PARAM(0x00E0);
        setRegister_REG_BIT_VAL(0xF754, 0x40, 0);  // bit 64 (bit 6)
        loadStatusRegister_ADDR(sr);
    }
}
```
**Status:** high ; Register address 0xF754 and bit patterns (0x40, 0x20) are consistent ; Function name matches immobilizer lamp control pattern ; SR save/restore + register sync indicate HW interaction with interrupt protection ; Uncertainties: exact bit meanings (64/32 may be bit-counting artifact), whether ON requires both bits or just one

# getOBDFuelModificationRequest @ 0x2FE14

_source: AI (Haiku) draft, unverified_

**Purpose:** Calculate OBD fuel modification request (regulatory fuel trim) while preserving CPU status register.

**Inputs:** 
- Current CPU status register (SR) — saved/restored around processing
- Global fuel-related state and parameters (read by called functions)

**Outputs / side effects:** 
- Modifies fuel-related memory (written by called functions)
- Restores original SR

**Calls:** 
- getSR @ 0x3920 (read current CPU status with interrupt state)
- FUN_000300B8 @ 0x000300B8 (unknown, likely clears interrupt flags or sets mode)
- filterFuelVolumeRequest @ 0x2FE88 (applies low-pass filter to fuel volume request)
- calculateFuelingRequestMaxForOBDControl @ 0x2FEB4 (calculates maximum allowed fuel trim)
- fuelingAddOBDControlMode @ 0x2FFD8 (adds OBD mode offset/adjustment to fueling)
- FUN_0002fd86 @ 0x0002FD86 (unknown, likely finalization or side-effect update)
- setSR @ 0x3934 (restore original CPU status register)

**Behavior:**
1. Save current SR (interrupt/CPU state)
2. Call FUN_000300B8 with mode flag 16 (likely disables interrupts or sets atomic mode)
3. Allocate 4 bytes on stack (add #-4, r15)
4. Call filterFuelVolumeRequest (apply filtering)
5. Call calculateFuelingRequestMaxForOBDControl (compute bounds)
6. Call fuelingAddOBDControlMode (apply OBD offset)
7. Call FUN_0002fd86 (finalization)
8. Restore saved SR (restores interrupt state)

**Draft C:**
```c
void getOBDFuelModificationRequest(void) {
    uint32_t sr_save = getSR();
    FUN_000300B8(16);  // Likely disable interrupts
    
    filterFuelVolumeRequest();
    calculateFuelingRequestMaxForOBDControl();
    fuelingAddOBDControlMode();
    FUN_0002fd86();
    
    setSR(sr_save);  // Restore interrupt state
}
```

**Confidence:** med — call sequence and SR preservation visible; purpose of each called function inferred from names; FUN_000300B8 and FUN_0002fd86 purpose unknown.

**Uncertainties:**
- Exact purpose of FUN_000300B8 (likely interrupt control, mode flag 16 significance unknown)
- Purpose of FUN_0002fd86 (likely memory or register finalization)
- Whether this is atomic operation (likely yes, given SR save/restore)

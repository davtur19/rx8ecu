# vfadControl @ 0x3505C

_source: AI (Haiku) draft, unverified_

**Purpose:** Control Variable Fresh Air Duct (VFAD) actuator. Similar to VDI but for rotary intake fresh-air duct. Compares sensor to thresholds and actuates based on conditions.

**Inputs:**
- Current sensor value from 0xB594 (float) 
- Cal min/max thresholds from 0x0792B8, 0x0792BC (float)
- VFAD control byte from 0xC1E0

**Outputs / side effects:**
- Updates VFAD control register at 0xC1E0
- Calls setRegister_REG_BIT_VAL (0x4BBC) with register 0xF754, bit value 0x0400
- Calls setSR_PARAM and loadStatusRegister_ADDR for SR manipulation

**Calls:**
- diagControlVFADMAYBE (0x5B5B4) - returns control command (0 or 1)
- setRegister_REG_BIT_VAL (0x4BBC) - sets hardware register bit
- setSR_PARAM (0x2054) - saves processor status register
- loadStatusRegister_ADDR (0x2064) - restores SR

**Behavior:**
1. Load sensor value and thresholds from calibration
2. Compare sensor against bounds
3. Call diagControlVFADMAYBE to get control command
4. Store result at 0xC1E0
5. If control == 1: save SR, call setRegister with bit 0x0400, restore SR
6. If control == 0: similar operation with bit value 0

**Draft C:**
```c
void vfadControl() {
    float sensorVal = *(float*)0xB594;
    float minThresh = *(float*)0x0792B8;
    float maxThresh = *(float*)0x0792BC;
    
    u8 controlCmd;
    if (sensorVal >= maxThresh) {
        controlCmd = 1;
    } else if (sensorVal >= minThresh) {
        controlCmd = diagControlVFADMAYBE(preliminary_state);
    } else {
        controlCmd = 0;
    }
    
    *(u8*)0xC1E0 = controlCmd;
    
    setSR_PARAM();
    if (controlCmd == 1) {
        setRegister_REG_BIT_VAL(0xF754, 0x0400, 1);
    } else {
        setRegister_REG_BIT_VAL(0xF754, 0x0400, 0);
    }
    loadStatusRegister_ADDR();
}
```

**Confidence:** med - Structure mirrors VDIControl; exact threshold semantics and SR need unconfirmed.

**Uncertainties:**
- Exact boundary conditions and comparison operators
- Purpose of SR save/restore
- Semantics of diagControlVFADMAYBE vs diagControlVDI
- Whether bit 0x0400 is mask or position

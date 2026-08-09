# vfadControl @ 0x3505C
**Purpose:** Control the Variable Fresh Air Duct (VFAD) actuator. It is similar to VDI but for the rotary intake fresh-air duct. Compare the sensor to the thresholds. Actuate based on the conditions.
**Inputs:** Current sensor value from 0xB594 (float) ; Cal min/max thresholds from 0x0792B8, 0x0792BC (float) ; VFAD control byte from 0xC1E0
**Out:** Updates the VFAD control register at 0xC1E0 ; Calls setRegister_REG_BIT_VAL (0x4BBC) with register 0xF754, bit value 0x0400 ; Calls setSR_PARAM and loadStatusRegister_ADDR for SR manipulation
**Calls:** diagControlVFADMAYBE (0x5B5B4) - returns the control command (0 or 1) ; setRegister_REG_BIT_VAL (0x4BBC) - sets the hardware register bit ; setSR_PARAM (0x2054) - saves the processor status register ; loadStatusRegister_ADDR (0x2064) - restores SR
Load the sensor value and the thresholds from calibration ; Compare the sensor against the bounds ; Call diagControlVFADMAYBE to get the control command ; Store the result at 0xC1E0 ; If control == 1: save SR, call
setRegister with bit 0x0400, restore SR ; If control == 0: similar operation with bit value 0
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
**Status:** med — mirrors VDIControl. The threshold semantics and SR need confirmation.
**Uncertainties:** The boundary conditions and comparison operators? The purpose of the SR save/restore? diagControlVFADMAYBE vs diagControlVDI? Is 0x0400 a bit mask or a position?

# VDIControl @ 0x34F64
**Purpose:** Control the Variable Dynamic Intake (VDI) actuator. Compare the sensor thresholds. Call the diagnostic/register control helper based on the conditions.
**Inputs:** Current sensor value from 0xB594 (float) ; Cal min/max thresholds from 0x0792B0, 0x0792B4 (float) ; VDI control byte from 0xC1DC
**Out:** Updates the VDI control register at 0xC1DC ; May trigger setRegister_REG_BIT_VAL (0x4BBC) with register 0xF746 and the bit value ; Calls setSR_PARAM and loadStatusRegister_ADDR for SR manipulation
**Calls:** diagControlVDI (0x5ABB0) - returns the control command (0 or 1) ; setRegister_REG_BIT_VAL (0x4BBC) - sets the hardware register bit ; setSR_PARAM (0x2054) - saves the processor status register ; loadStatusRegister_ADDR (0x2064) - restores SR
Load the current sensor value and the thresholds ; Compare the sensor value against the min/max bounds ; Determine the preliminary control state from the comparison result ; Call diagControlVDI(r4) to get the final control
command ; Store the result in the VDI control byte at 0xC1DC ; If control == 1: call setRegister with bit value 1, else 0 ; Perform the SR save/restore around the register operation
**Draft C:**
```c
void VDIControl() {
    float sensorVal = *(float*)0xB594;
    float minThresh = *(float*)0x0792B0;
    float maxThresh = *(float*)0x0792B4;
    u8 controlCmd;
    if (sensorVal >= maxThresh) {
        controlCmd = 1;
    } else if (sensorVal >= minThresh) {
        controlCmd = diagControlVDI(preliminary_state);
    } else {
        controlCmd = 0;
    }
    *(u8*)0xC1DC = controlCmd;
    if (controlCmd == 1) {
        setSR_PARAM();
        setRegister_REG_BIT_VAL(0xF746, 32, 1);
        loadStatusRegister_ADDR();
    }
}
```
**Status:** med - Core logic is clear. The SR manipulation purpose and the exact threshold logic are uncertain.
**Uncertainties:** The exact boundary condition (>= vs >) ; The semantics of the diagControlVDI intermediate state ; Why the register operation needs the SR save/restore ; The bit position (32) semantics for 0xF746

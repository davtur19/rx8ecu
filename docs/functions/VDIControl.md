# VDIControl @ 0x34F64
**Purpose:** Control Variable Dynamic Intake (VDI) actuator. Compares sensor thresholds and calls diagnostic/register control helper based on conditions.
**Inputs:** Current sensor value from 0xB594 (float) ; Cal min/max thresholds from 0x0792B0, 0x0792B4 (float) ; VDI control byte from 0xC1DC
**Out:** Updates VDI control register at 0xC1DC ; May trigger setRegister_REG_BIT_VAL (0x4BBC) with register 0xF746 and bit value ; Calls setSR_PARAM and loadStatusRegister_ADDR for SR manipulation
**Calls:** diagControlVDI (0x5ABB0) - returns control command (0 or 1) ; setRegister_REG_BIT_VAL (0x4BBC) - sets hardware register bit ; setSR_PARAM (0x2054) - saves processor status register ; loadStatusRegister_ADDR (0x2064) - restores SR
Load current sensor value and thresholds ; Compare sensor value against min/max bounds ; Determine preliminary control state based on comparison result ; Call diagControlVDI(r4) to get final control
command ; Store result in VDI control byte at 0xC1DC ; If control == 1: call setRegister with bit value 1, else 0 ; Perform SR save/restore around register operation
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
**Status:** med - Core logic clear; SR manipulation purpose and exact threshold logic uncertain.
**Uncertainties:** Exact boundary condition (>= vs >) ; Semantic of diagControlVDI intermediate state ; Why SR save/restore needed for register operation ; Bit position (32) semantics for 0xF746

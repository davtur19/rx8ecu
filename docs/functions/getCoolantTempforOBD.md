# getCoolantTempforOBD @ 0x53590
**Purpose:** OBD-II Mode 22 handler. Reads engine coolant temperature, adds -40°C offset (OBD-II standard), and encodes as u8 (0–255 = -40 to +215°C).
**Inputs:** None (reads global coolant temp value)
**Out:** Returns u8 in r0 (0–255, representing -40 to +215°C in OBD-II encoding) ; Calls floatToInt_SIGNAL_MULT_OFFSET for scaling/offset
**Calls:** floatToInt_SIGNAL_MULT_OFFSET (0x000024D0): Scale float with multiplier and offset → u8
**Behavior:** Load coolant temperature from 0xFFFF9F70 (RAM) → fr4 ; Load constant -40.0 (OBD offset) → fr6 ; Call floatToInt_SIGNAL_MULT_OFFSET(fr4, multiplier=1.0, offset=-40.0, ...) → r0 ; Return r0 as u8
**Draft C:**
```c
uint8_t getCoolantTempforOBD(void) {
    volatile float32 *coolant_temp_ptr = (volatile float32 *) 0xFFFF9F70;
    float32 temp_c = *coolant_temp_ptr;
    // OBD-II PID 0x05: coolant temp encoded as (temp + 40)
    // 0°C → 40, 100°C → 140, etc.
    return floatToInt_SIGNAL_MULT_OFFSET(temp_c, 1.0f, 1.0f, -40.0f, 0.0f);
}
```
**Status:** med (OBD encoding standard is clear, RAM address unconfirmed)
Notes: Coolant temperature is OBD-II PID 0x05 ; OBD encoding: u8 = (Temp_C + 40) where 0 = -40°C, 255 = +215°C ; RAM address 0xFFFF9F70 is in ECU RAM space (FFFF prefix indicates internal RAM on SH7055) ; floatToInt_SIGNAL_MULT_OFFSET likely performs: (temp + offset) * scale, clamped to u8

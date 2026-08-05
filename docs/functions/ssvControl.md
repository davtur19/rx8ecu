# ssvControl @ 0x220F8
**Purpose:** Control Secondary Shutter Valve (SSV) position based on throttle/air demand and operating conditions, with ramping and state transitions.
**Inputs:** RAM 0xAACC: SSV mode/command byte ; RAM 0xA9FC: air demand or throttle position (float) ; RAM 0x000729C0: SSV calibration offset (float) ; RAM 0x000729BE: SSV target angle (16-bit, conditional) ; RAM 0x000729BC: SSV control mode flag
**Out:** RAM 0xFFFFB310: SSV actuator command (byte, 0=close, 1=open) ; RAM 0xFFFFB30E: SSV ramp/position register (16-bit signed)
**Calls:** None
Read SSV mode flag (0xAACC) into r11 ; Load calibration offset (0x000729C0) into fr6 ; Add offset to calibration constant (-3) to compute control range ; Compare air demand (0xA9FC) against
calibration offset and adjusted offset: ; If demand > offset: set SSV to OPEN (r5=1, write to 0xFFFFB310) ; Else if demand < adjusted offset: set SSV to CLOSED (r5=0) ; If mode byte == 0: ; Check flag
at 0xFFFFB311; if != 1: skip ramp logic ; Else if mode byte indicates active control: ; Load target angle from 0x000729BE ; Update ramp register at 0xFFFFB30E by adding target ; Check secondary
control flag (0x000729BC); if 1: process special ramping ; If ramp register is positive: ; Decrement by 0x0000FFFF (saturating subtraction); conditional write ; Handle multi-stage state machine for
SSV engagement
**Draft C:**
```c
void ssvControl(void) {
  u8 ssvMode = readMemory8(0xAACC);
  float airDemand = readFloatMemory(0xA9FC);
  float calibOffset = readFloatMemory(0x000729C0);
  float adjustedOffset = calibOffset - 3.0f;
  u8 ssvCmd = 0;
  if (airDemand > calibOffset) {
    ssvCmd = 1;
  } else if (airDemand < adjustedOffset) {
    ssvCmd = 0;
  }
  writeMemory8(0xFFFFB310, ssvCmd);
  if (ssvMode == 0) {
    u8 flag = readMemory8(0xFFFFB311);
    if (flag == 1) {
      u16 targetAngle = readMemory16(0x000729BE);
      i16 ramp = (i16)readMemory16(0xFFFFB30E);
      ramp += targetAngle;
      writeMemory16(0xFFFFB30E, (u16)ramp);
    }
  }
  u8 ctrlFlag = readMemory8(0x000729BC);
  if (ctrlFlag == 1) {
    // Special ramping logic
  }
  if (readMemory16(0xFFFFB30E) > 0) {
    i16 ramp = (i16)readMemory16(0xFFFFB30E);
    ramp -= 0xFFFF;  // saturating decrement
    writeMemory16(0xFFFFB30E, (u16)ramp);
  }
}
```
**Status:** med ; SSV purpose inferred from function name (secondary shutter valve on rotary) ; Exact control thresholds and ramping constants uncertain ; State machine logic partially reconstructed from conditional branches ; Mode/flag meanings unclear (enable? active?)

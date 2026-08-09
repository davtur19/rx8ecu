# ssvControl @ 0x220F8
**Purpose:** Control the Secondary Shutter Valve (SSV) position. Base it on throttle/air demand and operating conditions, with ramp and state transitions.
**Inputs:** RAM 0xAACC: SSV mode/command byte ; RAM 0xA9FC: air demand or throttle position (float) ; RAM 0x000729C0: SSV calibration offset (float) ; RAM 0x000729BE: SSV target angle (16-bit, conditional) ; RAM 0x000729BC: SSV control mode flag
**Out:** RAM 0xFFFFB310: SSV actuator command (byte, 0=close, 1=open) ; RAM 0xFFFFB30E: SSV ramp/position register (16-bit signed)
**Calls:** None
Read the SSV mode flag (0xAACC) into r11 ; Load the calibration offset (0x000729C0) into fr6 ; Add the offset to the calibration constant (-3) to compute the control range ; Compare air demand (0xA9FC) against
the calibration offset and the adjusted offset: ; If demand > offset: set SSV to OPEN (r5=1, write to 0xFFFFB310) ; Else if demand < adjusted offset: set SSV to CLOSED (r5=0) ; If mode byte == 0: ; Check the flag
at 0xFFFFB311; if != 1: skip the ramp logic ; Else if the mode byte indicates active control: ; Load the target angle from 0x000729BE ; Add the target to the ramp register at 0xFFFFB30E ; Check the secondary
control flag (0x000729BC); if 1: process a special ramp ; If the ramp register is positive: ; Decrement by 0x0000FFFF (saturating subtraction); conditional write ; Handle the multi-stage state machine for
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
**Status:** med — purpose from the name (secondary shutter valve). The thresholds and ramp constants are uncertain. The state machine is partially reconstructed. The mode and flag meanings are unclear.

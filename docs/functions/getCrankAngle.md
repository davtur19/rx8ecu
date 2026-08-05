# getCrankAngle @ 0x7FCC
**Purpose:** Calculate current crank angle from sensor input (0-359 degrees), maintaining circular buffer of samples and rolling sample counter.
**Inputs:** r4: sensor sample (0-255, extu.b zero-extends) ; RAM 0xFFFF9FA8: some sensor input value ; RAM 0xFFFF9FB8: another sensor parameter
**Out:** RAM 0xFFFF9F84: stores r5 (from 0xFFFF9FA8) ; RAM 0xFFFF9F9C: stores r7 (from 0xFFFF9FB8) ; RAM 0xFFFF9F98: crank angle as f32 (result of: fpul converted to float, scaled by 30, mod 720) ; RAM 0xFFFF9FE9: rolling counter (byte, incremented; wraps at 6) ; RAM 0xFFFF9FE8: byte counter 2 (wraps at 0xFF) ; RAM 0xFFFF9FD0: circular buffer storage (indexed by r2*4, stores r3) ; return r0: (implicit, no explicit return observed)
**Calls:** None
Load sensor parameters from RAM (0xFFFF9FA8, 0xFFFF9FB8) ; Zero-extend r4 (byte input) ; Convert r4 to float: `fpul = r4; float fpul → fr3` ; Load constants: -5.0 (fr4), 30.0 (fr0), 720.0 (fr5) ;
Compute angle: `fr4 = fr0 * fr3 + (-5.0)` → scaled by 30 ; If angle < 0, add 720: `if fr4 <= 0 { fr4 += 720 }` ; Store angle to RAM 0xFFFF9F98 ; Increment rolling counter at 0xFFFF9FE9 (wraps at 6) ;
Store current angle into circular buffer at 0xFFFF9FD0 (indexed by counter*4) ; Increment second counter at 0xFFFF9FE8 (wraps at 0xFF)
**Draft C:**
```c
float crank_angle_buffer[6];  // @ 0xFFFF9FD0
uint8_t sample_counter;       // @ 0xFFFF9FE9, wraps at 6
uint8_t byte_counter;         // @ 0xFFFF9FE8, wraps at 0xFF
float current_crank_angle;    // @ 0xFFFF9F98
void getCrankAngle(uint8_t sensor_sample) {
    float angle = (float)sensor_sample * 30.0f - 5.0f;
    if (angle < 0.0f) {
        angle += 720.0f;
    }
    current_crank_angle = angle;
    // Store in circular buffer
    uint8_t idx = sample_counter;
    crank_angle_buffer[idx] = angle;
    sample_counter++;
    if (sample_counter >= 6) {
        sample_counter = 0;
    }
    byte_counter++;
    if (byte_counter >= 0xFF) {
        byte_counter = 0;
    }
}
```
**Status:** med ; Angle calculation (scale 30, subtract 5, modulo 720) is clear ; Circular buffer structure inferred from indexing pattern ; Unknown: exact meaning of the two counters; why 6 samples; why 0xFF threshold; what 0xFFFF9FA8/9FB8 represent

# getConditionalsForRevLimit @ 0xEE86
_source: AI (Haiku) draft, unverified_

**Purpose:** Determine rev-limit conditional flags based on engine speed, throttle, and operational mode.

**Inputs:**
- Globals:
  - 0xA9FC = engine speed or load threshold (float)
  - 0xBB24 = mode/condition byte
  - 0x6DA3C, 0x6DA40 = rpm thresholds or speed boundaries (float)
  - 0xB580 = condition flag byte
  - 0xA4A6, 0xA4AE, 0xA4AD = output control bytes
  - 0xA450 = throttle related byte
  - 0x6DA34 = rev-limit override or condition value

**Outputs / side effects:**
- 0xA4A6: rev-limit conditional flag (set to 1 or 0 based on speed ranges)
- 0xA4AE: secondary conditional flag
- 0xA4AD: throttle or mode adjustment byte
- 0xFFFFA4AA: rev-limit status flag

**Calls:** None (pure logic)

**Behavior:**
1. Initialize r7 = 1 (default rev-limit active)
2. Load engine speed (0xA9FC) → fr4
3. Load mode byte (0xBB24) → r4
4. Load rpm threshold (0x6DA3C) → fr5
5. Load rpm threshold2 (0x6DA40) → fr3
6. Compute: fr6 = fr5 - fr3 (threshold delta)
7. Check if fr4 > fr6:
   - If yes (speed high): set r6 = 0, write to 0xA4A6
   - If no: check fr4 > fr5 (within threshold)
     - If yes: skip write (leave as is)
     - If no: write r6 to 0xA4A6
8. Load condition byte (0xB580) → r2, check if non-zero:
   - If zero: check mode r4, check throttle 0xA4AD
   - If all conditions met: load value from 0x6DA34 → write to 0xA4AE
9. Final: read 0xA4AE, if positive, write (value + 0xFF) else write 0
10. Write mode byte to 0xA4AD

**Draft C:**
```c
void getConditionalsForRevLimit(void) {
  float speed = *(float *)0xA9FC;
  uint8_t mode = *(uint8_t *)0xBB24;
  float rpm_high = *(float *)0x6DA3C;
  float rpm_low = *(float *)0x6DA40;
  uint8_t cond = *(uint8_t *)0xB580;
  
  uint8_t rev_limit_flag = 1;  // Default active
  
  // Speed comparison logic
  if (speed > (rpm_high - rpm_low)) {
    rev_limit_flag = 0;  // High speed: disable
    *(uint8_t *)0xA4A6 = rev_limit_flag;
  } else if (speed > rpm_high) {
    // Within upper threshold
  } else {
    *(uint8_t *)0xA4A6 = rev_limit_flag;
  }
  
  // Conditional mode checks
  if (cond == 0) {
    uint8_t throttle_adj = *(uint8_t *)0xA4AD;
    if (mode != 0 && throttle_adj != 0 && mode != 7) {
      uint8_t override = *(uint8_t *)0x6DA34;
      *(uint8_t *)0xA4AE = override;
    }
  }
  
  // Adjust threshold value
  uint8_t limit_val = *(uint8_t *)0xA4AE;
  if (limit_val > 0) {
    *(uint8_t *)0xFFFFA4AA = 1;
    *(uint8_t *)0xA4AE = limit_val + 0xFF;
  } else {
    *(uint8_t *)0xFFFFA4AA = 0;
  }
  
  *(uint8_t *)0xA4AD = mode;
}
```

**Confidence:** med
- Overall logic structure is clear: speed range checking → conditional flags
- Some branch conditions are ambiguous (exact threshold application)
- Final threshold adjustment (limit_val + 0xFF) logic unclear — may be saturation or wraparound
- The 0xFFFFA4AA role (temp storage?) not fully determined

# setEngineLoadInitalVal @ 0x341DA

_source: AI (Haiku) draft, unverified_

**Purpose:** Initialize engine load value by reading from ROM calibration table and writing to RAM working register.

**Inputs:**
- Float calibration value from ROM 0x00078CE4

**Outputs / side effects:**
- Writes float value to RAM 0xC0D8 (engine load working value)

**Calls:** None (direct memory operations only)

**Behavior:**
1. Load float from calibration address 0x00078CE4 into fr3
2. Store immediately to RAM address 0xC0D8
3. Return

**Draft C:**
```c
void setEngineLoadInitalVal() {
    float calValue = *(float*)0x00078CE4;  // ROM calibration
    *(float*)0xC0D8 = calValue;            // initialize RAM working value
}
```

**Confidence:** high - Function is minimal; straight load-store operation.

**Uncertainties:**
- Whether this is called at startup or on demand
- Exact role of engine load in downstream calculations
- Whether 0x00078CE4 is a single value or lookup table base

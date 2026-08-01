# driveCycleDetect @ 0x63F80

_source: AI (Haiku) draft, unverified_

**Purpose:** Detects whether current engine operating conditions constitute an OBD-II "drive cycle" — a standardized sequence of engine loads, speeds, and temperatures used to verify emissions diagnostics are running. Returns 1 if drive cycle criteria are met, 0 otherwise.

**Inputs:** none (reads engine sensors via function calls)

**Outputs / side effects:**
- Returns in `r0`: 1 if drive cycle detected, 0 if criteria not met
- Uses FP registers (fr14, fr15) for intermediate float computations
- No persistent state modification

**Calls:**
- `FUN_00066068()` @ 0x64038: Read/validate sensor data (returns status in r4)
- `returnEngineSpeed()` @ 0x5E604: Get current engine RPM (returns float in fr0)
- `returnEngineLoad()` @ 0x5E5FE: Get current engine load % (returns float in fr0)
- `returnCoolantTempGreaterThan71()` @ 0x5E5F0: Check if coolant temp > 71°C (returns 0/1 in r0)
- `subtractAbsolute(a, b)` @ 0x23DC: Compute |a - b| (returns float in fr0)

**Behavior:**

1. Save r14, fr14, fr15 to stack; allocate 20 bytes of local frame
2. Initialize r14 = 1 (assume success)
3. Call `FUN_00066068()` to read sensor validity
4. If sensor data invalid (r4 == 0):
   - Return 0 (drive cycle not possible without valid sensors)
5. Call `returnEngineSpeed()` → store in fr14 (engine RPM as float)
6. Call `returnEngineLoad()` → store in fr15 (load % as float)
7. Call `returnCoolantTempGreaterThan71()` → store result (0/1) in stack and r4
8. Compute RPM change: call `subtractAbsolute(fr15, threshold_71.0)` → fr15 = |load% - 71|
9. Compute load change: call `subtractAbsolute(fr14, stack_value)` → fr4 = |rpm_change - something|
10. Load threshold 71.0 (float constant at 0x64044 = 0x428E0000)
11. Fetch stored threshold values:
    - 0x7DB0C ← engine load threshold (fr2)
    - 0x7DB08 ← engine speed threshold (fr1)
12. Branch on coolant temp (r4):
    - If r4 == 1 (coolant > 71°C):
      - Verify: load% ≤ threshold @ 0x7DB0C (if not, r14 = 0)
      - Verify: |speed_delta| ≤ threshold @ 0x7DB08 (if not, r14 = 0)
    - If r4 == 0 (coolant ≤ 71°C):
      - Verify: load% ≤ threshold @ 0x7DB0C (if not, r14 = 0)
      - Verify: |speed_delta| ≤ threshold @ 0x7DB08 (if not, r14 = 0)
13. Return r0 = r14 (1 if all criteria met, 0 if any failed)

**Draft C:**

```c
uint8_t driveCycleDetect(void) {
    // Read and validate sensor data
    uint8_t sensor_status = FUN_00066068();
    if (sensor_status == 0) {
        return 0;  // Invalid sensors
    }
    
    // Fetch sensor values as floats
    float engine_speed = returnEngineSpeed();
    float engine_load = returnEngineLoad();
    uint8_t coolant_hot = returnCoolantTempGreaterThan71();
    
    // Compute deltas from thresholds
    float load_delta = subtractAbsolute(engine_load, 71.0f);
    float speed_delta = subtractAbsolute(engine_speed, *(float *)0x7DB08);
    
    // Fetch stored thresholds
    volatile float *load_threshold = (float *)0x7DB0C;
    volatile float *speed_threshold = (float *)0x7DB08;
    
    // Drive cycle criteria
    uint8_t criteria_met = 1;
    
    if (coolant_hot == 1) {
        // Hot engine: strict thresholds
        if (engine_load > *load_threshold) criteria_met = 0;
        if (speed_delta > *speed_threshold) criteria_met = 0;
    } else {
        // Cold engine: same or different thresholds
        if (engine_load > *load_threshold) criteria_met = 0;
        if (speed_delta > *speed_threshold) criteria_met = 0;
    }
    
    return criteria_met;
}
```

**Confidence:** med
- Overall structure (sensor read, threshold checks, conditional logic) is sound
- Function calls and float-register usage are clear
- Threshold addresses (0x7DB08, 0x7DB0C) and constant 71.0°C are inferred from patterns
- Uncertainties:
  - Exact semantics of the two branch paths (hot vs. cold) — appear nearly identical in ASM
  - Meaning of intermediate deltas and how they combine
  - Whether thresholds are fixed or calibration values
  - Clarify: what is `subtractAbsolute(engine_load, 71.0)` actually computing? May be a complex weighted delta.

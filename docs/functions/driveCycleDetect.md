# driveCycleDetect @ 0x63F80
**Purpose:** Detect whether the current engine operating conditions form an OBD-II "drive cycle". A drive cycle is a standardized sequence of engine loads, speeds, and temperatures. It verifies that emissions diagnostics run. Returns 1 if the drive cycle criteria are met, 0 otherwise.
**Inputs:** none (reads engine sensors with function calls)
**Out:** Returns in `r0`: 1 if the drive cycle is detected, 0 if the criteria are not met ; Uses FP registers (fr14, fr15) for intermediate float computations ; No persistent state modification
**Calls:** `FUN_00066068()` @ 0x64038: Read/validate sensor data (returns status in r4) ; `returnEngineSpeed()` @ 0x5E604: Get current engine RPM (returns float in fr0) ; `returnEngineLoad()` @ 0x5E5FE: Get current engine load % (returns float in fr0) ; `returnCoolantTempGreaterThan71()` @ 0x5E5F0: Check if coolant temp > 71°C (returns 0/1 in r0) ; `subtractAbsolute(a, b)` @ 0x23DC: Compute |a - b| (returns float in fr0)
Save r14, fr14, fr15 to the stack; allocate 20 bytes of local frame. Initialize r14 = 1 (assume success). Call `FUN_00066068()` to read the sensor validity. If the sensor data is invalid (r4 == 0): return 0
(a drive cycle is not possible without valid sensors). Call `returnEngineSpeed()` → store the result in fr14 (engine RPM as float). Call `returnEngineLoad()` → store the result in fr15 (load % as float). Call
`returnCoolantTempGreaterThan71()` → store the result (0/1) in the stack and r4. Compute the RPM change: call `subtractAbsolute(fr15, threshold_71.0)` → fr15 = |load% - 71|. Compute the load change: call
`subtractAbsolute(fr14, stack_value)` → fr4 = |rpm_change - something|. Load threshold 71.0 (float constant at 0x64044 = 0x428E0000). Fetch the stored threshold values: 0x7DB0C ← engine load threshold
(fr2) ; 0x7DB08 ← engine speed threshold (fr1). Branch on the coolant temp (r4). If r4 == 1 (coolant > 71°C): verify that load% ≤ threshold @ 0x7DB0C (if not, r14 = 0); verify that |speed_delta| ≤ threshold
@ 0x7DB08 (if not, r14 = 0). If r4 == 0 (coolant ≤ 71°C): verify that load% ≤ threshold @ 0x7DB0C (if not, r14 = 0); verify that |speed_delta| ≤ threshold @ 0x7DB08 (if not, r14 = 0). Return r0 = r14 (1
if all criteria are met, 0 if any fails)
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
**Status:** med — the structure (sensor read, thresholds, conditionals) is sound; the thresholds (0x7DB08/0x7DB0C) and 71.0°C are inferred. Uncertain: the hot-vs-cold branches are nearly identical in ASM; the intermediate delta meaning; whether the thresholds are fixed or calibrated; `subtractAbsolute(engine_load, 71.0)` may be a weighted delta.

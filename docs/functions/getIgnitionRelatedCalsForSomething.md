# getIgnitionRelatedCalsForSomething @ 0x2C388
_source: AI (Haiku) draft, unverified_

**Purpose:** Fetch two ignition-related calibration values via 2D lookup table queries; likely ignition timing and dwell or advance maps.

**Inputs:**
- fr15: input lookup parameter (float, likely engine speed or load)

**Outputs / side effects:**
- 0xFFFFBC50: first calibration value (float)
- 0xFFFFBC54: second calibration value (float)

**Calls:**
- 0x2068 (2DLookup): called twice with different calibration table addresses
  - First call: table at 0x68C10, result stored at 0xFFFFBC50
  - Second call: table at 0x68C24, result stored at 0xFFFFBC54

**Behavior:**
1. Save fr15 (input parameter) and return address on stack
2. Load float from 0xB594 (likely engine RPM) → fr15
3. Load table pointer 0x68C10 → r4
4. Call 2DLookup(fr15, 0x68C10) with fr15 as input
5. Store result (fr0) at 0xFFFFBC50 (global RAM)
6. Load table pointer 0x68C24 → r4
7. Call 2DLookup(fr15, 0x68C24) with fr15 as input
8. Store result (fr0) at 0xFFFFBC54 (global RAM)
9. Restore stack and return

**Draft C:**
```c
void getIgnitionRelatedCalsForSomething(void) {
  float rpm = *(float *)0xB594;
  
  // First lookup
  float cal1 = twoD_lookup(rpm, (uint32_t *)0x68C10);
  *(float *)0xFFFFBC50 = cal1;
  
  // Second lookup (similar table, different offset)
  float cal2 = twoD_lookup(rpm, (uint32_t *)0x68C24);
  *(float *)0xFFFFBC54 = cal2;
}
```

**Confidence:** high
- Function structure is straightforward: load input → call 2DLookup twice → store results
- Both map addresses are hardcoded and visible
- No complex branching or conditional logic
- Offset difference between tables (0x68C24 - 0x68C10 = 0x14 bytes) suggests related maps

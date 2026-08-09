# getIgnitionRelatedCalsForSomething @ 0x2C388
**Purpose:** Fetch two ignition-related calibration values with 2D lookup table queries; likely ignition timing and dwell or advance maps.
**Inputs:** fr15: input lookup parameter (float, likely engine speed or load)
**Out:** 0xFFFFBC50: first calibration value (float) ; 0xFFFFBC54: second calibration value (float)
**Calls:** 0x2068 (2DLookup): called twice with different calibration table addresses ; First call: table at 0x68C10, result stored at 0xFFFFBC50 ; Second call: table at 0x68C24, result stored at 0xFFFFBC54
Save fr15 (input parameter) and return address on stack ; Load float from 0xB594 (likely engine RPM) → fr15 ; Load table pointer 0x68C10 → r4 ; Call 2DLookup(fr15, 0x68C10) with the input fr15 ; Store
result (fr0) at 0xFFFFBC50 (global RAM) ; Load table pointer 0x68C24 → r4 ; Call 2DLookup(fr15, 0x68C24) with the input fr15 ; Store result (fr0) at 0xFFFFBC54 (global RAM) ; Restore stack and return
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
**Status:** high ; Function structure is straightforward: load input → call 2DLookup twice → store results ; Both map addresses are hardcoded and visible ; No complex branching or conditional logic ; Offset difference between tables (0x68C24 - 0x68C10 = 0x14 bytes) suggests related maps

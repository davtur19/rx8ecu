# getSecondaryAirPumpRequestForMode22 @ 0x536E2
_source: AI (Haiku) draft, unverified_

**Purpose:** Determine secondary air pump request status for OBD mode 0x22 (read data by identifier).

**Inputs:**
- None (reads global state)

**Outputs / side effects:**
- r0: 1 or 4 (pump request code)

**Calls:** None

**Behavior:**
1. Read byte from address 0xA9D0
2. If value == 1, return 1
3. Otherwise return 4

**Draft C:**
```c
uint8_t getSecondaryAirPumpRequestForMode22(void) {
  uint8_t pump_flag = *(uint8_t*)0xA9D0;
  return (pump_flag == 1) ? 1 : 4;
}
```

**Confidence:** high – simple conditional return, equinox name reliable, addresses suggest OBD getter pattern

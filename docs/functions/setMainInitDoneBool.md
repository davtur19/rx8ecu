# setMainInitDoneBool?? @ 0x9F0C

_source: AI (Haiku) draft, unverified_

**Purpose:** Set initialization complete flag in system state.

**Inputs:**
- r4: boolean value (typically 0 or 1, or 0xFF for done)

**Outputs / side effects:**
- Memory at 0xFFFFA16C: byte set to r4

**Calls:** none

**Behavior:**
1. Load address 0xFFFFA16C into r2
2. Write r4 (byte) to r2

**Draft C:**
```c
void setMainInitDoneBool(uint8_t done_flag) {
  *(volatile uint8_t*)0xFFFFA16C = done_flag;
}
```

**Confidence:** high - trivial memory write; address 0xFFFFA16C is in RAM (0xFFFFxxxx space). Name strongly suggests initialization state flag.

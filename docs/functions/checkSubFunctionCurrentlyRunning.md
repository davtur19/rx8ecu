# checkSubFunctionCurrentlyRunning?? @ 0x54146

_source: AI (Haiku) draft, unverified_

**Purpose:** Check if a UDS sub-function is currently executing; likely reads a state flag that indicates whether a diagnostic sub-routine (e.g., ReadDataByIdentifier service) is in progress.

**Inputs:**
- None (reads global state flag)

**Outputs:**
- r0: Sub-function state byte (0x00 = idle, non-zero = sub-function running)

**Calls:**
- None

**Behavior:**

1. Load address of sub-function state flag: r3 = 0xFFFFCFE3
2. Return (rts) immediately
3. Load byte from that address: r0 = [0xFFFFCFE3]

_Note: Instruction order is delayed-slot (rts is executed before the mov.b)_

**Draft C:**

```c
uint8_t checkSubFunctionCurrentlyRunning(void) {
    uint8_t state = *(volatile uint8_t *)0xFFFFCFE3;
    return state;
}
```

**Confidence:** low–med
- Extremely minimal function; just returns a flag
- Name has ?? uncertainty marker; confirm usage context
- Uncertainties:
  - Exact meaning of return value (0=idle, >0=running, or bitfield?)
  - Which UDS services/sub-functions set this flag
  - Whether this is a lock/semaphore or simple state machine
  - Could also be for bootloader state or other subsystem checks
  - Recommend cross-referencing callers to verify purpose

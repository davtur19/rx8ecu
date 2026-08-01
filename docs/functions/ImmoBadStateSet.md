# ImmoBadStateSet @ 0x35A58

_source: AI (Haiku) draft, unverified_

**Purpose:** Marks immobilizer in a "bad state" condition: turns off the warning lamp, clears a lock flag, initializes a timeout counter, and sets a state code indicating immobilizer failure or invalid key challenge.

**Inputs:** none (uses global state)

**Outputs / side effects:**
- Calls `setImmoLight(0)` to turn off immobilizer warning lamp
- Writes to global registers:
  - 0xC1EC ← 0x00 (lock/enable flag cleared)
  - 0xFFFFC230 ← 0x01F4 (500 decimal = ~5 sec timeout at 100 ms ticks)
  - 0xFFFFC239 ← 0x04 (state code: bad state)
- Returns: none

**Calls:**
- `setImmoLight(r4)` @ 0x25DF4: Control immobilizer lamp (called with r4=0)

**Behavior:**

1. Save PR to stack
2. Call `setImmoLight(0)` with r4=0 (turn lamp OFF)
3. Clear lock flag: write 0x00 to register 0xC1EC
4. Initialize timeout counter: write 0x01F4 (500 decimal) to register 0xFFFFC230
5. Set state code: write 0x04 to register 0xFFFFC239
6. Restore PR and return

**Draft C:**

```c
void ImmoBadStateSet(void) {
    // Turn off immobilizer warning lamp
    setImmoLight(0);
    
    // Clear lock/enable flag
    *(volatile uint8_t *)0xC1EC = 0x00;
    
    // Set timeout counter: 500 ticks (~5 seconds at 100 ms per tick)
    *(volatile uint16_t *)0xFFFFC230 = 0x01F4;
    
    // Set state code to 0x04 (bad/invalid state)
    *(volatile uint8_t *)0xFFFFC239 = 0x04;
}
```

**Confidence:** high
- Simple wrapper with clear side effects
- Constants (0x01F4 = 500) and register addresses match immobilizer context
- Semantics (bad state + timeout + lamp off) are internally consistent
- Uncertainties: exact meaning of state code 0x04, whether 0xC1EC is actually a "lock" flag or has other purposes

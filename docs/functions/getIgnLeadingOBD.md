# getIgnLeadingOBD @ 0x53614

_source: AI (Haiku) draft, unverified_

**Purpose:** OBD-II Mode 22 handler. Reads ignition timing advance, encodes as s8 (-64 to +63.5 degrees BTDC).

**Inputs:** None (reads global ignition timing value)

**Outputs / side effects:**
- Returns s8 in r0 (range -64 to +63.5, representing degrees BTDC in OBD-II encoding)
- Calls floatToInt_SIGNAL_MULT_OFFSET for scaling/offset

**Calls:**
- floatToInt_SIGNAL_MULT_OFFSET (0x000024D0): Scale float → s8

**Behavior:**
1. Load ignition timing from 0xA62C (RAM) → fr4
2. Load constant -64.0 (lower bound, BTDC = leading) → fr6
3. Load constant 0.5 (scale / upper bound divisor) → fr5
4. Call floatToInt_SIGNAL_MULT_OFFSET(fr4, ???, 0.5f, -64.0f, ???) → r0
5. Return r0 as s8

**Draft C:**
```c
int8_t getIgnLeadingOBD(void) {
    volatile float32 *timing_ptr = (volatile float32 *) 0xA62C;
    
    float32 timing = *timing_ptr;  // degrees BTDC (before top-dead-center)
    // OBD-II PID 0x0E: ignition timing as s8 with scale 0.5°/count
    // -64 to +63.5 degrees BTDC encoded as -128 to +127 scaled by 0.5
    return floatToInt_SIGNAL_MULT_OFFSET(timing, ???, 0.5f, -64.0f, ???);
}
```

**Notes:**
- Ignition timing is OBD-II PID 0x0E
- Encoding: s8 = (Timing / 0.5) where Timing in degrees BTDC (before TDC)
- Range: -64°C to +63.5°C BTDC (covers full s8 range with 0.5° resolution)
- BTDC = positive timing advance (leading edge)
- Scale 0.5 = 1 count per 0.5 degrees (2 counts per degree)
- UNKNOWN: confirm 0xA62C is ignition timing variable

**Confidence:** med (OBD encoding standard for timing clear, RAM address unconfirmed)

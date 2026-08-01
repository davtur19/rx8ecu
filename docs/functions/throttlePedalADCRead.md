# throttlePedalADCRead @ 0xAD2A

_source: AI (Haiku) draft, unverified_

**Purpose:** Appears to be a stub or jump table entry; actual code jumps to 0xAEE8 immediately. Likely reads throttle pedal ADC value.

**Inputs:** None apparent (stub entry point).

**Outputs / side effects:** Unknown; control transfers to 0xAEE8.

**Calls:** Indirect jump to 0xAEE8.

**Behavior:** 
1. Branch unconditionally to 0xAEE8
2. NOP (delay slot)
3. Data follows (likely pool or jump table)

**Draft C:** 
```c
void throttlePedalADCRead(void) {
    // Jumps to real implementation at 0xAEE8
    goto aee8;
}
```

**Confidence:** low — this address contains a jump redirect, not the actual function. Symbol may refer to entry point, real implementation likely at 0xAEE8.

**Uncertainties:** 
- Is this a tail call, PLT entry, or wrapper?
- What is the actual function at 0xAEE8?

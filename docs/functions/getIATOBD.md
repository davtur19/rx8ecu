# getIATOBD @ 0x53678

_source: AI (Haiku) draft, unverified_

**Purpose:** Retrieve intake air temperature (IAT) for OBD (On-Board Diagnostics) reporting, applying a fixed-point conversion and offset.

**Inputs:**
- None (reads global IAT value from 0xFFFF9F60)

**Outputs:**
- fr0: Converted IAT as float (returned in FPU register fr0)

**Calls:**
- 0x000024D0: floatToInt_SIGNAL_MULT_OFFSET (or similar fixed-point conversion function)

**Behavior:**

1. Save return address on stack (sts.l pr, @-r15)
2. Load address of global IAT value: r3 = 0xFFFF9F60
3. Load address of constant float (-40.0): r0 = &0x537A4
4. Load IAT float from memory: fr4 = [0xFFFF9F60]
5. Load constant float: fr6 = [-40.0]
6. Load function pointer: r2 = 0x000024D0
7. Set up function argument: fr5 = 1.0 (fldi1)
8. Call conversion function at 0x000024D0 (jsr @r2)
   - Likely performs: `result = (iat - (-40)) * mult_offset`
   - Or similar offset/scale operation
9. Restore return address: lds.l @r15+, pr
10. Return to caller (rts) with result in fr4/fr0

**Draft C:**

```c
float getIATOBD(void) {
    float iat = *(volatile float *)0xFFFF9F60;
    float offset = -40.0f;
    float mult = 1.0f;
    
    // Call conversion function with:
    // fr4 = iat, fr6 = offset (-40), fr5 = 1.0
    float result = floatToInt_SIGNAL_MULT_OFFSET(iat, offset, mult);
    
    return result;
}
```

**Confidence:** med
- Function clearly reads IAT from a known RAM address
- Constant -40.0 is a standard OBD offset for IAT (in Celsius)
- Called function name inferred from context; exact semantics depend on function at 0x000024D0
- Uncertainties:
  - Exact operation performed by floatToInt_SIGNAL_MULT_OFFSET
  - Whether fr5=1.0 is a multiplier or something else
  - Return value scaling/format for OBD reporting

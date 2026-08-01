# setEngineRunningInjectorsOffFlag @ 0xE2AC

_source: AI (Haiku) draft, unverified_

**Purpose:** Sets a flag indicating whether injectors should be shut off while engine is still running (safety cutoff during coast-down or fault condition).

**Inputs:** 
- @0xA42C: injectors_off_flag (output address)
- @0xA428: engine_running flag (1=running, 0=off)
- @0xA41C: some enable/disable or fault flag

**Outputs / side effects:** 
- Writes 1 or 0 to @0xA42C (injectors_off flag)
- Condition: set to 1 if (engine_running==1 AND flag@0xA41C==0), else 0

**Calls:** None (inline logic only).

**Behavior:** 
1. Load target address 0xA42C into r4
2. Load engine_running flag from 0xA428 into r3
3. Test r3 (if zero, engine is off)
4. If engine NOT running: jump to step 7 (set flag to 0)
5. Load flag from 0xA41C into r0
6. Test r0
7. If that flag is non-zero: jump to step 9 (set to 0)
8. Set r2=1, branch to step 10
9. Set r1=0
10. Write r2 or r1 to @r4 (0xA42C)
11. Return

**Draft C:** 
```c
void setEngineRunningInjectorsOffFlag(void) {
    uint8_t *injectors_off = (uint8_t *)0xA42C;
    uint8_t engine_running = *(uint8_t *)0xA428;
    uint8_t some_flag = *(uint8_t *)0xA41C;
    
    if (engine_running && !some_flag) {
        *injectors_off = 1;  // Cut injectors
    } else {
        *injectors_off = 0;  // Normal operation
    }
}
```

**Confidence:** med — control flow is clear, but semantic meaning of @0xA41C flag is unknown. Name suggests injector cutoff logic.

**Uncertainties:** 
- What condition at 0xA41C triggers the injector cutoff? (fault? throttle closed? over-rev?)
- Is injectors_off=1 mean "shut them off now" or "safe to leave off"?
- When does this flag get checked/acted upon?

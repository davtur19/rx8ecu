# reInitCrankSensor @ 0x7724

_source: AI (Haiku) draft, unverified_

**Purpose:** Reset crank sensor state machine; clear RPM accumulators, counters, edge flags; prepare for new crank pulse sequence.

**Inputs:** None

**Outputs / side effects:**
- Clears crank sensor state variables
- Initializes floating-point accumulator to 0.0
- Sets control flags for crank detection state machine
- Return: None or calls crankSensorInit if conditions are met

**Calls:**
- `0x7B58` (unknown) - state setup helper
- `0x7C0C` (crankSensorInit?) - full HW initialization (conditional)
- `0x7B84` (unknown) - final state setup (conditional)

**Behavior:**
1. Load base address 0xFFFF9F95 into r3
2. Set value 36 at offset +0 (r1 = 36 -> @r3)
3. Load 0.0 into FPU register fr3
4. Set various flags to 0:
   - 0xFFFF9FC1 = 0
   - 0xFFFF9FB0 = -1 (0xFFFFFFFF, init value)
   - 0xFFFF9FC2 = 0
5. Write 0.0 to 0xFFFF9FBC (RPM accumulator?)
6. Set 0xFFFF9FC5 = 0
7. Call helper at 0x7B58 with r14=0
8. Read flag from 0xFFFF9FC0; if = 1:
   - Clear 0xFFFF9FC0 = 0
   - Check 0xFFFF9FA3; if != 2, call crankSensorInit
   - Otherwise call 0x7B84

**Draft C:**
```c
void reInitCrankSensor(void) {
  u8* base = (u8*)0xFFFF9F95;
  
  base[0] = 36;          // counter
  *(float*)(base + 0x1D) = 0.0f;  // 0xFFFF9FBC RPM accum
  *(u8*)(base + 0x2C) = 0;        // 0xFFFF9FC1
  *(s32*)(base + 0x1B) = -1;      // 0xFFFF9FB0
  *(u8*)(base + 0x2D) = 0;        // 0xFFFF9FC2
  *(u8*)(base + 0x30) = 0;        // 0xFFFF9FC5
  
  unknown_helper_0x7B58(0);
  
  u8 state = *(u8*)0xFFFF9FC0;
  if (state == 1) {
    *(u8*)0xFFFF9FC0 = 0;
    
    u8 mode = *(u8*)0xFFFF9FA3;
    if (mode != 2) {
      crankSensorInit();
    } else {
      unknown_0x7B84();
    }
  }
}
```

**Confidence:** med — the initialization pattern is clear but the meaning of specific flag values (36, -1) and the conditional logic for crankSensorInit requires verification through emulation.

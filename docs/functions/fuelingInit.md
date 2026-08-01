# fuelingInit @ 0x7518

_source: AI (Haiku) draft, unverified_

**Purpose:** Initialize fueling subsystem; clear injection state, reset accumulators, call sensor reinitialization chain.

**Inputs:** None

**Outputs / side effects:**
- Clears multiple global state variables (flags, accumulators, counters)
- Clears hardware I/O register at 0xF6EA (fuel pump/injector control?)
- Calls multiple reinitialization functions
- Return: None

**Calls:**
- `0x76B8` (unknown) - early initialization step
- `0x7724` (reInitCrankSensor??) - reset crank sensor state
- `0x7BDC` (unknown) - fueling-related init
- `0x7B84` (unknown) - fueling-related init
- `0x7C0C` (crankSensorInit?) - initialize crank sensor HW
- `0x7EB4` (unknown) - fueling-related init
- `0x7F90` (unknown) - fueling-related init
- `0x806A` (unknown) - final fueling state setup

**Behavior:**
1. Call 0x76B8 (early fueling init)
2. Read hardware register at 0xF6EA and clear bit mask 0x0004
3. Initialize multiple RAM globals to 0 or 1:
   - 0xFFFF9FA3 = 1
   - 0xFFFF9FA4 = 0
   - 0xFFFF9FA5 = 0
   - 0xFFFF9FC0 = 0
   - 0xFFFF9FC4 = 0
   - 0xFFFF9FA2 = 0
4. Call reInitCrankSensor
5. Call fueling helper functions (0x7BDC, 0x7B84)
6. Initialize 0xFFFF9F96 = 0
7. Call crankSensorInit
8. Call final helpers (0x7EB4, 0x7F90)
9. Jump to 0x806A (likely part of initialization chain)

**Draft C:**
```c
void fuelingInit(void) {
  // Early init
  unknown_0x76B8();
  
  // Clear fuel pump control
  u16 hw_ctrl = *(u16*)0xF6EA;
  hw_ctrl &= 0xFFFB;  // clear bit 2
  *(u16*)0xF6EA = hw_ctrl;
  
  // Initialize state variables
  *(u8*)0xFFFF9FA3 = 1;
  *(u8*)0xFFFF9FA4 = 0;
  *(u8*)0xFFFF9FA5 = 0;
  *(u8*)0xFFFF9FC0 = 0;
  *(u8*)0xFFFF9FC4 = 0;
  *(u8*)0xFFFF9FA2 = 0;
  
  // Reset crank sensor
  reInitCrankSensor();
  
  // Fueling helpers
  unknown_0x7BDC();
  unknown_0x7B84();
  
  *(u8*)0xFFFF9F96 = 0;
  
  // Initialize crank sensor HW
  crankSensorInit();
  
  // Final init
  unknown_0x7EB4();
  unknown_0x7F90();
}
```

**Confidence:** med — the structure is clear (initialize flags/HW) but the exact meaning of each flag and helper function requires tracing. The name suggests fueling but involves crank sensor heavily.

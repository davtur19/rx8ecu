# getAutoTransCal @ 0x253CC

_source: AI (Haiku) draft, unverified_

**Purpose:** Check automatic transmission calibration enable flag and write corresponding state byte to output register.

**Inputs:**
- RAM 0x000749B0: automatic transmission calibration flag (byte)

**Outputs / side effects:**
- RAM 0xB580: automatic transmission calibration state output (byte, 1=enabled, 0=disabled)

**Calls:** None

**Behavior:**
1. Read calibration flag byte from 0x000749B0 into r3
2. Test r3 (compare against 0):
   - If non-zero (flag is set): write 0x01 to 0xB580
   - Else: write 0x00 to 0xB580
3. Return

**Draft C:**
```c
void getAutoTransCal(void) {
  u8 atCalEnable = readMemory8(0x000749B0);
  u8 output = (atCalEnable != 0) ? 1 : 0;
  writeMemory8(0xB580, output);
}
```

**Confidence:** high
- Simple conditional flag check and write
- No branches, no calls
- Automatic transmission (auto trans) purpose inferred from function name
- Logic is straightforward: copy flag to output register (inverted logic: any non-zero flag → 1)

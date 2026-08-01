# somethingFuelCutRelated @ 0xF964
_source: AI (Haiku) draft, unverified_

**Purpose:** Apply per-rotor fuel cut command based on getFuelCutRequestStatus result and rotor-specific bit mask testing.

**Inputs:**
- r4: rotor index (0-2 for 3 rotors)
- fr4: fuel cut duty cycle or threshold value (float)
- Globals:
  - 0xFF08 (getFuelCutRequestStatus): returns rotor fuel cut status word
  - 0x4BD74: rotor fuel cut bit mask table (3 entries)
  - 0x4BDC0/0x4BDC6: per-rotor fuel cut command/state arrays

**Outputs / side effects:**
- 0x4BDC0-0x4BDC2: rotor fuel cut values written
- Calls thunk_FUN_00008b4c (0x84C2) per rotor if fuel cut condition met

**Calls:**
- 0xFF08 (getFuelCutRequestStatus): fetch global rotor fuel cut status bits
- 0x84C2 (thunk to rotor-specific fuel cut logic): apply fuel cut per rotor

**Behavior:**
1. Save registers (r14-r9) and allocate 8 bytes stack space
2. Store input rotor index (r4) at r15 (stack)
3. Call getFuelCutRequestStatus() → r0 (status word)
4. Load constant 0.25 → fr3
5. Store fr4 (fuel cut level) at r15+4
6. Divide fr4 / 0.25 → fr2 (scale fuel cut value)
7. Convert to int: ftrc fr2, fpul → r10 (scaled threshold)
8. Zero-extend status word (r4) and rotor index
9. Load rotor bit masks from 0x4BD74 indexed by rotor (shift left by 1 to get word offset)
10. Test: if (status & rotor_mask) != 0: loop through 3 rotors
11. For each rotor where bit is set:
    - Check if 0x4BDC6[rotor] == 1 (fuel cut enabled)
    - If yes: call 0x84C2 with rotor bit mask from 0x4BDC0[rotor]
12. Increment rotor counter, continue until all 3 rotors checked
13. Restore registers and return

**Draft C:**
```c
void somethingFuelCutRelated(uint8_t rotor_idx, float fuel_cut_level) {
  uint16_t status = getFuelCutRequestStatus();
  
  // Scale fuel cut duty cycle
  float scaled = fuel_cut_level / 0.25f;
  uint32_t threshold = (uint32_t)scaled;
  
  // Load per-rotor bit masks
  uint16_t *rotor_masks = (uint16_t *)0x4BD74;
  uint8_t *fuel_cut_enabled = (uint8_t *)0x4BDC6;
  uint8_t *fuel_cut_cmds = (uint8_t *)0x4BDC0;
  
  // Check each rotor
  for (int i = 0; i < 3; i++) {
    uint16_t mask = rotor_masks[i];
    
    if ((status & mask) != 0) {
      // Fuel cut requested for this rotor
      if (fuel_cut_enabled[i] == 1) {
        // Apply fuel cut command
        apply_rotor_fuel_cut(fuel_cut_cmds[i], threshold);  // 0x84C2
      }
    }
  }
}
```

**Confidence:** med
- Overall flow is clear: fetch status → scale threshold → per-rotor bit testing → conditional call
- Exact bit mask structure (16-bit words? bytes?) inferred from address spacing (0x4BD74 indexed)
- The 0x4BDC0 vs 0x4BDC6 distinction (command vs enable flag) not fully confirmed
- Rotor mask bit positions and meanings unclear without calibration data

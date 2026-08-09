# somethingFuelCutRelated @ 0xF964
**Purpose:** Apply the per-rotor fuel cut command. Base it on the getFuelCutRequestStatus result and the rotor-specific bit mask test.
**Inputs:** r4: rotor index (0-2 for 3 rotors) ; fr4: fuel cut duty cycle or threshold value (float) ; Globals: ; 0xFF08 (getFuelCutRequestStatus): returns the rotor fuel cut status word ; 0x4BD74: rotor fuel cut bit mask table (3 entries) ; 0x4BDC0/0x4BDC6: per-rotor fuel cut command/state arrays
**Out:** 0x4BDC0-0x4BDC2: rotor fuel cut values written ; Calls thunk_FUN_00008b4c (0x84C2) per rotor if the fuel cut condition is met
**Calls:** 0xFF08 (getFuelCutRequestStatus): fetch global rotor fuel cut status bits ; 0x84C2 (thunk to rotor-specific fuel cut logic): apply fuel cut per rotor
Save the registers (r14-r9) and allocate 8 bytes of stack space ; Store the input rotor index (r4) at r15 (stack) ; Call getFuelCutRequestStatus() → r0 (status word) ; Load constant 0.25 → fr3 ; Store fr4 (fuel
cut level) at r15+4 ; Divide fr4 / 0.25 → fr2 (scale the fuel cut value) ; Convert to int: ftrc fr2, fpul → r10 (scaled threshold) ; Zero-extend the status word (r4) and rotor index ; Load the rotor bit masks
from 0x4BD74 indexed by rotor (shift left by 1 to get the word offset) ; Test: if (status & rotor_mask) != 0: loop through 3 rotors ; For each rotor where the bit is set: ; Check if 0x4BDC6[rotor] == 1 (fuel
cut enabled) ; If yes: call 0x84C2 with the rotor bit mask from 0x4BDC0[rotor] ; Increment the rotor counter, continue until all 3 rotors are checked ; Restore the registers and return
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
**Status:** med — flow is clear (status → scale threshold → per-rotor bit test → conditional call). The mask width is inferred from address spacing. 0x4BDC0 vs 0x4BDC6 (command vs enable) is unconfirmed. The mask bit meanings need calibration data.

# eShaftLearn @ 0x284D6
**Purpose:** Manage eccentric shaft (e-shaft) position learning: read calibration state, conditionally load EEPROM data into RAM, and update adaptive trim values based on offset calculations.
**Inputs:** RAM 0xFFFFBA5F: e-shaft learning active flag (byte) ; RAM 0xC6B0: system condition/mode flag (byte) ; RAM 0xFFFFBA5E: e-shaft learn enable secondary flag (byte) ; RAM 0x8684: e-shaft reference/primary offset address (word in ROM/EEPROM) ; RAM 0x8682: e-shaft secondary offset address (word) ; RAM 0xFFFF8130: e-shaft state vector base address (float[]) ; RAM 0xFFFF8570: secondary state or coefficient (float) ; Calibration tables at 0x68678 (VE lookup), 0x68B5C (unknown)
**Out:** RAM 0xFFFF8130 (base) through related addresses: e-shaft learned offsets (floats) ; RAM 0x8684, 0x8682: primary and secondary offset registers (updated via updateMemoryAtAddress functions) ; Adaptive trim values stored back to EEPROM via E2 functions
**Calls:** readValue_8bit_ADDRESS_VAL @ 0x3E0DC (read byte from EEPROM/calibration) ; E2IntoRAM @ 0x383F8 (load EEPROM sector into RAM, r4=sector, r5=len) ; updateMemoryAtAddress_8bit_ADDR_VAL @ 0x3E1F8 (write byte to memory) ; updateMemoryAtAddress_float_VAL_ADDR @ 0x3E258 (write float to memory) ; getFromE2_E2ADDR_RAMADDR_LEN @ 0x38610 (read block from EEPROM into RAM) ; readValue @ calls for two-D lookups on calibration tables
Read learning-active flag (0xFFFFBA5F) ; If set: skip to step 3 ; Check secondary condition (0xFFFFBA5E): ; If not set: skip to step 4 ; Read mode condition (0xC6B0): ; If != 1: proceed to step 5 ;
Read reference offset from 0x8684 (readValue_8bit_ADDRESS_VAL) ; If zero: return without update ; Call E2IntoRAM to load EEPROM sector (r4=32, r5=68 bytes): ; Load e-shaft calibration block from
EEPROM into RAM ; Call updateMemoryAtAddress_8bit to update primary offset (0x8682, value=1) ; Initialize state vector loop: ; Set fr12 = 1.0 (multiplier initialization) ; Load base addresses for
state floats (0xFFFF8130 offset, 0xFFFF8570 coefficient) ; Load two calibration constants (-63.0, 0.5) ; Loop over state offsets (28 iterations or count from block): ; Read from EEPROM block
(getFromE2) ; Compute offset: offset = rawValue * multiplier + coefficient_scaling ; Call updateMemoryAtAddress_float to write learned trim ; Increment loop counter ; Finalize loop and return
**Draft C:**
```c
void eShaftLearn(void) {
  u8 learnActive = readMemory8(0xFFFFBA5F);
  if (!learnActive) {
    u8 learnEnable = readMemory8(0xFFFFBA5E);
    if (!learnEnable) {
      return;
    }
  }
  u8 modeFlag = readMemory8(0xC6B0);
  if (modeFlag != 1) {
    return;
  }
  u8 refOffset = readValue_8bit(0x8684);
  if (refOffset == 0) {
    return;
  }
  // Load EEPROM calibration block
  e2IntoRAM(32, 68);
  // Update primary offset
  updateMemoryAtAddress_8bit(0x8682, 1);
  // Initialize state learning vectors
  float multiplier = 1.0f;
  float baseAddr = 0xFFFF8130;
  float coeffAddr = 0xFFFF8570;
  float tau = -63.0f;    // Offset constant
  float scale = 0.5f;    // Scaling factor
  // Loop: read EEPROM block and compute learned e-shaft offsets
  for (int i = 0; i < 28; i++) {
    float rawValue = getFromE2_block(i);
    float learnedOffset = rawValue * multiplier + tau;
    updateMemoryAtAddress_float(baseAddr + i * 4, learnedOffset);
    if (refOffset >= threshold) {
      multiplier *= scale;
    }
  }
}
```
**Status:** med — purpose confirmed (adaptive e-shaft timing trim); EEPROM r/w sequence and 28-iteration loop inferred from calls; multiplier/scale logic and threshold conditions not fully reconstructed.

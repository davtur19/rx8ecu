# fuelinjectorSet0 @ 0x86AC
_source: AI (Haiku) draft, unverified_

**Purpose:** Set fuel injector output-compare value for one of three injectors based on mode selector.

**Inputs:**
- r4: mode/injector selector (0, 1, or 2)
- r5: value to write (likely pulse width or timer count)

**Outputs / side effects:**
- Writes r5 to one or two of the hardware injector output-compare registers:
  - Mode 0: 0xFFFFA0AC (+0 and +12)
  - Mode 1: 0xFFFFA0AC (+4 and +16)
  - Mode 2: 0xFFFFA0AC (+8 and +20)

**Calls:** None

**Behavior:**
1. Load base register 0xFFFFA0AC into r6 (likely injector output-compare timer base)
2. Check if r4 == 0: if yes, write r5 to r6[0] and r6[12]
3. Check if r4 == 1: if yes, write r5 to r6[4] and r6[16]
4. Check if r4 == 2: if yes, write r5 to r6[8] and r6[20]
5. Return

**Draft C:**
```c
void fuelinjectorSet0(uint8_t mode, uint32_t value) {
    volatile uint32_t *ocr_base = (volatile uint32_t *)0xFFFFA0AC;
    
    if (mode == 0) {
        ocr_base[0] = value;
        ocr_base[3] = value;  // +12 bytes = +3 words
    } else if (mode == 1) {
        ocr_base[1] = value;  // +4 bytes = +1 word
        ocr_base[4] = value;  // +16 bytes = +4 words
    } else if (mode == 2) {
        ocr_base[2] = value;  // +8 bytes = +2 words
        ocr_base[5] = value;  // +20 bytes = +5 words
    }
}
```

**Confidence:** high — logic is straightforward, register writes are direct.

**Uncertainties:**
- Whether the three injectors are truly independent or represent leading/trailing per rotor
- Exact hardware mapping of 0xFFFFA0AC register bank

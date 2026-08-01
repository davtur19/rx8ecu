# readADCs_coolantTempInHere @ 0x6CDC

_source: AI (Haiku) draft, unverified_

**Purpose:** Read ADC values from hardware; demultiplex 8 analog channels into global RAM array based on ADC state register.

**Inputs:** None (reads hardware ADC directly)

**Outputs / side effects:**
- Writes 16-bit ADC values to RAM array starting at ~0xFFFF9EE4 (8 values, 2 bytes each)
- Reads ADC control register at 0xFFFF9F2F to determine which channel set (1, 4, or 8 channels)
- Return: None

**Calls:**
- (none - direct hardware access)

**Behavior:**
1. Read ADC control register at offset +2 from base (0xFFFF9F2F)
2. If value is 0 or negative, return immediately
3. Switch on ADC control value:
   - Case 8: Read 8 ADC channels from hardware (0xF84E, 0xF84C, 0xF848, 0xF846, 0xF844, 0xF840) and store to RAM offsets +62, +60, +58, +56, +54, +52, +50, +48
   - Case 4: Read 4 ADC channels
   - Case 1: Read 1 ADC channel
4. Write all ADC data to RAM array

**Draft C:**
```c
void readADCs_coolantTempInHere(void) {
  u8 ctrl = *(u8*)(0xFFFF9F2F + 2);
  if (ctrl <= 0) return;
  
  u8* ram_base = (u8*)0xFFFF9EE4;
  
  switch(ctrl) {
    case 8:
      // Read 8 ADC channels from hardware
      *(u16*)(ram_base + 62) = *(u16*)0xF84E;  // ADC ch 0
      *(u16*)(ram_base + 60) = *(u16*)0xF84C;  // ADC ch 1
      *(u16*)(ram_base + 58) = *(u16*)0xF84A;  // ADC ch 2
      *(u16*)(ram_base + 56) = *(u16*)0xF848;  // ADC ch 3
      *(u16*)(ram_base + 54) = *(u16*)0xF846;  // ADC ch 4
      *(u16*)(ram_base + 52) = *(u16*)0xF844;  // ADC ch 5
      *(u16*)(ram_base + 50) = *(u16*)0xF842;  // ADC ch 6
      *(u16*)(ram_base + 48) = *(u16*)0xF840;  // ADC ch 7
      break;
    case 4:
      // Read 4 ADC channels
      break;
    case 1:
      // Read 1 ADC channel
      break;
  }
}
```

**Confidence:** med — the structure is clear (switch on mode, read hardware, write to RAM) but the exact hardware register layout and meaning of control values require verification.

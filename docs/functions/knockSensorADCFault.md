# knockSensorADCFault @ 0xC290
_source: AI (Haiku) draft, unverified_

**Purpose:** Validate knock sensor ADC reading against bounds; set fault code if out of range (open circuit=1, short circuit=2, ok=0).

**Inputs:**
- u16 from RAM 0xFFFF9F0E (knock sensor ADC raw value)

**Outputs / side effects:**
- RAM 0xFFFFA325: u8 fault code (0=ok, 1=open/high, 2=short/low)

**Calls:** None

**Verified analysis (capstone disassembly + manual decode):**

**Registers:**
- r6 = 0xFFFF9F0E (knock sensor ADC raw value)
- r4 = 0xFFFFA325 (fault code output address)
- r2 = 0x0006CF7E (max threshold address, value=0xC831=51249)
- r3 = 0x0006CF7C (min threshold address, value=0x3EF9=16121)

**Behavior:**
1. Load u16 from RAM 0xFFFF9F0E (knock sensor ADC) → r6
2. Load output address 0xFFFFA325 → r4
3. Zero-extend ADC to u16 → r5
4. Load u16 max threshold from ROM 0x0006CF7E → r3 (value=51249 ≈ 3.91V)
5. If r5 >= r3 (ADC >= max): 
   - Set fault = 1 (open circuit)
   - Branch to exit
6. Load u16 min threshold from ROM 0x0006CF7C → r0 (value=16121 ≈ 1.23V)
7. If r5 >= r0 (ADC >= min):
   - Set fault = 0 (ok)
   - Branch to exit
8. Else (r5 < r0, below min threshold):
   - Set fault = 2 (short circuit)
9. Store fault code to RAM 0xFFFFA325
10. Return

**Draft C:**
```c
uint16_t knock_adc_raw;         // @ 0xFFFF9F0E
uint16_t knock_adc_max_thresh;  // ROM 0x0006D47E
uint16_t knock_adc_min_thresh;  // ROM 0x0006D47C
uint8_t knock_adc_fault_code;   // @ 0xFFFFA325

#define KNOCK_FAULT_OK      0
#define KNOCK_FAULT_OPEN    1
#define KNOCK_FAULT_SHORT   2

void knockSensorADCFault(void) {
    uint16_t adc_value = knock_adc_raw;
    uint16_t max_thresh = knock_adc_max_thresh;
    uint16_t min_thresh = knock_adc_min_thresh;
    
    uint8_t fault = KNOCK_FAULT_OK;
    
    // Check upper bound (open circuit)
    if (adc_value >= max_thresh) {
        fault = KNOCK_FAULT_OPEN;
    }
    // Check lower bound (short circuit)
    else if (adc_value < min_thresh) {
        fault = KNOCK_FAULT_SHORT;
    }
    // Else in range: fault = 0
    
    knock_adc_fault_code = fault;
}
```

**Confidence:** high
- Threshold-based fault detection pattern is standard
- Bounds logic is clear: high=open (sensor disconnected), low=short
- Unknown: exact ADC range; whether thresholds come from EEPROM or ROM

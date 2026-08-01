# knockFunctionInit @ 0xC14C
_source: AI (Haiku) draft, unverified_

**Purpose:** Initialize knock detection subsystem: call sub-initializers, set up ADC configuration, zero fault counters.

**Inputs:** None explicit

**Outputs / side effects:**
- Calls two initialization sub-functions
- RAM 0xFFFFA37A: u16 config = 0x0000AC08
- RAM 0xFFFFA378: u16 config = 0x0000AC08
- RAM 0xFFFFA374: f32 constant = 44040.0
- RAM 0xFFFFA38C: u8 = 0 (fault counter)
- RAM 0xFFFFA325: u8 = 0 (fault counter)

**Calls:**
- 0xC176 (unnamed sub-init, likely ADC or sensor setup)
- 0xC1F8 (knockRelatedInit): full knock initialization

**Behavior:**
1. Push return address (pr) to stack
2. Call sub-init @ 0xC176
3. Call knockRelatedInit @ 0xC1F8 (full knock system setup)
4. Load config constant 0x0000AC08 into r4
5. Store r4 to RAM 0xFFFFA37A (ADC config 1)
6. Store r4 to RAM 0xFFFFA378 (ADC config 2)
7. Load constant f32 44040.0 (mova) from ROM
8. Store f32 to RAM 0xFFFFA374 (likely threshold or gain)
9. Zero r4
10. Store r4=0 to RAM 0xFFFFA38C (fault counter 1)
11. Restore return address and return, zero-ing r4 at exit to RAM 0xFFFFA325 (fault counter 2)

**Draft C:**
```c
uint16_t knock_adc_config_a;    // @ 0xFFFFA37A
uint16_t knock_adc_config_b;    // @ 0xFFFFA378
float knock_threshold;          // @ 0xFFFFA374
uint8_t knock_fault_count_a;    // @ 0xFFFFA38C
uint8_t knock_fault_count_b;    // @ 0xFFFFA325

void knockFunctionInit(void) {
    // Call sub-initializers
    sensor_setup();          // @ 0xC176
    knockRelatedInit();      // @ 0xC1F8
    
    // Configure ADC
    uint16_t adc_config = 0x0000AC08;
    knock_adc_config_a = adc_config;
    knock_adc_config_b = adc_config;
    
    // Set threshold/gain constant
    knock_threshold = 44040.0f;
    
    // Reset fault counters
    knock_fault_count_a = 0;
    knock_fault_count_b = 0;
}
```

**Confidence:** med
- Call sequence and zero-initialization pattern are clear
- Config value 0x0000AC08 and threshold 44040.0 are explicit
- Unknown: exact meaning of the two redundant config locations; sub-init @ 0xC176 purpose; whether fault counters are per-rotor

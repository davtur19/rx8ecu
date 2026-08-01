# injectorPulseSet @ 0x8A68
_source: AI (Haiku) draft, unverified_

**Purpose:** Compute and set fuel injector pulse width from timing and calibration data; write to hardware output-compare register.

**Inputs:**
- r4: injector selector (0–2)
- State/globals:
  - 0xFFFFA004 (injector config array, 32 bytes per entry)
  - 0xFFFFA094 (injector calibration map, 32 bytes per inj)
  - 0xF440 (hardware timer counter, read-only)

**Outputs / side effects:**
- Computes pulse width: (calibration_value + hw_counter - 3) >> 4
- Writes computed pulse width to hardware output-compare register (0xF440 or similar)
- Clears state byte at offset +18 and +20
- Calls setSR_PARAM/loadStatusRegister to manage interrupt masking

**Calls:**
- setSR_PARAM @ 0x2054: disable interrupts for critical section
- FUN_0000A8A4 @ 0xA8A4: unknown utility, likely register or interrupt operation
- loadStatusRegister @ 0x2064: restore interrupt mask

**Behavior:**
1. Save/mask status register (disable interrupts)
2. Compute state offset: (injector_id * 24 * 4) into 0xFFFFA004
3. Load calibration offset from state[+12]
4. Read injector calibration from 0xFFFFA094 + (injector_id * 32)
5. Compute pulse width:
   - hw_counter = read 0xF440 (current timer value)
   - pulse = (calibration + hw_counter - 3) >> 4 (divide by 16)
6. Check if result width >= 0x8000 (32K): if yes, write to state[+16]
7. Read injector enable bits from 0xF66C (hardware register)
8. Write computed pulse to output-compare hardware register
9. Clear state bytes at +18 and +20
10. Restore status register (re-enable interrupts)

**Draft C:**
```c
void injectorPulseSet(uint8_t injector_id) {
    volatile uint32_t *state_base = (volatile uint32_t *)0xFFFFA004;
    volatile uint32_t *calib_base = (volatile uint32_t *)0xFFFFA094;
    
    uint32_t sr = getSR();
    setSR_PARAM(sp, sr | 0x00F0);  // mask IRQs
    
    volatile uint32_t *state = state_base + injector_id * 8;
    volatile uint32_t *calib = calib_base + injector_id * 8;
    
    uint32_t calib_value = *(calib + 3);  // +12 offset
    uint16_t hw_counter = *(volatile uint16_t *)0xF440;
    int32_t pulse_width = (calib_value + hw_counter - 3) >> 4;
    
    if ((uint32_t)pulse_width >= 0x8000) {
        *(uint16_t *)((uintptr_t)state + 16) = pulse_width;
    }
    
    uint16_t hw_en_bits = *(volatile uint16_t *)0xF66C;
    *(volatile uint16_t *)0xF440 = pulse_width;
    
    *(uint8_t *)((uintptr_t)state + 18) = 0;
    *(uint8_t *)((uintptr_t)state + 20) = 0;
    
    loadStatusRegister(sp, sr);  // restore IRQs
}
```

**Confidence:** med — pulse computation is clear; exact timing/latch semantics and hardware register mapping need verification.

**Uncertainties:**
- Why pulse is right-shifted by 4 (possibly fixed-point to timer clock conversion)
- Whether 0x8000 threshold has special meaning (overflow? dual-injector mode?)
- Exact hardware register mapping for injector timer channels
- Why two state bytes are cleared; whether they represent completion flags

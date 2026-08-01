# putFuelingStuffInArray @ 0x85E4
_source: AI (Haiku) draft, unverified_

**Purpose:** Conditionally set fuel injector pulse width in a per-chamber (rotor) state array based on enable flag; write to hardware injector I/O.

**Inputs:**
- r4: rotor index / chamber index (code iterates per-chamber entries 0–2; the RX-8 itself has 2 rotors)
- RAM globals: 0xFFFFA004 (per-chamber state array), 0xFFFFA094 (injector config), 0x0000D7D4 (injector calibration)

**Outputs / side effects:**
- Writes pulse width (16-bit) to state array at offset +4 or +8 (depends on injector type)
- Writes to hardware registers 0xF440 and 0xF66C (likely fuel injector output-compare timers)
- Clears enable flag at state[+19] after setting pulse

**Calls:**
- setSR_PARAM @ 0x2054: disable interrupts for critical section
- FUN_0000A8A4 @ 0xA8A4: unknown utility, likely register write
- loadStatusRegister @ 0x2064: restore interrupt mask

**Behavior:**
1. Compute state array offset as (chamber_id * 32) bytes into base 0xFFFFA004
2. Check enable flag at offset +19
3. If disabled: skip to end, write 0 to enable flag
4. If enabled:
   - Save and mask status register (disable interrupts)
   - Load injector config from 0xD7D4 + (id * 24)
   - Check injector type byte at config+20
     - Type 1: write pulse to state[+4] and state[+16]
     - Type 2: write pulse to state[+8] and state[+20]
   - Read hardware reg 0xF440, write result to 0xF66C (or masked write depending on type)
   - Restore status register (re-enable interrupts)
5. Clear enable flag at state[+19]

**Draft C:**
```c
void putFuelingStuffInArray(uint8_t cyl_id) {
    uint32_t *state_base = (uint32_t *)0xFFFFA004;
    uint32_t *state = state_base + cyl_id * 8;  // 32 bytes per chamber entry
    
    if (!*(uint8_t *)((uintptr_t)state + 19)) {
        *(uint8_t *)((uintptr_t)state + 19) = 0;
        return;
    }
    
    uint32_t sr = getSR();
    setSR_PARAM(sp, sr | 0x00F0);  // mask IRQs
    
    uint32_t *config = (uint32_t *)(0xD7D4 + cyl_id * 24);
    uint16_t pulse_width = *(uint16_t *)config;
    uint8_t inj_type = *(uint8_t *)((uintptr_t)config + 20);
    
    if (inj_type == 1) {
        *(uint16_t *)((uintptr_t)state + 4) = pulse_width;
        *(uint16_t *)((uintptr_t)state + 16) = pulse_width;
    } else if (inj_type == 2) {
        *(uint16_t *)((uintptr_t)state + 8) = pulse_width;
        *(uint16_t *)((uintptr_t)state + 20) = pulse_width;
    }
    
    uint16_t hw_val = *(uint16_t *)0xF440;
    *(uint16_t *)0xF66C = hw_val;
    
    loadStatusRegister(sp, sr);  // restore IRQs
    *(uint8_t *)((uintptr_t)state + 19) = 0;
}
```

**Confidence:** med — overall structure is clear; exact injector type semantics and hardware register mapping need verification.

**Uncertainties:**
- Exact function of injector type values
- Whether 0xF440/0xF66C are independent timer registers or a shared control/status pair
- Whether pulse_width is raw value or needs scaling/conversion

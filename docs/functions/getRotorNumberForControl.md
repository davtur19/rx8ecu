# getRotorNumberForControl @ 0xA266
_source: AI (Haiku) draft, unverified_

**Purpose:** Select and return the next rotor index for the rotary engine (13B 2-rotor), cycling between rotors 0 and 1.

**Inputs:**
- r4: parameter or rotor base index

**Outputs / side effects:**
- r0: selected rotor index (value from table)
- Rotor counter at RAM+9 bytes offset: incremented each call, wraps at 2

**Calls:** None

**Behavior:**
1. Compute offset into rotor control table at 0xFFFFA170:
   - offset = (r4 << 1) + r4 = r4 * 3
   - offset <<= 2 → r4 * 12 (12-byte per rotor record)
2. Load rotor counter from offset+9 in table
3. Index into rotor data: load 4-byte value from table[counter] (0, 4, 8 bytes offset depending on counter)
4. Increment rotor counter at offset+9
5. If counter >= 2, wrap to 0 and update table
6. Return rotor index value from step 3

**Draft C:**
```c
typedef struct {
  uint32_t rotor_data[3];  // 3 * 4-byte entries
  uint8_t rotor_counter;   // Offset +12 (or +9 from base?)
} RotorControl;

uint32_t getRotorNumberForControl(uint8_t rotor_param) {
  RotorControl* rotor_table = (RotorControl*)0xFFFFA170;
  RotorControl* entry = &rotor_table[rotor_param];
  
  uint8_t counter = entry->rotor_counter;
  uint32_t selected_rotor = entry->rotor_data[counter];
  
  counter++;
  if (counter >= 2) {
    counter = 0;
  }
  entry->rotor_counter = counter;
  
  return selected_rotor;
}
```

**Confidence:** med – rotor selection and cycling logic clear (2-rotor RX-8 engine); exact table structure and data interpretation uncertain; equinox name confirms 2-rotor purpose

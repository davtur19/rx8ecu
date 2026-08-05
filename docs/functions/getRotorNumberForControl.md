# getRotorNumberForControl @ 0xA266

**Purpose:** Select and return the next rotor index for the rotary engine (13B 2-rotor), cycling between rotors 0 and 1.
In: r4: parameter or rotor base index  Out: r0: selected rotor index (value from table) ; Rotor counter at RAM+9 bytes offset: incremented each call, wraps at 2  Behavior: Compute offset into rotor control table at 0xFFFFA170: ; offset = (r4 << 1) + r4 = r4 * 3 ; offset <<= 2 → r4 * 12 (12-byte per rotor record) ; Load rotor counter from offset+9 in table ; Index into rotor data: load 4-byte value from table[counter] (0, 4, 8 bytes offset depending on counter) ; Increment rotor counter at offset+9 ; If counter >= 2, wrap to 0 and update table ; Return rotor index value from step 3
**Status:** med – rotor selection and cycling logic clear (2-rotor RX-8 engine); exact table structure and data interpretation uncertain; equinox name confirms 2-rotor purpose

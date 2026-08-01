# readValue_32bit_ADDRESS_VAL @ 0x3E15C
_source: AI (Haiku) draft, unverified_

**Purpose:** Read a 32-bit value stored with redundancy/checksum (ADDRESS_VAL format); validate against complement; return original value if valid.

**Inputs:**
- r4: pointer to ADDRESS_VAL struct (6 bytes: value + inverted complement + extra validation)
  - @+0,2: two 16-bit words (high and low of 32-bit value?)
  - @+2,2: inverted/complement (NOT of value)
  - @+4,2: validation mirror or extra complement word

**Outputs / side effects:**
- r13 (return): 32-bit value if valid, or 0xFFFFFFFF if validation fails
- r0: r13 (copy of return value)
- Call to `setMemInsideFUNCto1` (0x0003E3F0) if validation fails (marks error state)
- SR saved/restored; interrupts disabled during read

**Calls:**
1. `getSR` (0x00003920) – save SR, disable interrupts (arg r4=0x0010)
2. `setMemInsideFUNCto1` (0x0003E3F0) – called if validation fails
3. `setSR` (0x00003934) – restore SR, re-enable interrupts

**Behavior:**
1. Save SR, disable interrupts (0x0010 mask – minimal interrupt blocking)
2. Store r5 argument in local (likely buffer pointer for output)
3. Load two 16-bit words from @r4 and @r4+2
4. Compute NOT(r0) of second word (inverted complement)
5. Load first word into r8
6. Compare r8 (high word) against NOT(second word):
   - If equal: jump to success path, set r13 = @r4 (original 32-bit value)
7. Else (validation failed):
   - Load third word @r4+4 from r0, compare against complement
   - If third word matches NOT(value): jump to success
8. If all fail: call setMemInsideFUNCto1(buffer), set r13=1 (error marker)
9. Restore SR, return r0 = r13

_Note: Denso redundant memory format stores value twice (original + inverted) for EEPROM/RAM wear leveling._

**Confidence:** med – redundancy scheme matches Denso patterns; exact struct layout inferred from offsets.

**Uncertainties:**
- exact ADDRESS_VAL struct size and field layout (6 or 8 bytes?)
- what @+0 vs @+2 vs @+4 actually represent
- whether r13 value should be returned or validated value placed in buffer
- error handling: does setMemInsideFUNCto1 throw or just set flag?

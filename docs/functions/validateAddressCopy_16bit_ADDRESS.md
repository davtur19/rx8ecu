# validateAddressCopy_16bit_ADDRESS @ 0x3E2DA
**Purpose:** Validate a 16-bit redundant memory cell (ADDRESS_VAL format); check that stored value matches its inverted complement.
**Inputs:** r4: pointer to 16-bit redundant memory cell (4 bytes: value + inverted complement) ; @+0: 16-bit value ; @+2: 16-bit complement (NOT of value)
**Out:** r0: 0 if validation passes (value == NOT(complement)), 1 if fails ; Call to `SetMemoryNotValid2` (0x0003E5A8) if validation fails (marks cell as corrupt) ; SR saved/restored; interrupts disabled during read
**Calls:** `getSR` (0x00003920) – save SR, disable interrupts (arg r4=0x0010) ; `SetMemoryNotValid2` (0x0003E5A8) – called if validation fails ; `setSR` (0x00003934) – restore SR, re-enable interrupts
Save SR, disable interrupts ; Store r4 (cell pointer) in local ; Load 16-bit value from @r4 into r2, zero-extend (extu.w r2,r2) ; Load complement from @r4+2 into r0, compute NOT(r0), zero-extend ;
Compare r2 (value) == NOT(complement): ; If equal: set r14=0 (success) and branch to restore ; Else (mismatch): ; Call SetMemoryNotValid2(cell_ptr) – mark cell as invalid ; Set r14=1 (validation
failed) ; Restore SR, return r0 = r14 ; _Note: 16-bit variant of readValue_32bit_ADDRESS_VAL; simpler 4-byte struct._
**Draft C:**
```c
uint8_t validateAddressCopy_16bit(struct ADDRESS_VAL_16 *cell) {
  uint16_t value = (uint16_t)cell->value;
  uint16_t complement = (uint16_t)cell->complement;
  if (value == (uint16_t)~complement) {
    return 0;  // valid
  }
  SetMemoryNotValid2(cell);
  return 1;   // invalid
}
```
**Status:** high – validation logic is straightforward; matches 32-bit variant pattern.
**Uncertainties:** exact struct size (4 or 6 bytes? assume 4) ; whether both words are checked (code shows only 2-byte check, not 4) ; whether SetMemoryNotValid2 is fatal or just flags for later handling

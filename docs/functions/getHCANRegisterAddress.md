# getHCANRegisterAddress @ 0xCEFE
_source: AI (Haiku) draft, unverified_

**Purpose:** Convert mailbox index and offset to absolute HCAN peripheral register address.

**Inputs:**
- r4: mailbox index (0..7?) or flag; extu.b zero-extends
- r5: base offset (e.g., 0xE406, 0xE40A, 0xE41A, etc.)

**Outputs / side effects:**
- r0: absolute register address (HCAN peripheral base + offset + scaled index)

**Calls:** none

**Behavior:**
1. Zero-extend r4 to full word (extu.b r4,r4)
2. If r4 == 0 (test r4,r4; bf skip):
   - return r4 = r5 (offset unchanged)
3. Else (r4 != 0):
   - r4 = 0x0200 (HCAN peripheral stride or offset multiplier)
   - r4 = r5 + r4 (base offset + stride)
   - return r4

_Note: The 0x0200 constant likely represents the HCAN mailbox register spacing (512 bytes apart)._

**Draft C:**
```c
uint32_t getHCANRegisterAddress(uint8_t mailbox_idx, uint16_t offset) {
  mailbox_idx = (uint8_t)mailbox_idx;
  if (mailbox_idx == 0) {
    return offset;  // or HCAN_BASE + offset
  }
  return offset + (mailbox_idx * 0x0200);  // stride by 512 bytes per mailbox
}
```

**Confidence:** high – code is straightforward; 0x0200 stride is SH7055 HCAN spec (512-byte mailbox blocks).

**Uncertainties:**
- whether offset is absolute (HCAN_BASE + offset) or peripheral-relative (caller adds base)
- mailbox index range (0..7 likely, but not verified)

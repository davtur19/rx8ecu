# getHCANRegisterAddress @ 0xCEFE

**Purpose:** Convert mailbox index and offset to absolute HCAN peripheral register address.
In: r4: mailbox index (0..7?) or flag; extu.b zero-extends ; r5: base offset (for example, 0xE406, 0xE40A, 0xE41A)  Out: r0: absolute register address (HCAN peripheral base + offset + scaled index)  Behavior: Zero-extend r4 to full word (extu.b r4,r4) ; If r4 == 0 (test r4,r4; bf skip): ; return r4 = r5 (offset unchanged) ; Else (r4 != 0): ; r4 = 0x0200 (HCAN peripheral stride or offset multiplier) ; r4 = r5 + r4 (base offset + stride) ; return r4 ; _Note: The 0x0200 constant likely represents the HCAN mailbox register spacing (512 bytes apart)._
**Status:** high – code is straightforward; 0x0200 stride is SH7055 HCAN spec (512-byte mailbox blocks). ; whether offset is absolute (HCAN_BASE + offset) or peripheral-relative (caller adds base) ; mailbox index range (0..7 likely, but not verified)

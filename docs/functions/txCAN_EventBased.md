# txCAN_EventBased @ 0x99B0
_source: AI (Haiku) draft, unverified_

**Purpose:** Queue and transmit a CAN frame from a prepared message structure, with interrupt-safe register manipulation.

**Inputs:**
- r4: pointer to CAN message struct (frame ID, flags, data, DLC)
  - byte @+5: mailbox selector (0..7?)
  - byte @+6: DLC (data length)
  - longword @+8: pointer to data buffer (8 bytes)

**Outputs / side effects:**
- r0: 1 if transmission successful, 0 if mailbox busy
- HCAN registers written via setRegister_REG_BIT_VAL (0x0000CCDA)
- SR (status register) saved and restored; interrupts disabled during CAN register access

**Calls:**
1. `getSR` (0x00003920) – save current SR, disable interrupts (arg r4=0x0090)
2. `getHCANRegisterAddress` (0x0000CEE8 or 0x0000CF12) – resolve mailbox base address from index
3. `setRegister_REG_BIT_VAL` (0x0000CCDA) – write DLC, CAN ID, control bits, then data
4. `setSR` (0x00003934) – restore SR, re-enable interrupts

**Behavior:**
1. Save SR, disable interrupts (0x0090 mask)
2. Read mailbox selector from message byte +5, get mailbox register base address
3. Check if mailbox ready (CAN status register read):
   - Mask with read from mailbox; test vs expected flag pattern (0xE406 or 0xE40A)
   - If NOT ready (bf branch taken), set r14=1 (error) and skip to restore
4. If ready:
   - Write DLC to mailbox+0x0A offset (flags register)
   - Call setRegister 3 times to write: ID, then data, then final control
   - Load data pointer from message @+8, pass r6=0 (length multiplier?), r7=data_ptr
   - Set r14=0 (success)
5. Restore SR, return r0 = r14

**Confidence:** med – mailbox addressing logic and return semantics inferred; setRegister behavior unverified.

**Uncertainties:**
- exact struct layout of CAN_Message
- what "ready" flag pattern (0xE406 vs 0xE40A) signifies
- whether r0 return (1=fail, 0=success) or inverted

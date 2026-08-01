# placeCANRX @ 0x9890
_source: AI (Haiku) draft, unverified_

**Purpose:** Process a received CAN frame and place it into a message queue or buffer; validates mailbox readiness before reading RX data.

**Inputs:**
- r4: pointer to CAN RX message struct (similar layout to txCAN_EventBased)
  - byte @+5: mailbox selector (0..7?)
  - byte @+6: unused/DLC placeholder
  - longword @+8: pointer to receive buffer (8 bytes)

**Outputs / side effects:**
- r0: 1 if frame placed successfully, 0 if mailbox not ready or RX pending
- Data buffer at msg->@+8 filled with 8 bytes of CAN frame data
- HCAN mailbox registers read via getHCANRegisterAddress calls
- SR saved/restored; interrupts disabled during register access

**Calls:**
1. `getSR` (0x00003920) – save SR, disable interrupts (arg r4=0x0090)
2. `getHCANRegisterAddress` (0x0000CF12, 0x0000CEE8) – resolve mailbox register address
3. `setRegister_REG_BIT_VAL` (0x0000CCA4) – write data to receive buffer (or ack RX mailbox)
4. `setSR` (0x00003934) – restore SR, re-enable interrupts

**Behavior:**
1. Save SR, disable interrupts
2. Read mailbox selector from message byte +5
3. Check mailbox RX status (flag 0xE40E):
   - Get mailbox register address; read two status words
   - AND them together; test against expected "ready for RX" pattern
   - If NOT ready (movt/xor/cmp logic inverts result), set r0=0 and skip to restore
4. If ready:
   - Read CAN frame ID and store to some temp
   - Get mailbox register address (0xE41A offset?)
   - Read data buffer (8 bytes) from mailbox
   - Call setRegister 3 times with r6=2 (data word count?), r7=receive_buffer_ptr
   - Set r0=1 (success)
5. Restore SR, return r0

**Confidence:** med – mailbox status flags and data extraction order inferred; whether buffer is filled or queued unclear.

**Uncertainties:**
- exact flag pattern for "RX ready" (0xE40E) vs "RX pending" (0xE41A)
- whether r6=2 means 2 words or some other multiplier
- queue vs inline buffer behavior
- whether return value indicates frame placed or queue ready

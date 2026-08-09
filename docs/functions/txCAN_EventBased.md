# txCAN_EventBased @ 0x99B0
**Purpose:** Queue and transmit a CAN frame from a prepared message structure, with interrupt-safe register manipulation.
**Inputs:** r4: pointer to the CAN message struct (frame ID, flags, data, DLC) ; byte @+5: mailbox selector (0..7?) ; byte @+6: DLC (data length) ; longword @+8: pointer to data buffer (8 bytes)
**Out:** r0: 1 if the transmission is successful, 0 if the mailbox is busy ; HCAN registers written with setRegister_REG_BIT_VAL (0x0000CCDA) ; SR (status register) saved and restored; interrupts disabled during CAN register access
**Calls:** `getSR` (0x00003920) – save the current SR, disable interrupts (arg r4=0x0090) ; `getHCANRegisterAddress` (0x0000CEE8 or 0x0000CF12) – resolve the mailbox base address from the index ; `setRegister_REG_BIT_VAL` (0x0000CCDA) – write DLC, CAN ID, control bits, then data ; `setSR` (0x00003934) – restore SR, re-enable interrupts
Save SR, disable interrupts (0x0090 mask) ; Read the mailbox selector from the message byte +5, get the mailbox register base address ; Check if the mailbox is ready (CAN status register read): ; Mask with the read from the
mailbox; test against the expected flag pattern (0xE406 or 0xE40A) ; If NOT ready (bf branch taken), set r14=1 (error) and skip to restore ; If ready: ; Write DLC to the mailbox+0x0A offset (flags register) ; Call
setRegister 3 times to write: ID, then data, then the final control ; Load the data pointer from the message @+8, pass r6=0 (length multiplier?), r7=data_ptr ; Set r14=0 (success) ; Restore SR, return r0 = r14
**Status:** med – the mailbox addressing logic and return semantics are inferred; the setRegister behavior is unverified.
**Uncertainties:** the exact struct layout of CAN_Message ; what the "ready" flag pattern (0xE406 vs 0xE40A) signifies ; whether the r0 return is (1=fail, 0=success) or inverted

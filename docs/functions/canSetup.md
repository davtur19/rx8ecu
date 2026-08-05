# canSetup @ 0xD9F4
**Purpose:** Initialize CAN controller mailboxes for both TX and RX channels.
**Inputs:** None
**Out:** Flags at 0xFFFFA410, 0xFFFFA411: set on success/failure ; RAM counter at 0xFFFFA40E: tracks mailbox initialization attempts
**Calls:** CANControllerSetup @ 0x9744 (setup controller with parameters) ; canMessageSetup @ 0x2AC4C (setup individual mailbox)
Clear setup attempt counter at 0xFFFFA40E ; Loop (max 2 iterations based on r8=2): ; Check enable flag at 0xB580 ; If enabled, configure TX mailboxes (0x4BB14) with CANControllerSetup(r4=0,
r5=mailbox, r6=16) ; Otherwise configure RX mailboxes (0x4BC14) with CANControllerSetup(r4=0, r5=mailbox, r6=16) ; For each mailbox pair, call canMessageSetup(r4=0) ; Load second mailbox address,
repeat CANControllerSetup(r4=1) and canMessageSetup(r4=1) ; Accumulate errors in r11 ; Increment attempt counter if any error occurred ; If attempt counter >= 2, set success flag 0xFFFFA410=1 and
error flag 0xFFFFA411=0 ; Otherwise set flags to 0
**Draft C:**
```c
void canSetup(void) {
  uint8_t* counter = (uint8_t*)0xFFFFA40E;
  *counter = 0;
  uint8_t error_accumulator = 0;
  uint8_t* enable_flag = (uint8_t*)0xB580;
  for (int loop = 0; loop < 2; loop++) {
    uint8_t result = 0;
    if (*enable_flag == 1) {
      result |= CANControllerSetup(0, (uint32_t*)0x4BB14, 16);
      result |= canMessageSetup(0, (uint32_t*)0x4BB14);
      result |= CANControllerSetup(1, (uint32_t*)0x4BB14, 6);
      result |= canMessageSetup(1, (uint32_t*)0x4BB14);
    } else {
      result |= CANControllerSetup(0, (uint32_t*)0x4BC14, 16);
      result |= canMessageSetup(0, (uint32_t*)0x4BC14);
      result |= CANControllerSetup(1, (uint32_t*)0x4BC14, 6);
      result |= canMessageSetup(1, (uint32_t*)0x4BC14);
    }
    error_accumulator |= result;
    if (error_accumulator != 0) {
      (*counter)++;
    }
  }
  *(uint8_t*)0xFFFFA410 = (*counter >= 2) ? 1 : 0;
  *(uint8_t*)0xFFFFA411 = 0;
}
```
**Status:** med – CAN controller dual-channel setup pattern clear (TX/RX branches), mailbox iteration clear; exact error handling logic and magic addresses (0x4BB14, 0x4BC14) require verification

# setCANRegisters @ 0xCACC
**Purpose:** Configure CAN peripheral registers for a specific mailbox, selecting between two register banks (channel 0/1).
**Inputs:** r4: mailbox index (0-31 = channel 0, 32+ = channel 1) ; r5: register buffer address ; r6: register set size
**Out:** Calls initializeCANRegisters with computed register addresses
**Calls:** initializeCANRegisters @ 0x9D24 (apply register values)
Extract mailbox number from r4 (mask with 0x0F to get index 0-15) ; Branch based on mailbox < 32: ; Channel 0 (mailbox 0-15): ; Tx/Rx mailbox base: 0xE420 + (mailbox * 20) [offset=(mailbox & 0x0F) <<
3 + << 2] ; Alternate base: 0xE414 + offset ; Control base: 0xE4B0 + offset ; Channel 1 (mailbox 32+): ; Tx/Rx mailbox base: 0xE620 + (mailbox & 0x0F) * 20 ; Alternate base: 0xE614 + offset ; Control
base: 0xE6B0 + offset ; Push computed register addresses and input buffer to stack ; Call initializeCANRegisters(reg_addr1, reg_addr2, reg_addr3, buffer, size)
**Draft C:**
```c
void setCANRegisters(uint8_t mailbox, uint32_t* reg_buffer, uint8_t size) {
  uint8_t mailbox_num = mailbox & 0x0F;
  uint32_t offset = (mailbox_num << 2) << 1;  // mailbox_num * 8, then << 2
  uint32_t *addr1, *addr2, *addr3;
  if (mailbox < 32) {
    // Channel 0
    addr1 = (uint32_t*)(0xE420 + offset);
    addr2 = (uint32_t*)(0xE4B0 + offset - 28);
    addr3 = (uint32_t*)(0xE414 + offset);
  } else {
    // Channel 1
    addr1 = (uint32_t*)(0xE620 + offset);
    addr2 = (uint32_t*)(0xE6B0 + offset - 28);
    addr3 = (uint32_t*)(0xE614 + offset);
  }
  initializeCANRegisters(addr1, addr2, addr3, reg_buffer, size);
}
```
**Status:** med – mailbox selector and offset calculation clear; addresses within CAN peripheral area (0xE4xx, 0xE6xx expected for SH7055 HCAN); exact register semantics require Denso HCAN spec

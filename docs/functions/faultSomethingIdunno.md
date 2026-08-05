# faultSomethingIdunno @ 0x5FD40
**Purpose:** Process and count fault/DTC codes by severity level or classification.
**Inputs:** r4: severity level or filter parameter ; r5: (unknown) control/flag
**Out:** r0: count of matching DTCs
**Calls:** None (lookup tables only)
Initialize r6=0 (counter), r7=0 (loop index), r13=1, r9=21 (max DTC count?) ; Loop through 21 DTC slots (i=0 to 20): ; Load DTC entry from table at 0xFFFF8920 + offset ; Extract severity byte at
offset +6 ; Look up in table at 0xFFFFF87D0 for extended info ; Cross-reference two lookup tables (0x7C9FC, 0x7CA88) ; Check severity flags (0x01, 0x02, 0x80, 0xC0, 0xC1, 0xF0, 0x50, 0x70, 0x80-0xBF,
0x81-0xBF) ; If conditions match parameter r4, increment counter r6 ; Return r6
**Draft C:**
```c
uint8_t faultSomethingIdunno(uint8_t severity_filter, uint8_t control_flag) {
  uint8_t count = 0;
  uint16_t* dtc_table = (uint16_t*)0xFFFF8920;
  uint8_t* severity_table = (uint8_t*)0xFFFF87D0;
  for (int i = 0; i < 21; i++) {
    uint16_t dtc_entry = dtc_table[i * 16];  // offset 0 of 16-byte struct
    uint8_t severity = severity_table[i * 16 + 6];
    uint8_t type1 = *(uint8_t*)(0x7C9FC + (dtc_entry & 0xFF));
    uint8_t type2 = *(uint8_t*)(0x7CA88 + (dtc_entry & 0xFF));
    // Complex severity/type matching logic (multiple cases)
    if (/* severity matches filter */) {
      count++;
    }
  }
  return count;
}
```
**Status:** low – large complex switch logic over severity codes, exact matching criteria unclear; equinox name suggests fault processing

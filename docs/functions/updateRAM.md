# updateRAM?? @ 0x529AE

_source: AI (Haiku) draft, unverified_

**Purpose:** Increment a counter at one RAM location and write data to another, advancing a pointer.

**Inputs:**
- r4: destination address (data will be written, then incremented)
- r5: counter address (byte counter to increment)
- r6: data value to write

**Outputs / side effects:**
- Memory at r5: byte counter incremented
- Memory at r4: data value written, then r4 incremented
- r0: updated r4 (return value)

**Calls:** none

**Behavior:**
1. Read byte at r5 into r3
2. Increment r3 (add #1)
3. Write r3 back to r5
4. Write r6 to address r4
5. Increment r4 (add #1)
6. Return with r4 (rts, mov r4,r0 in delay slot)

**Draft C:**
```c
uint32_t updateRAM(volatile uint8_t* counter_addr, uint8_t* data_ptr, uint8_t data) {
  (*counter_addr)++;
  *data_ptr = data;
  return (uint32_t)(data_ptr + 1);
}
```

**Confidence:** high - clear counter increment and data write pattern; likely part of a ring buffer or log writer.

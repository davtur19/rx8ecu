# updateRAM?? @ 0x529AE

**Purpose:** Increment a counter at one RAM location and write data to another, advancing a pointer.
In: r4: destination address (data will be written, then incremented) ; r5: counter address (byte counter to increment) ; r6: data value to write  Out: Memory at r5: byte counter incremented ; Memory at r4: data value written, then r4 incremented ; r0: updated r4 (return value)  Behavior: Read the byte at r5 into r3 ; Increment r3 (add #1) ; Write r3 back to r5 ; Write r6 to address r4 ; Increment r4 (add #1) ; Return with r4 (rts, mov r4,r0 in the delay slot)
**Status:** high - clear counter increment and data write pattern; likely part of a ring buffer or log writer.

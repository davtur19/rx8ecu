# faultEnableStatus2 @ 0x5E2BC

**Purpose:** Check if a specific fault enable status flag is set for a given fault condition.
In: r4: Index into fault enable status table (0–N) ; r5: Bit mask to check against the retrieved byte  Out: r0: Boolean result (1 if bits in r5 are set in the retrieved value, 0 otherwise)  Behavior: Load table address 0x0007CB14 into r0 ; Zero-extend r5 to 8 bits (ensure upper bits clear) ; Zero-extend r4 to 16 bits ; Load byte from table at offset r4: `byte_value = ram[0x0007CB14 + r4]` ; Zero-extend loaded byte to 16 bits ; Perform bitwise AND: `result = byte_value & r5` ; Test result (tst r5, r3): Sets T flag if result != 0 ; Copy T flag to r4 with movt (T → r4) ; Move r4 to r0 as return value
**Status:** high ; Clear straightforward bit-check operation ; Table location and indexing unambiguous ; Uncertainties: semantic meaning of individual bits in the fault enable status byte

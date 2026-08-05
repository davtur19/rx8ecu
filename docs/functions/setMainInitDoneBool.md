# setMainInitDoneBool?? @ 0x9F0C

**Purpose:** Set initialization complete flag in system state.
In: r4: boolean value (typically 0 or 1, or 0xFF for done)  Out: Memory at 0xFFFFA16C: byte set to r4  Behavior: Load address 0xFFFFA16C into r2 ; Write r4 (byte) to r2
**Status:** high - trivial memory write; address 0xFFFFA16C is in RAM (0xFFFFxxxx space). Name strongly suggests initialization state flag.

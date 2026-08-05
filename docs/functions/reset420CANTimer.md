# reset420CANTimer @ 0x29584

**Purpose:** Reset the 420 Hz CAN timer counter to zero.
In: None (uses global state)  Out: Writes 0 to RAM location 0xFFFFBAEC (420 Hz CAN timer counter)  Behavior: Load address 0xFFFFBAEC into r2 ; Clear r3 to 0 ; Write r3 (0) to memory location in r2
**Status:** high — straightforward register write; function name confirms purpose. ; None

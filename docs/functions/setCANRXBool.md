# setCANRXBool @ 0xE044

**Purpose:** Signal that a CAN message was received by setting a flag.
Out: Flag at 0xA406: set to 1  Behavior: Load address 0xA406 ; Set value to 1
**Status:** high – trivial flag setter, address pattern consistent with other OBD/diagnostic flags

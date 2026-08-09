# setEngineLoadInitalVal @ 0x341DA

**Purpose:** Initialize the engine load value. Read it from the ROM calibration table and write it to the RAM working register.
In: Float calibration value from ROM 0x00078CE4  Out: Writes float value to RAM 0xC0D8 (engine load working value)  Calls: None (direct memory operations only)  Behavior: Load the float from calibration address 0x00078CE4 into fr3 ; Store it immediately to RAM address 0xC0D8
**Status:** high - Function is minimal; straight load-store operation. ; Whether this is called at startup or on demand ; The exact role of engine load in downstream calculations ; Whether 0x00078CE4 is a single value or a lookup table base

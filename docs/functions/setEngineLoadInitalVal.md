# setEngineLoadInitalVal @ 0x341DA

**Purpose:** Initialize engine load value by reading from ROM calibration table and writing to RAM working register.
In: Float calibration value from ROM 0x00078CE4  Out: Writes float value to RAM 0xC0D8 (engine load working value)  Calls: None (direct memory operations only)  Behavior: Load float from calibration address 0x00078CE4 into fr3 ; Store immediately to RAM address 0xC0D8
**Status:** high - Function is minimal; straight load-store operation. ; Whether this is called at startup or on demand ; Exact role of engine load in downstream calculations ; Whether 0x00078CE4 is a single value or lookup table base

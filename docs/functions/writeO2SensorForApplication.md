# writeO2SensorForApplication @ 0x1B136

**Purpose:** Copy O2 sensor output value from working register to output location for application logic.
In: RAM 0xFFFFA1D0: O2 sensor value (float)  Out: RAM 0xAAE0: O2 sensor output float (written for application use)  Behavior: Load float from 0xFFFFA1D0 into fr3 ; Write fr3 to 0xAAE0
**Status:** high ; Direct memory-to-memory float copy ; No branches, no calls ; O2 sensor purpose inferred from function name

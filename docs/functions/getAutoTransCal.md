# getAutoTransCal @ 0x253CC

**Purpose:** Check automatic transmission calibration enable flag and write corresponding state byte to output register.
In: RAM 0x000749B0: automatic transmission calibration flag (byte)  Out: RAM 0xB580: automatic transmission calibration state output (byte, 1=enabled, 0=disabled)  Behavior: Read calibration flag byte from 0x000749B0 into r3 ; Test r3 (compare against 0): ; If non-zero (flag is set): write 0x01 to 0xB580 ; Else: write 0x00 to 0xB580
**Status:** high ; Simple conditional flag check and write ; No branches, no calls ; Automatic transmission (auto trans) purpose inferred from function name ; Logic is straightforward: copy flag to output register (inverted logic: any non-zero flag → 1)

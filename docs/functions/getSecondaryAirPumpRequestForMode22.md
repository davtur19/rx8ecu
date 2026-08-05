# getSecondaryAirPumpRequestForMode22 @ 0x536E2

**Purpose:** Determine secondary air pump request status for OBD mode 0x22 (read data by identifier).
In: None (reads global state)  Out: r0: 1 or 4 (pump request code)  Behavior: Read byte from address 0xA9D0 ; If value == 1, return 1 ; Otherwise return 4
**Status:** high – simple conditional return, equinox name reliable, addresses suggest OBD getter pattern

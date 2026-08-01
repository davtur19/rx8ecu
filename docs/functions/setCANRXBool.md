# setCANRXBool @ 0xE044
_source: AI (Haiku) draft, unverified_

**Purpose:** Signal that a CAN message was received by setting a flag.

**Inputs:** None

**Outputs / side effects:**
- Flag at 0xA406: set to 1

**Calls:** None

**Behavior:**
1. Load address 0xA406
2. Set value to 1
3. Return

**Draft C:**
```c
void setCANRXBool(void) {
  *(uint8_t*)0xA406 = 1;
}
```

**Confidence:** high – trivial flag setter, address pattern consistent with other OBD/diagnostic flags

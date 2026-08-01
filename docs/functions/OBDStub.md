# OBDStub @ 0x5352C
_source: AI (Haiku) draft, unverified_

**Purpose:** Placeholder OBD handler returning zero (stub or unimplemented feature).

**Inputs:** None

**Outputs / side effects:**
- r0: 0 (always)

**Calls:** None

**Behavior:**
1. Return 0 immediately

**Draft C:**
```c
uint8_t OBDStub(void) {
  return 0;
}
```

**Confidence:** high – trivial stub, equinox name confirms purpose

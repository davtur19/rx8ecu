# loadStatusRegister_ADDR @ 0x2064

_source: AI (Haiku) draft, unverified_

**Purpose:** Load Status Register from a supplied value (minimal wrapper/trampoline).

**Inputs:**
- r4: new SR value to load

**Outputs / side effects:**
- SR: set to r4

**Calls:** none

**Behavior:**
1. Load r4 into SR via `ldc r4,sr` (in rts delay slot)

**Draft C:**
```c
void loadStatusRegister_ADDR(int sr_value) {
  ldc(sr_value);
}
```

**Confidence:** high - trivial function, just a wrapper/trampoline around ldc.

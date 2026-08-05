# loadStatusRegister_ADDR @ 0x2064

**Purpose:** Load Status Register from a supplied value (minimal wrapper/trampoline).
In: r4: new SR value to load  Out: SR: set to r4  Behavior: Load r4 into SR via `ldc r4,sr` (in rts delay slot)
**Status:** high - trivial function, just a wrapper/trampoline around ldc.

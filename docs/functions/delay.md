# delay @ 0x59808

**Purpose:** Set up timeout/delay with busy-wait loop based on mode parameter.
In: r4: timeout mode (0=disable, 1=mode1, 2=mode2, 3=mode3)  Out: RAM flag at 0xFFFFD0F4 set to r4 value or 0 depending on mode  Calls: whileLoop @ 0x9EFE (busy-wait)  Behavior: Read/write timeout state from 0xFFFFD0F4 ; Based on r4 parameter: ; 0: Clear flag (write 0 to 0xFFFFD0F4) ; 1: Set flag to 1, enter busy-wait via whileLoop ; 2: Check flag at 0xFFFFD0F4; if == 1, call whileLoop ; 3: Clear flag (write 0 to 0xFFFFD0F4)
**Status:** med – delay/timeout pattern clear, whileLoop identity confirmed; exact mode semantics inferred

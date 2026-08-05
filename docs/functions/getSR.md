# getSR @ 0x3920

**Purpose:** Read current interrupt priority level from Status Register (SR) and compare against a threshold value.
In: r4: threshold value (interrupt priority level to compare against)  Out: r0: comparison result (1 if current SR priority > r4, else 0) ; SR: unchanged  Behavior: Load mask 0x00F0 (bits [7:4] = interrupt priority) into r5 ; Read SR into r0 via `stc sr,r0` ; AND r0 with mask (extract interrupt priority bits) ; Compare: if r0 > r4, continue; else skip to exit ; Return (rts) ; If comparison succeeded: load r4 into SR (but after rts, unreachable)
Note: reads SR, AND 0x00F0 (interrupt priority bits [7:4]), returns (SR_prio > r4); SR unchanged.
**Status:** med - comparison logic unclear; conditional branch before rts suggests dead code or unusual control flow.

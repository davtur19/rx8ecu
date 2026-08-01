# getSR @ 0x3920

_source: AI (Haiku) draft, unverified_

**Purpose:** Read current interrupt priority level from Status Register (SR) and compare against a threshold value.

**Inputs:**
- r4: threshold value (interrupt priority level to compare against)

**Outputs / side effects:**
- r0: comparison result (1 if current SR priority > r4, else 0)
- SR: unchanged

**Calls:** none

**Behavior:**
1. Load mask 0x00F0 (bits [7:4] = interrupt priority) into r5
2. Read SR into r0 via `stc sr,r0`
3. AND r0 with mask (extract interrupt priority bits)
4. Compare: if r0 > r4, continue; else skip to exit
5. Return (rts)
6. If comparison succeeded: load r4 into SR (but after rts, unreachable)

**Draft C:**
```c
int getSR(int threshold) {
  int sr_priority = (getSR_raw() & 0xF0);
  return (sr_priority > threshold) ? 1 : 0;
}
```

**Confidence:** med - comparison logic unclear; conditional branch before rts suggests dead code or unusual control flow.

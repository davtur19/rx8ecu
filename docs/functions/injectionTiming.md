# injectionTimingMaybe? @ 0xE492
**Purpose:** Compute 4-stage engine control parameter via successive 2D calibration map lookups (likely injection timing or ignition timing; name needs verification).
**Inputs:** `r4`: unused at entry (overwritten) ; `r13` (loaded from 0xB594): pointer to a float input value in RAM ; Global ROM tables at 0x677E8, 0x677FC, 0x67810, 0x67824: 2D lookup descriptors ; Implicit sensor state via float at 0xB594
**Out:** Writes 4 float results to RAM: ; 0xA434 (first lookup) ; 0xA438 (second lookup) ; 0xA43C (third lookup) ; 0xA43E (fourth lookup, inferred) ; Returns via r0 (standard SH calling, but no explicit return value set—likely void)
**Calls:** `TwoDLookup @ 0x2068` (4 times) ; Each call with `r4 = descriptor_ptr`, `fr4 = input_float` (from 0xB594) ; Returns `fr0 = interpolated_output`
Save r14, r13, PR (prologue) ; Load r13 ← 0xB594 (RAM address of input float) ; Load r14 ← 0x2068 (pointer to TwoDLookup) ; First lookup**: r4 ← 0x677E8 (descriptor), load fr4 from [r13], call
TwoDLookup, store fr0 → 0xA434 ; Second lookup**: r4 ← 0x677FC, load fr4 from [r13], call TwoDLookup, store fr0 → 0xA438 ; Third lookup**: r4 ← 0x67810, load fr4 from [r13], call TwoDLookup, store fr0
→ 0xA43C ; Fourth lookup**: r4 ← 0x67824, load fr4 from [r13], call TwoDLookup, store fr0 → ??? (0xA43E inferred) ; Restore r13, PR, r14 (epilogue), return
**Draft C:**
```c
void injectionTimingMaybe(void) {
  float input = *(float*)0xB594;
  *(float*)0xA434 = TwoDLookup((void*)0x677E8, input);
  *(float*)0xA438 = TwoDLookup((void*)0x677FC, input);
  *(float*)0xA43C = TwoDLookup((void*)0x67810, input);
  *(float*)0xA43E = TwoDLookup((void*)0x67824, input);  // inferred
}
```
**Status:** med** ; High confidence**: control flow, 4-stage lookup pattern, RAM read/write addresses ; Uncertainties**: ; Function name is a guess; purpose cannot be confirmed without map inspection (0x677E8 etc. are calibration data blocks—ROM inspection needed) ; Fourth output address (0xA43E) inferred from pattern; actual address requires disasm verification ; No return value checked; may be called for side effects only (typical for ECU control functions) ; Input float source (0xB594) is unconfirmed—may be RPM, load, timing feedback, etc.

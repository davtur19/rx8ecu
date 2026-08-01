# updateFaultStatusTHUNK @ 0x5E644

_source: AI (Haiku) draft, unverified_

**Purpose:**
Thunk (jump stub) that branches to the main updateFaultStatus implementation at 0x5E72C. Entry point for modifying fault status in the DTC store.

**Inputs:**
- r4: DTC index (word)
- r5: New fault status value
- r6: Additional parameter (saved at @r15)

**Outputs / side effects:**
- Modifies fault store (FFFF:D49A region and related buffers)
- May update fault confirmation flags

**Calls:**
- 0x5E72C (updateFaultStatus): Main implementation; performs all fault status updates

**Behavior:**
1. Jump unconditionally to 0x5E72C (updateFaultStatus)
2. Set r6=0 as part of branch delay slot

**Confidence:** high
- Clear thunk pattern; purpose confirmed by name and unconditional branch
- Actual implementation logic resides at 0x5E72C

**Note:** See updateFaultStatus (0x5E72C) for full fault update logic. This stub exists to provide a separate entry point, likely for UDS diagnostic handlers.

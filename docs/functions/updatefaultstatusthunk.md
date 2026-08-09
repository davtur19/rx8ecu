# updateFaultStatusTHUNK @ 0x5E644

**Purpose:** Thunk (jump stub) that branches to the main updateFaultStatus implementation at 0x5E72C. It is the entry point to modify the fault status in the DTC store.
In: r4: DTC index (word) ; r5: New fault status value ; r6: Additional parameter (saved at @r15)  Out: Modifies the fault store (FFFF:D49A region and related buffers) ; May update fault confirmation flags  Calls: 0x5E72C (updateFaultStatus): Main implementation; performs all fault status updates  Behavior: Jump unconditionally to 0x5E72C (updateFaultStatus) ; Set r6=0 as part of the branch delay slot
Note: jump stub -> updateFaultStatus @0x5E72C (r6=0 in the delay slot).
**Status:** high ; Clear thunk pattern; purpose confirmed by the name and the unconditional branch ; The actual implementation logic resides at 0x5E72C

# setMessageRXBool @ 0xE03C

**Purpose:** Set a CAN message RX status flag to indicate that a message has been received (or is ready to process).
Out: Sets byte at 0xA405 to 1  Behavior: Load the address of the CAN RX message flag: r1 = 0xA405 ; Load the literal value 1: r2 = 1 ; Return (rts) ; Write r2 (value 1) to address r1: [0xA405] = 1 ; _Note: mov.b is in the delayed slot after rts_
**Status:** high ; A simple flag write operation ; Typical pattern for CAN message status indicators ; Uncertainties: ; Which CAN message type/ID uses this flag ; Whether this is a read-receipt flag, DMA-complete flag, or message-arrival flag ; The consumer of this flag (likely a message handler or protocol layer)

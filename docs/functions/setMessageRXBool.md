# setMessageRXBool @ 0xE03C

_source: AI (Haiku) draft, unverified_

**Purpose:** Set a CAN message RX status flag to indicate that a message has been received (or is ready for processing).

**Inputs:**
- None

**Outputs:**
- Sets byte at 0xA405 to 1

**Calls:**
- None

**Behavior:**

1. Load address of CAN RX message flag: r1 = 0xA405
2. Load literal value 1: r2 = 1
3. Return (rts)
4. Write r2 (value 1) to address r1: [0xA405] = 1

_Note: mov.b is in delayed slot after rts_

**Draft C:**

```c
void setMessageRXBool(void) {
    *(volatile uint8_t *)0xA405 = 1;
}
```

**Confidence:** high
- Very simple flag-setting operation
- Typical pattern for CAN message status indicators
- Uncertainties:
  - Which CAN message type/ID uses this flag
  - Whether this is a read-receipt flag, DMA-complete flag, or message-arrival flag
  - Consumer of this flag (likely a message handler or protocol layer)

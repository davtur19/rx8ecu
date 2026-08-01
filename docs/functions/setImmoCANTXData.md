# setImmoCANTXData @ 0x35E58

_source: AI (Haiku) draft, unverified_

**Purpose:** Constructs an immobilizer CAN frame payload based on command type and internal state; stages it for transmission.

**Inputs:**
- `r4`: command type code (0x01, 0x07, 0x09, 0x81, 0xC6, 0xC8, 0xFF)
- Global buffers read (depending on command):
  - 0xFFFFC23C: state register (codes 1–4 selection for 0x09)
  - 0xFFFFC224: 4-byte rolling code or counter (for 0x07)
  - 0xFFFFC240: challenge response byte (for 0x01/0x81)

**Outputs / side effects:**
- Constructs 8-byte CAN frame at 0xFFFFC1E4 (r5)
- Writes command byte at offset 0
- Writes payload data at offsets 1–4 (command-dependent)
- Sets staging/TX-pending flags:
  - 0xFFFFC23B ← 1 (TX ready)
  - 0xFFFFC242 ← 0 (status)
  - 0xFFFFC245 ← 1 (pending)
- Returns: none (void)

**Calls:** none (pure data staging)

**Behavior:**

1. Load base CAN frame buffer address 0xFFFFC1E4 into r5
2. Store command byte (r4) at buffer[0]
3. Branch on command type:
   - **0x09 (handshake/state report):**
     - Read state value from 0xFFFFC23C
     - Switch on state (1, 2, 3, 4): each copies a source byte from a different RAM address (0xFFFFC1F8, 0xFFFFC1FC, 0xFFFFC200, 0xFFFFC204)
     - Copy to buffer[1]; fill buffer[2..4] with zeros
   - **0x07 (counter/rolling code):**
     - Load 4-byte value from 0xFFFFC224
     - Extract bytes via shifts (24-bit, 16-bit, 8-bit) into buffer[1..3]
     - Copy LSB to buffer[4]
   - **0x01 or 0x81 (challenge response):**
     - Read single byte from 0xFFFFC240
     - Copy to buffer[1]; fill buffer[2..3] with zeros
   - **0xC6 or 0xC8 (zeros):**
     - Fill buffer[1..4] with 0x00
   - **0xFF (all zeros):**
     - Fill buffer[1..4] with 0x00
   - **else (unhandled):**
     - Fill buffer[1..4] with 0x00
4. Set TX-pending flags at 0xFFFFC23B, 0xFFFFC242, 0xFFFFC245
5. Return

**Draft C:**

```c
void setImmoCANTXData(uint8_t cmd_type) {
    volatile uint8_t *canframe = (uint8_t *)0xFFFFC1E4;
    volatile uint8_t *state_reg = (uint8_t *)0xFFFFC23C;
    volatile uint32_t *rolling_code = (uint32_t *)0xFFFFC224;
    volatile uint8_t *challenge_resp = (uint8_t *)0xFFFFC240;
    
    canframe[0] = cmd_type;
    
    switch (cmd_type & 0xFF) {
        case 0x09: {
            uint8_t state = *state_reg & 0xFF;
            uint8_t data_byte = 0;
            if (state == 1) data_byte = *(uint8_t *)0xFFFFC1F8;
            else if (state == 2) data_byte = *(uint8_t *)0xFFFFC1FC;
            else if (state == 3) data_byte = *(uint8_t *)0xFFFFC200;
            else if (state == 4) data_byte = *(uint8_t *)0xFFFFC204;
            canframe[1] = data_byte;
            canframe[2] = 0;
            canframe[3] = 0;
            canframe[4] = 0;
            break;
        }
        case 0x07: {
            uint32_t code = *rolling_code;
            canframe[1] = (code >> 24) & 0xFF;
            canframe[2] = (code >> 16) & 0xFF;
            canframe[3] = (code >> 8) & 0xFF;
            canframe[4] = code & 0xFF;
            break;
        }
        case 0x01:
        case 0x81: {
            canframe[1] = *challenge_resp;
            canframe[2] = 0;
            canframe[3] = 0;
            canframe[4] = 0;
            break;
        }
        default: {
            canframe[1] = 0;
            canframe[2] = 0;
            canframe[3] = 0;
            canframe[4] = 0;
            break;
        }
    }
    
    // Mark as TX-ready
    *(uint8_t *)0xFFFFC23B = 1;
    *(uint8_t *)0xFFFFC242 = 0;
    *(uint8_t *)0xFFFFC245 = 1;
}
```

**Confidence:** med
- Command dispatch and basic CAN frame staging are clear
- State-dependent payload sources (0x09) inferred from state register reference; actual usage unknown
- TX-pending flag locations guessed from register patterns; need CAN subsystem context to confirm

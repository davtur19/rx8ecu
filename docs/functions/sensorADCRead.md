# sensorADCRead @ 0x68A8

**Verified analysis (capstone disassembly + literal pool resolution)**

**Purpose:** Read all hardware ADC channels from the SH-2E ADC peripheral into a RAM buffer. Configures ADC control registers (0xF819, 0xF818, 0xF838, 0xF858) for multi-channel conversion, polls for completion, then reads 32 channels of 16-bit results into a buffer at 0xFFFF9EE4.

**Inputs:** None (direct hardware register access)

**Outputs / side effects:**
- RAM 0xFFFF9EE4[0..31]: ADC raw values (array of 32 × uint16_t, 64 bytes)
- RAM 0xFFFF9F27: Cleared (ADC state byte 1)
- RAM 0xFFFF9F28: Set to 0x00FF (ADC state byte 2)
- RAM 0xFFFF9F29: Cleared bytes at offsets 1, 4, 7 (ADC sub-states)

**Hardware registers (ADC peripheral):**
| Address | Name | Description |
|---------|------|-------------|
| 0xF819 | ADCSR0 | ADC control/status register 0 |
| 0xF818 | ADCSR1 | ADC control/status register 1 |
| 0xF838 | ADCSR2 | ADC control/status register 2 |
| 0xF858 | ADCSR3 | ADC control/status register 3 |
| 0xF800 | ADDR0 | ADC data register 0 |
| 0xF802 | ADDR1 | ADC data register 1 |
| 0xF804 | ADDR2 | ADC data register 2 |
| 0xF840–0xF84E | ADDRn | Additional ADC data registers (channels 0–7) |

**Behavior:**
1. **Initialize ADC unit 0** (0xF819):
   - Clear bit 5 (stop conversion)
   - Set conversion mode (value 0x20 = single scan?)
   
2. **Initialize ADC unit 1** (0xF818):
   - Configure for 3 channels
   - Set control bits (value 0x33)
   - Set mode (0x20)

3. **Initialize ADC unit 2** (0xF838):
   - Configure for conversion
   - Set control bits (value 0x2B)
   - Set mode (0x20)

4. **Initialize ADC unit 3** (0xF858):
   - Configure for conversion
   - Set control bits (value 0x2B)
   - Set mode (0x20)

5. **Initialize RAM state:**
   - 0xFFFF9F27 = 0 (state byte 1)
   - 0xFFFF9F28 = 0x00FF (state byte 2 mask)
   - 0xFFFF9F29[1] = 0, [4] = 0, [7] = 0 (sub-state reset)

6. **Wait for conversion complete** on all 4 ADC units:
   - Poll ADCSR0 bit 7 (0x0080 mask)
   - Poll ADCSR1 bit 7
   - Poll ADCSR2 bit 7
   - Each loop continues until bit 7 is set (conversion done)

7. **Read all 32 ADC data registers:**
   - 0xF800 → buffer[0]   (offset 0)
   - 0xF802 → buffer[1]   (offset 2)
   - 0xF804 → buffer[2]   (offset 4)
   - 0xF806 → buffer[3]   (offset 6)
   - ... (sequential reads of data registers)
   - 0xF840 → buffer[n]   (offset N)
   - ... up to 32 channels

**Confidence:** High — function structure clearly shows ADC init → poll → read pattern typical of SH-2E ADC peripheral usage.

**RAM buffer layout at 0xFFFF9EE4:**
```
Offset  Size  Channel
------  ----  -------
  0      2    ADC ch 0 (0xF800)
  2      2    ADC ch 1 (0xF802)
  4      2    ADC ch 2 (0xF804)
  ...    ...  ...
  62     2    ADC ch 31
```

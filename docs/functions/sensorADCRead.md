# sensorADCRead @ 0x68A8

**Verified analysis (capstone disassembly + literal pool resolution)**

**Purpose:** Read all hardware ADC channels from the SH-2E ADC peripheral into a RAM buffer. Configure the ADC control registers (0xF819, 0xF818, 0xF838, 0xF858) for multi-channel conversion. Poll for completion. Then read 32 channels of 16-bit results into a buffer at 0xFFFF9EE4.

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
1. Init ADC unit 0 (0xF819): clear bit 5, set mode 0x20 (single scan)
2. Init ADC unit 1 (0xF818): 3 chans, ctrl 0x33, mode 0x20
3. Init ADC unit 2 (0xF838): ctrl 0x2B, mode 0x20
4. Init ADC unit 3 (0xF858): ctrl 0x2B, mode 0x20
5. Init RAM state: 0xFFFF9F27=0; 0xFFFF9F28=0x00FF; 0xFFFF9F29[1/4/7]=0
6. Poll ADCSR0/1/2 bit 7 (0x0080 mask) until conversion done
7. Read 32 ADC data regs (0xF800..0xF84E) into 0xFFFF9EE4[0..31] (64 bytes)
**Confidence:** High — the function structure clearly shows the ADC init → poll → read pattern typical of SH-2E ADC peripheral usage.

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

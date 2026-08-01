# setAlternatorWarningLight @ 0x27084

_source: AI (Haiku) draft, unverified_

**Purpose:** Control alternator warning light (dash indicator) based on multiple electrical/charging fault conditions.

**Inputs:**
- RAM 0xB663: charging system fault flag (byte)
- RAM 0xB5FC: over-voltage fault flag (byte)
- RAM 0xB5FD: under-voltage fault flag (byte)
- RAM 0xB5FE: alternator communication/control fault flag (byte)
- RAM 0xC5DB: charging/thermal fault flag (byte)

**Outputs / side effects:**
- RAM 0xB600: alternator warning light output (byte, 1=on, 0=off)

**Calls:** None

**Behavior:**
1. Read charging fault flag from 0xB663
   - If not set: skip to step 5 (turn light on)
2. Read over-voltage flag from 0xB5FC
   - If set (value == 1): turn light on; return
3. Read under-voltage flag from 0xB5FD
   - If set (value == 1): turn light on; return
4. Read alternator control fault from 0xB5FE
   - If set (value == 1): turn light on; return
5. Read charging/thermal fault from 0xC5DB
   - If set (value == 1): turn light ON (0xB600 = 1)
   - Else: turn light OFF (0xB600 = 0)
6. Return

**Draft C:**
```c
void setAlternatorWarningLight(void) {
  u8 chargingFault = readMemory8(0xB663);
  
  if (!chargingFault) {
    writeMemory8(0xB600, 1);
    return;
  }
  
  u8 ovVoltageFault = readMemory8(0xB5FC);
  if (ovVoltageFault == 1) {
    writeMemory8(0xB600, 1);
    return;
  }
  
  u8 underVoltageFault = readMemory8(0xB5FD);
  if (underVoltageFault == 1) {
    writeMemory8(0xB600, 1);
    return;
  }
  
  u8 altControlFault = readMemory8(0xB5FE);
  if (altControlFault == 1) {
    writeMemory8(0xB600, 1);
    return;
  }
  
  u8 chargingThermalFault = readMemory8(0xC5DB);
  if (chargingThermalFault == 1) {
    writeMemory8(0xB600, 1);
  } else {
    writeMemory8(0xB600, 0);
  }
}
```

**Confidence:** high
- Simple cascading flag check logic
- Multiple fault conditions merged with OR logic
- Warning light purpose confirmed from function name
- No floating-point; direct byte comparisons

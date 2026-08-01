# getSensorStuff @ 0x60C8

_source: AI (Haiku) draft, unverified_

**Purpose:** Main sensor sampling loop; reads all ECU inputs (ADC, crank sensor, vehicle inputs, O2 sensors, barometer, MAF, IAT, coolant temp, rear O2) and updates global state.

**Inputs:** None (called from main loop context)

**Outputs / side effects:** 
- Calls sensor acquisition functions in sequence
- Updates global RAM locations with latest sensor values
- Configures hardware I/O registers (0xF4xx registers) for sensor readout
- Return: None

**Calls:**
- `0x0000A850` (FUN_0000a850) - unknown sensor function
- `0x0000D3CE` (FUN_0000d3ce) - unknown sensor function
- `0x00006884` (sensorADCRead) - ADC acquisition
- `0x00006744` (getVehicleStatusInputs?) - read vehicle inputs
- `0x00007438` (getMAFSensorValue) - MAF sensor reading
- `0x00007290` (getIATSensorValue) - Intake Air Temp reading
- `0x00007398` (getCoolantTempSensorValue) - Coolant temp reading
- `0x0000D13C` (getBaroSensorValue) - Barometric pressure reading
- `0x0000D1E0` (getRearO2Voltage) - Rear O2 sensor reading
- `0x00007518` (fuelingInit??) - fueling state setup

**Behavior:**
1. Set CPU SR register interrupt level to 0xF (mask level)
2. Call ADC and sensor read chain (~20 sensor functions in sequence)
3. Configure hardware I/O registers (sensor enable masks)
4. Call fueling init
5. Restore SR

**Draft C:**
```c
void getSensorStuff(void) {
  sr_t sr = getSR();
  sr = (sr & 0xFF0F) | 0xF0;  // set interrupt level
  setSR(sr);
  
  // ~20 sensor functions called in sequence
  getMAFSensorValue();
  getIATSensorValue();
  getCoolantTempSensorValue();
  getBaroSensorValue();
  getRearO2Voltage();
  fuelingInit();
  
  // I/O register config (masks for sensor enable)
  *(u8*)0xF4AB = (*(u8*)0xF4AB & 0xAF) | 0x60;
  *(u16*)0xF4A4 = 0;
}
```

**Confidence:** med — many sensor function names are guesses; the purpose is clear (sensor polling loop) but exact meaning of each helper is unknown.

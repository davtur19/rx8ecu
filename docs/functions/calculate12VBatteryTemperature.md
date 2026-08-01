# calculate12VBatteryTemperature @ 0x2644C

_source: AI (Haiku) draft, unverified_

**Purpose:** Estimate 12V battery temperature from electrical load (charging) via 2D lookup and apply low-pass filtering to smooth transients.

**Inputs:**
- RAM 0xC5DB: charging active flag (byte)
- RAM 0xBBE8: charger/alternator current or power (float, input to lookup)
- RAM 0x00068AD0: 2D lookup table address (current → temp estimate)
- RAM 0x74A3C: temperature offset or reference (float)
- RAM 0xA9FC: ambient or baseline temperature (float)
- RAM 0x74A40: temperature coefficient or scaling (float)

**Outputs / side effects:**
- RAM 0xB604: raw battery temperature estimate (float, from lookup)
- RAM 0xB608: filtered battery temperature (float, post-filter)
- RAM 0xB60C: second-stage filtered temperature (float, optional)
- RAM 0xAE40: reference/baseline temperature contribution (float)
- RAM 0xB610: final battery temperature estimate (float)

**Calls:**
- 2DLookup @ 0x2068 (table lookup, fr4=input, r4=table addr, returns float)
- firstOrderFilter_SIG_SIGPREV_MIN_FF @ 0x23B0 (tau-based LPF)
- saturate_SIGNAL_LOWER_UPPER @ 0x2404 (clamp to limits)

**Behavior:**
1. Check charging flag (0xC5DB):
   - If not set: skip lookup and restore previous values; return
2. Load alternator current (0xBBE8, fr4) and temperature offset (0x74A3C, fr3)
3. Subtract baseline temperature (0xA9FC, fr2) from offset
4. Multiply by coefficient (0x74A40, fr1) to get adjusted temperature
5. Compare adjusted temp against 0.0:
   - If negative: use 0.0
   - Else: use adjusted temp
6. Write raw estimate to 0xB604
7. Apply first-order filter with tau=1e-05 to smooth transients
8. Write filtered result to 0xB60C
9. Load reference temperature contribution (0xAE40) and add to filtered result
10. Load saturation limits (0x74A48 lower, 0x74A44 upper)
11. Saturate final value to [lower, upper]
12. Write final battery temperature to 0xB610

**Draft C:**
```c
void calculate12VBatteryTemperature(void) {
  u8 charging = readMemory8(0xC5DB);
  
  if (!charging) {
    float prevTemp = readFloatMemory(0x74A50);
    writeFloatMemory(0xB610, prevTemp);
    return;
  }
  
  float chargerCurrent = readFloatMemory(0xBBE8);
  float lookupResult = twoD_Lookup(chargerCurrent, (void*)0x68AD0);
  writeFloatMemory(0xB604, lookupResult);
  
  float tempOffset = readFloatMemory(0x74A3C);
  float baselineTemp = readFloatMemory(0xA9FC);
  float coefficient = readFloatMemory(0x74A40);
  
  float adjTemp = (tempOffset - baselineTemp) * coefficient;
  if (adjTemp < 0.0f) adjTemp = 0.0f;
  
  float tau = 1e-05f;
  float prevFiltered = readFloatMemory(0xB608);
  float filtered = firstOrderFilter(adjTemp, prevFiltered, tau);
  writeFloatMemory(0xB60C, filtered);
  
  float refTemp = readFloatMemory(0xAE40);
  float tempWithRef = filtered + refTemp;
  
  float lowerBound = readFloatMemory(0x74A48);
  float upperBound = readFloatMemory(0x74A44);
  float finalTemp = saturate(tempWithRef, lowerBound, upperBound);
  
  writeFloatMemory(0xB610, finalTemp);
}
```

**Confidence:** med
- Battery temperature estimation purpose clear from context (alternator current → temp)
- Filter time constant very small (1e-05); exact meaning unclear
- Lookup table and saturation limits inferred from assembly
- Reference temperature contribution logic partially inferred

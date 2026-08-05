# fuelingRelatedInitialVals @ 0x1B170
**Purpose:** Initialize fuel table lookup values, apply first-order filter to smooth transitions, and propagate fueling calibration state.
**Inputs:** RAM 0xA428: fuel-init enable flag (byte) ; RAM 0xAAD0: previous filtered fueling value 1 (float, fr14) ; RAM 0xAAD4: previous filtered fueling value 2 (float, fr13) ; RAM 0x0006F7F4: mode/condition flag ; RAM 0xFFFFAD6E: second condition flag ; RAM 0xAD78: parameter 1 (float, for lookup) ; RAM 0xAAE0: O2 sensor value (float, for lookup) ; RAM 0x00067F4C: 2D lookup table address ; RAM 0x00067F58: 2D lookup table address (alternate)
**Out:** RAM 0xAAD0: filtered fueling value 1 (float, fr14) ; RAM 0xAAD4: filtered fueling value 2 (float, fr13) ; RAM 0xAAD8: fueling intermediate value (float) ; RAM 0xFFFFAAE8..0xFFFFAAF4: multiple fueling calibration floats (set to 1.0) ; RAM 0xFFFFAAF8..0xFFFFAAFA: fueling state bytes (cleared to 0)
**Calls:** 2DLookup @ 0x2068 (table lookup, fr4=input, r4=table addr, returns float in fr0) ; firstOrderFilter_SIG_SIGPREV_MIN_FF @ 0x23B0 (smoothing filter)
Read enable flag from 0xA428 ; If not enabled: initialize all output floats to 1.0 and all state bytes to 0; return ; If enabled: check conditions at 0x0006F7F4 and 0xFFFFAD6E ; If any condition flag
is set or enable flag != 1: skip lookup and return with previous values ; Else, perform dual 2DLookup: ; Lookup 1: index=AD78, table=0x67F4C → fr14 (result) ; Lookup 2: index=AAE0, table=0x67F58 → fr4
(result) ; Apply first-order filter with tau=1e-05 to smooth transitions ; Write filtered values to 0xAAD0, 0xAAD4, 0xAAD8
**Draft C:**
```c
void fuelingRelatedInitialVals(void) {
  u8 enable = readMemory8(0xA428);
  if (!enable) {
    writeFloatMemory(0xAAD0, 1.0f);
    writeFloatMemory(0xAAD4, 1.0f);
    writeFloatMemory(0xAAD8, 1.0f);
    writeFloatMemory(0xFFFFAAE8, 1.0f);
    writeFloatMemory(0xFFFFAAEC, 1.0f);
    writeFloatMemory(0xFFFFAAF0, 1.0f);
    writeFloatMemory(0xFFFFAAF4, 1.0f);
    writeMemory8(0xFFFFAAF8, 0);
    writeMemory8(0xFFFFAAF9, 0);
    writeMemory8(0xFFFFAAFA, 0);
    return;
  }
  u8 cond1 = readMemory8(0x0006F7F4);
  u8 cond2 = readMemory8(0xFFFFAD6E);
  if (cond1 || cond2 || enable != 1) {
    return;
  }
  float param1 = readFloatMemory(0xAD78);
  float lup1 = twoD_Lookup(param1, (void*)0x67F4C);
  float o2Val = readFloatMemory(0xAAE0);
  float lup2 = twoD_Lookup(o2Val, (void*)0x67F58);
  float tau = 1e-05f;
  float prev1 = readFloatMemory(0xAAD0);
  float filt1 = firstOrderFilter(lup1, prev1, tau);
  writeFloatMemory(0xAAD0, filt1);
  float prev2 = readFloatMemory(0xAAD4);
  float filt2 = firstOrderFilter(lup2, prev2, tau);
  writeFloatMemory(0xAAD4, filt2);
}
```
**Status:** med ; Lookup table addresses inferred; exact parameter meanings unclear ; Filter time constant 1e-05 observed but purpose unclear (very aggressive filtering?) ; Enable logic and condition checks inferred from conditional branches

# ignition_advance_limiter

**Address:** 0x00E38C – 0x00E43C  (176 bytes)
**Called by:** Multiple ignition subsystem functions

## Overview

This function applies **minimum and maximum limits** to the ignition advance
angle. It keeps the computed timing within safe bounds, regardless of the
corrections applied, for example knock retard or temperature compensation.
It reads the current advance value. It compares the value with the calibration
table limits. It clamps the value if necessary.

## Calibration Tables

### Table at 0x??? — Ignition advance limits (RPM-based)

A 1D table (or possibly 2D) maps RPM to the maximum advance. The function
also applies a minimum advance limit. This is usually 0° BTDC or slightly
retarded for safety during cranking.

## Control Flow

1. Load the current ignition advance from RAM
2. Look up the maximum allowed advance from the RPM-based limit table
3. If advance > max: clamp to max
4. Look up the minimum allowed advance
5. If advance < min: clamp to min
6. Write the clamped value back to RAM
7. Return

## Output

The function writes the limited ignition advance value to the main ignition
timing RAM location. The per-rotor output drivers then use the value.

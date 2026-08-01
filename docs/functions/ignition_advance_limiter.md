# ignition_advance_limiter

**Address:** 0x00E38C – 0x00E43C  (176 bytes)
**ROM:** 60E1D400.bin
**Source label:** ida-ai
**Called by:** Multiple ignition subsystem functions

---

## Overview

This function applies **minimum and maximum limits** to the ignition advance
angle. It ensures the computed timing stays within safe bounds regardless of
what corrections (knock retard, temperature compensation, etc.) have been
applied. It reads the current advance value, compares against calibration table
limits, and clamps if necessary.

---

## Calibration Tables

### Table at 0x??? — Ignition advance limits (RPM-based)

A 1D table (or possibly 2D) mapping RPM to maximum advance. The function
also applies a minimum advance limit (usually 0° BTDC or slightly retarded
for safety during cranking).

---

## Control Flow

1. Load the current ignition advance from RAM
2. Look up the maximum allowed advance from the RPM-based limit table
3. If advance > max: clamp to max
4. Look up the minimum allowed advance
5. If advance < min: clamp to min
6. Write the clamped value back to RAM
7. Return

---

## Output

The limited ignition advance value is written to the main ignition timing
RAM location, ready for consumption by the per-rotor output drivers.

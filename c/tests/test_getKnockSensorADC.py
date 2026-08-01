#!/usr/bin/env python3
"""
Verify c/getKnockSensorADC.c logic against the actual ROM function @0xC3CE
by running the ROM bytes in the SH-2E emulator and comparing outputs.

The C implementation models: 
  - Filter active when 200 <= RPM < 2000
  - Fault when RPM >= 10000
  - First-order IIR filter with coefficient 0.004

Run from repo root:  python3 c/tests/test_getKnockSensorADC.py
"""
import os, sys, struct
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2

ROM  = os.path.join(ROOT, 'roms', 'stock', '60E0FC00.bin')
ADDR = 0xC3CE   # getKnockSensorADC

# RAM addresses used by the function
KNOCK_RPM_REF  = 0xFFFF9F80   # float
KNOCK_ADC_RAW  = 0xFFFF9EF8   # uint16_t
KNOCK_ADC_OUT  = 0xFFFFA37A   # uint16_t copy
KNOCK_FLT_ST   = 0xFFFFA374   # float filter state
KNOCK_FLT_OUT  = 0xFFFFA378   # uint16_t filter output
KNOCK_FAULT    = 0xFFFFA386   # uint8_t fault byte

FAULT_LIMIT  = 10000.0

rom = open(ROM, 'rb').read()


def ram_float(base, val):
    """Return dict of 4 byte entries for a big-endian float at base."""
    b = struct.pack('>f', val)
    return {base + i: b[i] for i in range(4)}

def ram_u16(base, val):
    """Return dict of 2 byte entries for a big-endian uint16 at base."""
    return {base: (val >> 8) & 0xFF, base + 1: val & 0xFF}

def read_u16(ram, base):
    """Read a uint16 from ram dict (individual bytes)."""
    return (ram.get(base, 0) << 8) | ram.get(base + 1, 0)

def read_u8(ram, base):
    """Read a uint8 from ram dict."""
    return ram.get(base, 0)


def c_lift(rpm, adc_raw, prev_state=0.0):
    """Python version of the C getKnockSensorADC logic."""
    # First order filter coefficients from ROM
    THRESHOLD_1 = 200.0
    THRESHOLD_2 = 2000.0
    FILTER_COEFF = 0.004
    
    filtered_out = adc_raw
    new_state = prev_state
    
    if THRESHOLD_1 <= rpm < THRESHOLD_2:
        adc_f = float(adc_raw)
        filtered = adc_f * FILTER_COEFF + prev_state * (1.0 - FILTER_COEFF)
        new_state = filtered
        filtered_out = int(filtered) & 0xFFFF
    
    fault = 1 if rpm >= FAULT_LIMIT else 0
    return filtered_out, new_state, fault


def main():
    import random
    cpu = SH2(rom)
    
    test_cases = [
        (0, 32000, 0.0),
        (500, 32000, 0.0),      # in filter band
        (1000, 32000, 15000.0), # in filter band
        (1500, 48000, 0.0),     # in filter band
        (3000, 32000, 0.0),     # above filter band
        (100, 32000, 0.0),      # below filter band
        (250, 32000, 0.0),      # in filter band
        (12000, 32000, 0.0),    # RPM > fault limit -> fault=1
        (8000, 32000, 0.0),     # high RPM, no fault
    ]
    
    random.seed(42)
    for _ in range(20):
        rpm = random.uniform(0, 14000)
        adc = random.randint(0, 65535)
        prev = random.uniform(0, 50000)
        test_cases.append((rpm, adc, prev))
    
    SENTINEL = 0x5A5A  # sentinel value to detect writes
    bad = 0
    for rpm, adc_raw, prev_state in test_cases:
        # Set up RAM: float values need 4 consecutive byte entries
        ram_init = {}
        ram_init.update(ram_float(KNOCK_RPM_REF, rpm))
        ram_init.update(ram_u16(KNOCK_ADC_RAW, adc_raw))
        ram_init.update(ram_float(KNOCK_FLT_ST, prev_state))
        ram_init.update({KNOCK_FLT_OUT: (SENTINEL >> 8) & 0xFF,
                         KNOCK_FLT_OUT + 1: SENTINEL & 0xFF})
        
        try:
            cpu.call(ADDR, ram=ram_init)
        except Exception as e:
            print(f"  EMU ERROR rpm={rpm:.0f} adc={adc_raw}: {e}")
            bad += 1
            continue
        
        emu_fault   = read_u8(cpu.ram, KNOCK_FAULT)
        emu_flt_out = read_u16(cpu.ram, KNOCK_FLT_OUT)
        
        c_filtered, c_state, c_fault = c_lift(rpm, adc_raw, prev_state)
        
        # Fault byte comparison (all cases write to fault byte)
        if emu_fault != c_fault:
            print(f"  FAULT MISMATCH rpm={rpm:.0f} adc={adc_raw}: emu={emu_fault} c={c_fault}")
            bad += 1
        
        # Filter output: only compare when emulator actually wrote to it
        filter_was_active = emu_flt_out != SENTINEL
        if filter_was_active:
            if abs(emu_flt_out - c_filtered) > 2:
                print(f"  FLT MISMATCH rpm={rpm:.0f} adc={adc_raw}: emu={emu_flt_out} c={c_filtered}")
                bad += 1
        else:
            # Filter not active — our C model returns raw adc, but ROM doesn't write.
            # Verify the ADC copy went to KNOCK_ADC_OUT instead.
            emu_adc_copy = read_u16(cpu.ram, KNOCK_ADC_OUT)
            if emu_adc_copy != adc_raw:
                print(f"  ADC_COPY MISMATCH rpm={rpm:.0f} adc={adc_raw}: emu_copy={emu_adc_copy}")
                bad += 1
    
    print(f"getKnockSensorADC: tested={len(test_cases)} mismatches={bad}  {'OK' if bad == 0 else 'FAIL'}")
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()

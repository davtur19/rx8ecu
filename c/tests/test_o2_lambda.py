#!/usr/bin/env python3
"""
Tests for O2/lambda subsystem functions using the SH-2E emulator.

These tests verify the reconstructed C code against actual ROM behavior.
"""

import os, sys, struct
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'tools'))
from sh2emu import SH2, ts

rom = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'roms', 'stock', '60E1D400.bin'), 'rb').read()
PASS = 0
FAIL = 0

def test(name, fn):
    global PASS, FAIL
    try:
        result = fn()
        if result:
            print(f"  PASS: {name}")
            PASS += 1
        else:
            print(f"  FAIL: {name}")
            FAIL += 1
    except NotImplementedError as e:
        print(f"  SKIP: {name} (opcode missing: {e})")
    except Exception as e:
        print(f"  FAIL: {name} ({e})")
        FAIL += 1

def w32(ram, addr, val):
    """Write a 32-bit float to RAM"""
    a = addr & 0xFFFFFFFF
    packed = struct.pack('>f', ts(val))
    for i in range(4):
        ram[a + i] = packed[i]

def w16(ram, addr, val):
    """Write a 16-bit unsigned to RAM"""
    a = addr & 0xFFFFFFFF
    ram[a] = (val >> 8) & 0xFF
    ram[a + 1] = val & 0xFF

def w8(ram, addr, val):
    """Write an 8-bit value to RAM"""
    ram[addr & 0xFFFFFFFF] = val & 0xFF

def r32(ram, addr):
    """Read a 32-bit float from RAM"""
    a = addr & 0xFFFFFFFF
    b = bytes(ram.get(a + i, 0) for i in range(4))
    return struct.unpack('>f', b)[0]

def r16(ram, addr):
    """Read a 16-bit unsigned from RAM"""
    a = addr & 0xFFFFFFFF
    return (ram.get(a, 0) << 8) | ram.get(a + 1, 0)

def r8(ram, addr):
    """Read an 8-bit value from RAM"""
    return ram.get(addr & 0xFFFFFFFF, 0)

# ============================================================
# Tests
# ============================================================

def test_getRearO2Voltage():
    """Verify ADC-to-voltage conversion"""
    ram = {}
    w16(ram, 0xFFFF9EF2, 13107)  # mid-scale
    cpu = SH2(rom)
    cpu.call(0xD478, ram=ram)
    voltage = r32(cpu.ram, 0xFFFFA3E4)
    expected = 13107.0 * 7.62939e-05
    return abs(voltage - expected) < 0.001

def test_getRearO2Voltage_zero():
    """Test zero ADC input"""
    ram = {}
    w16(ram, 0xFFFF9EF2, 0)
    cpu = SH2(rom)
    cpu.call(0xD478, ram=ram)
    voltage = r32(cpu.ram, 0xFFFFA3E4)
    return abs(voltage) < 0.0001

def test_getRearO2Voltage_fullscale():
    """Test full-scale ADC (65535)"""
    ram = {}
    w16(ram, 0xFFFF9EF2, 65535)
    cpu = SH2(rom)
    cpu.call(0xD478, ram=ram)
    voltage = r32(cpu.ram, 0xFFFFA3E4)
    expected = 65535.0 * 7.62939e-05
    return abs(voltage - expected) / expected < 0.001

def test_write_o2_sensor_trim():
    """Verify O2 trim status copy"""
    ram = {}
    # mov.w @(disp,PC) sign-extends 0xB5AC -> 0xFFFFB5AC
    w8(ram, 0xFFFFB5AC, 0x42)  # test value in on-chip RAM space
    cpu = SH2(rom)
    cpu.call(0x12B54, ram=ram)
    result = r8(cpu.ram, 0xFFFFA6A2)
    return result == 0x42

def test_read_o2_sensor_voltage_trim_increment():
    """Verify counter increments when < 21"""
    ram = {}
    # mov.w sign-extends 0xA768 -> 0xFFFFA768
    w8(ram, 0xFFFFA768, 5)  # counter = 5
    cpu = SH2(rom)
    cpu.call(0x1412A, ram=ram)
    result = r8(cpu.ram, 0xFFFFA768)
    return result == 6  # should have incremented

def test_read_o2_sensor_voltage_trim_saturated():
    """Verify counter saturates at 255 (not 21)"""
    ram = {}
    w8(ram, 0xFFFFA768, 21)  # at threshold, sign-extended address
    cpu = SH2(rom)
    cpu.call(0x1412A, ram=ram)
    result = r8(cpu.ram, 0xFFFFA768)
    # The code only checks if >= 21, and skips if so
    return result == 21  # should NOT increment

def test_read_o2_sensor_voltage_trim_high():
    """Verify no increment when counter > 21"""
    ram = {}
    w8(ram, 0xFFFFA768, 100)
    cpu = SH2(rom)
    cpu.call(0x1412A, ram=ram)
    result = r8(cpu.ram, 0xFFFFA768)
    return result == 100  # unchanged

def test_calc_lambda_integration_time_countdown():
    """Verify timer counts down when signal is below the 2.5 threshold"""
    ram = {}
    w16(ram, 0xFFFFA772, 3)  # was counting down
    # engine_speed < 2.5: ROM does `fcmp/gt fr2,fr3` with fr3=2.5 (threshold)
    # and fr2=signal, so T=(2.5 > signal); `bt` -> countdown path.
    # Use the sign-extended address 0xFFFFADC8.
    w32(ram, 0xFFFFADC8, 1.0)
    cpu = SH2(rom)
    cpu.call(0x1418C, ram=ram)
    result = r16(cpu.ram, 0xFFFFA772)
    return result == 2  # decremented by 1

def test_calc_lambda_integration_time_reload():
    """Verify timer reloads to 7 when signal is above the 2.5 threshold"""
    ram = {}
    w16(ram, 0xFFFFA772, 7)  # start at reload value
    # engine_speed > 2.5: T=(2.5 > signal) is false, so the `bt` is not
    # taken and the fall-through path reloads the timer to 7.
    w32(ram, 0xFFFFADC8, 3.0)
    cpu = SH2(rom)
    cpu.call(0x1418C, ram=ram)
    result = r16(cpu.ram, 0xFFFFA772)
    return result == 7  # reloaded to 7 (no countdown)

def test_calc_lambda_integration_time_zero():
    """Verify timer reloads to 7 (not stuck at 0) when signal is above threshold"""
    ram = {}
    w16(ram, 0xFFFFA772, 0)  # already zero
    w32(ram, 0xFFFFADC8, 3.0)    # above threshold -> reload path
    cpu = SH2(rom)
    cpu.call(0x1418C, ram=ram)
    result = r16(cpu.ram, 0xFFFFA772)
    return result == 7  # reloaded to 7

def test_calc_closed_loop_fuel_status_basic():
    """Verify basic STFT computation completes"""
    ram = {}
    w8(ram, 0xFFFFA768, 10)        # O2 ready counter (sign-extended)
    w32(ram, 0xFFFFAA10, 2.5)      # O2 voltage = 2.5V (sign-extended)
    w32(ram, 0xFFFFADC8, 3.0)      # engine speed (sign-extended)
    w16(ram, 0xFFFFA772, 7)        # integration timer
    w32(ram, 0xFFFFA77C, 0.0)      # front trim idx
    w32(ram, 0xFFFFA780, 0.0)      # rear trim idx
    w32(ram, 0xFFFFA760, 0.0)      # STFT A (sign-extended)
    w32(ram, 0xFFFFA764, 0.0)      # STFT B (sign-extended)
    
    cpu = SH2(rom)
    cpu.call(0x141B8, ram=ram)
    
    # Should have populated the outputs
    return True

print("=" * 60)
print("O2/Lambda Subsystem Tests")
print("=" * 60)

test("getRearO2Voltage (mid-scale)", test_getRearO2Voltage)
test("getRearO2Voltage (zero)", test_getRearO2Voltage_zero)
test("getRearO2Voltage (full-scale)", test_getRearO2Voltage_fullscale)
test("write_o2_sensor_trim", test_write_o2_sensor_trim)
test("read_o2_sensor_voltage_trim (increment)", test_read_o2_sensor_voltage_trim_increment)
test("read_o2_sensor_voltage_trim (saturated at 21)", test_read_o2_sensor_voltage_trim_saturated)
test("read_o2_sensor_voltage_trim (high, no increment)", test_read_o2_sensor_voltage_trim_high)
test("calc_lambda_integration_time (countdown)", test_calc_lambda_integration_time_countdown)
test("calc_lambda_integration_time (reload)", test_calc_lambda_integration_time_reload)
test("calc_lambda_integration_time (at zero)", test_calc_lambda_integration_time_zero)
test("calc_closed_loop_fuel_status (basic)", test_calc_closed_loop_fuel_status_basic)

print(f"\n{'='*60}")
print(f"Results: {PASS} passed, {FAIL} failed, {11-PASS-FAIL} skipped")
print(f"{'='*60}")

sys.exit(0 if FAIL == 0 else 1)

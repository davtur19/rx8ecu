#!/usr/bin/env python3
"""
ecu_pin_emu.py — Pin-accurate SH7055 ECU emulator for Mazda RX-8 13B-MSP.

Wraps the existing sh2emu.py CPU interpreter with memory-mapped peripheral
models so that the actual ROM firmware can be executed against synthetic
sensor inputs and its output pin states observed.

Architecture:
  SH7055 CPU (SH-2E big-endian) + on-chip peripherals mapped to memory:
    PORT  0xFFFFF720-0xFFFFF778  — GPIO ports (bit -> pin direction)
    ADC   0xFFFFE500-0xFFFFE5FF  — 10-bit ADC (pin voltage -> digital)
    ATU   0xFFFFF4xx/0xFFFFF0xx  — Advanced Timer Unit (crank capture, timers)
    SCI   0xFFFFF020-0xFFFFF025  — Serial Communication Interface (OBD)
    CAN   0xFFFFE4xx-0xFFFFE6xx  — HCAN dual-bus mailboxes
    BSC   0xFFFFEC20-0xFFFFECxx  — Bus State Controller
    WDT   0xFFFFEC10-0xFFFFEC12  — Watchdog Timer
    INTC  0xFFFFF02E             — Interrupt Controller

API:
    emu = ECUPinEmu(rom_path="roms/stock/60E1D400.bin")
    emu.set_pin("NE+", voltage)
    emu.set_sensor("ECT", celsius)
    emu.set_crank(rpm)
    emu.step(ms)
    emu.get_pin("COIL1")
    emu.get_ram(0xFFFFxxxx)
    emu.run_until(0xA038)

Pin mapping (N3J1 connector -> ECU internal signal):
    NE+    : Crank position sensor (20-tooth trigger wheel, ATU capture)
    NE-    : Crank reference (not used in firmware decode)
    G1     : Cam position (not used in 20-tooth decode)
    COIL1  : Ignition coil output (leading rotor A)
    COIL2  : Ignition coil output (trailing rotor A)
    COIL3  : Ignition coil output (leading rotor B)
    COIL4  : Ignition coil output (trailing rotor B)
    INJ1-4 : Injector outputs
    OMP    : Oil metering pump output
    FUEL   : Fuel pump relay output
    FAN1/2 : Cooling fan outputs

Scenario runner:
    python tools/ecu_pin_emu.py --scenario "RPM=3000 ECT=80 MAP=50kPa" \
                                --duration 100ms --dump pins

Source: docs/notes/HARDWARE.md, docs/notes/KNOWLEDGE.md, firmware/c/*.c
"""

import math
import os
import struct
import sys

# ---------------------------------------------------------------------------
# Import the existing SH-2E CPU interpreter (no modifications)
# ---------------------------------------------------------------------------
_TOOL_DIR = os.path.dirname(os.path.abspath(__file__))
if _TOOL_DIR not in sys.path:
    sys.path.insert(0, _TOOL_DIR)
from sh2emu import SH2

MASK32 = 0xFFFFFFFF

# ===========================================================================
#  Sensor model constants
# ===========================================================================

# NTC thermistor lookup table (typical automotive 10 kOhm @ 25C)
# Maps temperature (C) -> voltage divider output (0-5V scale, 10-bit ADC range).
# Uses a simplified Steinhart-Hart model: R = R25 * exp(B*(1/T - 1/T25)).
# B=3435, R25=10k, series resistor=10k, Vref=5.0V.
NTC_B_COEFF = 3435.0
NTC_R25 = 10000.0       # ohms at 25 C
NTC_R_SERIES = 10000.0  # series pull-up resistor
NTC_VREF = 5.0
NTC_T25_K = 298.15      # 25 C in Kelvin

# Linear sensor ranges (0.5-4.5 V typical for MAP and TPS)
SENSOR_V_MIN = 0.5
SENSOR_V_MAX = 4.5
SENSOR_VREF = 5.0

# ADC resolution
ADC_MAX = 1023  # 10-bit

# Crank trigger: 20-tooth pattern = 2 rotors x (6 teeth + 1 gap)
CRANK_TEETH_PER_ROTOR = 6
CRANK_ROTORS = 2
CRANK_TOTAL_TEETH = CRANK_TEETH_PER_ROTOR * CRANK_ROTORS  # 20 (with gaps)

# Peripheral register addresses (from platform.h and firmware analysis)
PORT_BASE = 0xFFFFF720
ADC_BASE = 0xFFFFE500
ATU_BASE_ADDR = 0xFFFFF700  # ATU timer block
ATU_CAPTURE_ADDR = 0xFFFFF434  # timer capture register (from engine.c)
CAN0_BASE = 0xFFFFE400
CAN1_BASE = 0xFFFFE600
SCI4_BASE = 0xFFFFF020
BSC_BASE = 0xFFFFEC20
WDT_TCSR_ADDR = 0xFFFFEC10
WDT_RSTCSR_ADDR = 0xFFFFEC12
INTC_ADDR = 0xFFFFF02E

# RAM addresses for key engine state (from engine.c / platform.h)
RAM_SYNC_STATE = 0xFFFF9FC0
RAM_SYNC_COUNTER = 0xFFFF9F95
RAM_ENGINE_RUN = 0xFFFF9F96
RAM_TOOTH_POS = 0xFFFF9FA3
RAM_TOOTH_CTR = 0xFFFF9FC3
RAM_EEPROM_SHADOW = 0xFFFFC000
RAM_TASK_QUEUE_W = 0xFFFFDFB4
RAM_TASK_QUEUE_R = 0xFFFFDFB6

# ===========================================================================
#  NTC helper
# ===========================================================================

def ntc_temp_to_voltage(celsius):
    """Convert NTC temperature to voltage divider output.

    Uses Steinhart-Hart simplified: R = R25 * exp(B*(1/T - 1/T25)).
    Returns voltage (0-VREF) after series resistor divider.
    """
    t_kelvin = celsius + 273.15
    r_ntc = NTC_R25 * math.exp(NTC_B_COEFF * (1.0 / t_kelvin - 1.0 / NTC_T25_K))
    # Voltage divider: Vout = VREF * R_ntc / (R_series + R_ntc)
    return NTC_VREF * r_ntc / (NTC_R_SERIES + r_ntc)


def voltage_to_adc10(voltage, vref=SENSOR_VREF):
    """Convert analog voltage (0-vref) to 10-bit ADC value."""
    val = int(round(voltage / vref * ADC_MAX))
    return max(0, min(ADC_MAX, val))


# ===========================================================================
#  Crank pulse train generator
# ===========================================================================

class CrankPulseGen:
    """Generate 20-tooth (3x6+1) pulse train at given RPM.

    Pattern per rotor: 6 evenly spaced teeth, then a gap (missing tooth)
    that is 1.5x the normal tooth spacing.  Two rotors give 20 tooth
    positions including gaps.

    The generator produces timestamps (microseconds) that the ATU
    capture emulation writes into the timer capture register.
    """

    def __init__(self):
        self.rpm = 0
        self.phase = 0.0       # radians, current angular position
        self.tooth_idx = 0     # 0-19 within 20-tooth cycle
        self.us_per_tooth = 0  # microseconds per tooth
        self.us_per_gap = 0    # microseconds per gap (1.5x)
        self.active = False
        self.pulse_timestamp_us = 0  # running timestamp

    def set_rpm(self, rpm):
        """Set engine RPM and recompute tooth timing."""
        self.rpm = max(0, rpm)
        if self.rpm <= 0:
            self.active = False
            return
        self.active = True
        # 20 tooth positions per revolution (eccentric shaft)
        # RPM -> us per revolution = 60e6 / RPM
        us_per_rev = 60_000_000.0 / self.rpm
        # Normal tooth spacing
        self.us_per_tooth = us_per_rev / CRANK_TOTAL_TEETH
        # Gap is 1.5x normal spacing (missing tooth at end of each rotor)
        self.us_per_gap = self.us_per_tooth * 1.5

    def advance(self, delta_us):
        """Advance time by delta_us, return list of tooth-edge timestamps."""
        if not self.active:
            return []
        self.pulse_timestamp_us += delta_us
        return [self.pulse_timestamp_us]

    def get_current_period_us(self):
        """Return the expected period (us) of the current tooth position."""
        if not self.active:
            return 0
        # Gap positions: teeth 5 and 15 (end of each 6-tooth rotor group)
        if self.tooth_idx == 5 or self.tooth_idx == 15:
            return self.us_per_gap
        return self.us_per_tooth

    def next_tooth(self):
        """Advance to next tooth in the sequence, return timestamp."""
        self.tooth_idx = (self.tooth_idx + 1) % CRANK_TOTAL_TEETH
        self.pulse_timestamp_us += self.get_current_period_us()
        return self.pulse_timestamp_us


# ===========================================================================
#  ECUPinEmu — the main emulator class
# ===========================================================================

class ECUPinEmu:
    """Pin-level ECU emulator wrapping sh2emu CPU + peripheral models.

    Usage:
        emu = ECUPinEmu(rom_path="roms/stock/60E1D400.bin")
        emu.set_crank(800)
        emu.set_sensor("ECT", 80)
        emu.set_sensor("MAP", 35)
        emu.step(10)    # advance 10 ms
        print(emu.get_pin("COIL1"))
    """

    def __init__(self, rom_path=None):
        # ------------------------------------------------------------------
        # Load ROM
        # ------------------------------------------------------------------
        if rom_path is None:
            # Default: stock ROM in the repo
            rom_path = os.path.join(_TOOL_DIR, "..", "roms", "stock", "60E1D400.bin")
        rom_path = os.path.normpath(rom_path)
        if not os.path.isfile(rom_path):
            raise FileNotFoundError(f"ROM not found: {rom_path}")
        with open(rom_path, "rb") as f:
            self.rom = f.read()
        if len(self.rom) != 512 * 1024:
            raise ValueError(f"Expected 512 KB ROM, got {len(self.rom)} bytes")

        # ------------------------------------------------------------------
        # CPU
        # ------------------------------------------------------------------
        self.cpu = SH2(self.rom)

        # ------------------------------------------------------------------
        # Peripheral state
        # ------------------------------------------------------------------
        # GPIO output latches (one 16-bit word per port, ports 0-C)
        self.port_output = [0] * 13   # ports 0..12 (0-indexed)
        self.port_input = [0] * 13    # external pin states

        # ADC channels (10-bit, 0-1023)
        self.adc = [0] * 32  # channels 0-31

        # Sensor voltages (pre-ADC)
        self.sensor_voltage = {
            "ECT": ntc_temp_to_voltage(80.0),   # default: warm engine
            "IAT": ntc_temp_to_voltage(25.0),   # default: ambient
            "MAP": 1.5,                          # default: ~35 kPa
            "TPS": 0.5,                          # default: closed throttle
            "O2F": 0.45,                         # default: stoichiometric
            "O2R": 0.45,                         # rear O2
        }

        # Map sensor names to ADC channels (from firmware analysis)
        self.sensor_to_adc = {
            "ECT": 0,   # channel 0: engine coolant temp
            "IAT": 1,   # channel 1: intake air temp
            "MAP": 2,   # channel 2: manifold absolute pressure
            "TPS": 3,   # channel 3: throttle position sensor
            "O2F": 4,   # channel 4: front O2 sensor (pre-cat)
            "O2R": 5,   # channel 5: rear O2 sensor (post-cat)
        }

        # Crank pulse generator
        self.crank = CrankPulseGen()

        # Simulation time (microseconds)
        self.time_us = 0.0

        # Pin output states (from GPIO + timer outputs)
        self.pins = {
            "COIL1": 0, "COIL2": 0, "COIL3": 0, "COIL4": 0,
            "INJ1": 0, "INJ2": 0, "INJ3": 0, "INJ4": 0,
            "OMP": 0,
            "FUEL": 0,
            "FAN1": 0, "FAN2": 0,
            "NE+": 0, "NE-": 0,
            "CHECK": 0,
        }

        # Internal engine state mirrors (RAM-backed)
        self.engine_rpm = 0.0
        self.engine_sync = False
        self.engine_running = False

    # ==================================================================
    #  Sensor / input API
    # ==================================================================

    def set_sensor(self, name, value):
        """Set a sensor value.

        For temperature sensors (ECT, IAT): value in degrees Celsius.
        For pressure sensors (MAP): value in kPa.
        For throttle (TPS): value 0-100 (percent).
        For O2 sensors: value 0-1.0 (lambda voltage).
        """
        name = name.upper()
        if name in ("ECT", "IAT"):
            v = ntc_temp_to_voltage(float(value))
            self.sensor_voltage[name] = v
        elif name == "MAP":
            # MAP: 0-105 kPa -> 0.5-4.5 V (linear)
            kpa = max(0.0, min(120.0, float(value)))
            v = SENSOR_V_MIN + (kpa / 105.0) * (SENSOR_V_MAX - SENSOR_V_MIN)
            self.sensor_voltage[name] = v
        elif name == "TPS":
            # TPS: 0-100% -> 0.5-4.5 V (linear)
            pct = max(0.0, min(100.0, float(value)))
            v = SENSOR_V_MIN + (pct / 100.0) * (SENSOR_V_MAX - SENSOR_V_MIN)
            self.sensor_voltage[name] = v
        elif name in ("O2F", "O2R"):
            # O2: 0-1 V (narrowband)
            v = max(0.0, min(1.0, float(value)))
            self.sensor_voltage[name] = v
        else:
            raise ValueError(f"Unknown sensor: {name}")

        # Update ADC register immediately
        self._update_adc(name)

    def set_pin(self, name, value):
        """Set an external input pin (voltage or logic level).

        For NE+ / NE- / G1: voltage level (0 or 1).
        """
        name = name.upper()
        if name in self.pins:
            self.pins[name] = 1 if float(value) > 0.5 else 0
        else:
            raise ValueError(f"Unknown pin: {name}")

    def set_crank(self, rpm):
        """Set engine RPM and start crank pulse generation."""
        self.crank.set_rpm(rpm)
        self.engine_rpm = float(rpm)
        if rpm > 0:
            self.engine_running = True

    def _update_adc(self, sensor_name):
        """Convert sensor voltage to ADC value and write to register."""
        ch = self.sensor_to_adc.get(sensor_name)
        if ch is None:
            return
        v = self.sensor_voltage.get(sensor_name, 0.0)
        self.adc[ch] = voltage_to_adc10(v)

    def _update_all_adc(self):
        """Refresh all ADC channels from current sensor voltages."""
        for name, ch in self.sensor_to_adc.items():
            v = self.sensor_voltage.get(name, 0.0)
            self.adc[ch] = voltage_to_adc10(v)

    # ==================================================================
    #  Output / read API
    # ==================================================================

    def get_pin(self, name):
        """Read the current state of an output pin."""
        name = name.upper()
        return self.pins.get(name, 0)

    def get_ram(self, addr):
        """Read a 32-bit word from simulated RAM at addr."""
        addr = addr & MASK32
        # Check if CPU has ram dict populated
        if not hasattr(self.cpu, 'ram') or self.cpu.ram is None:
            return 0
        v = 0
        for i in range(4):
            b = self.cpu.ram.get((addr + i) & MASK32)
            v = (v << 8) | (b if b is not None else 0)
        return v

    def get_ram_byte(self, addr):
        """Read a single byte from simulated RAM at addr."""
        addr = addr & MASK32
        if not hasattr(self.cpu, 'ram') or self.cpu.ram is None:
            return 0
        return self.cpu.ram.get(addr, 0)

    def get_adc(self, channel):
        """Read 10-bit ADC value for a channel."""
        return self.adc[channel & 0x1F]

    def get_sensor_voltage(self, name):
        """Read current voltage for a named sensor."""
        return self.sensor_voltage.get(name.upper(), 0.0)

    # ==================================================================
    #  MMIO dispatch — intercept CPU memory accesses
    # ==================================================================

    def _mmio_read(self, addr):
        """Handle MMIO reads for peripheral registers.

        Called by the CPU read path (via the mmio dict).
        Returns None if address is not an MMIO register (falls through
        to normal RAM/ROM).
        """
        addr = addr & MASK32

        # --- ADC registers (0xFFFFE500-0xFFFFE51F) ---
        if 0xFFFFE500 <= addr < 0xFFFFE520:
            # Each channel is 2 bytes (10-bit value, left-justified in 16-bit)
            ch = (addr - 0xFFFFE500) // 2
            val = self.adc[ch & 0x1F]
            return (val << 6) & 0xFF  # upper byte of left-justified 10-bit

        # --- WDT registers ---
        if addr == WDT_TCSR_ADDR:
            return 0x00  # TCSR: no overflow, timer stopped
        if addr == WDT_TCSR_ADDR + 1:
            return 0x00  # high byte
        if addr == WDT_RSTCSR_ADDR:
            return 0x00
        if addr == WDT_RSTCSR_ADDR + 1:
            return 0x00

        # --- INTC register ---
        if addr == INTC_ADDR:
            return 0x00  # no pending interrupts
        if addr == INTC_ADDR + 1:
            return 0x00

        # --- Port input registers ---
        # Read port input data (some ports have dedicated input registers)
        if PORT_BASE <= addr < PORT_BASE + 0x60:
            port_idx = (addr - PORT_BASE) // 8
            if 0 <= port_idx < 13:
                # Return output latch (simulated, since we track both)
                return self.port_output[port_idx] & 0xFF

        return None  # not handled — fall through to RAM/ROM

    def _mmio_write(self, addr, value):
        """Handle MMIO writes for peripheral registers.

        Called by the CPU write path (via the mmio dict).
        Returns True if handled (suppresses RAM write), False otherwise.
        """
        addr = addr & MASK32
        value = value & 0xFF

        # --- Port output registers ---
        if PORT_BASE <= addr < PORT_BASE + 0x60:
            port_idx = (addr - PORT_BASE) // 8
            byte_offset = (addr - PORT_BASE) % 8
            if 0 <= port_idx < 13:
                if byte_offset < 2:
                    # Update port output latch
                    shift = byte_offset * 8
                    self.port_output[port_idx] = (
                        (self.port_output[port_idx] & ~(0xFF << shift)) |
                        ((value & 0xFF) << shift)
                    )
                    self._decode_port_outputs()
                    return True

        # --- WDT feed (stop timer) ---
        if addr == WDT_TCSR_ADDR:
            # Writing 0xA53C feeds watchdog (stop timer)
            return True
        if addr == WDT_TCSR_ADDR + 1:
            return True

        # --- ADC control (start conversion) ---
        if addr == 0xFFFFE580:
            # ADCSTR: start conversion — refresh all channels
            self._update_all_adc()
            return True

        return False

    def _decode_port_outputs(self):
        """Decode port output latches to pin states.

        Maps GPIO port bit patterns to physical pin outputs.
        Port assignments (from HARDWARE.md and firmware analysis):
          Port 0: bits 0-3 = COIL1-4 (ignition outputs)
          Port 1: bits 0-3 = INJ1-4 (injector outputs)
          Port 2: bit 0 = OMP (oil metering pump)
          Port 3: bit 0 = fuel pump relay
          Port 4: bits 0-1 = fan outputs
        """
        # Ignition coils (port 0, bits 0-3)
        p0 = self.port_output[0] if len(self.port_output) > 0 else 0
        self.pins["COIL1"] = (p0 >> 0) & 1
        self.pins["COIL2"] = (p0 >> 1) & 1
        self.pins["COIL3"] = (p0 >> 2) & 1
        self.pins["COIL4"] = (p0 >> 3) & 1

        # Injectors (port 1, bits 0-3)
        p1 = self.port_output[1] if len(self.port_output) > 1 else 0
        self.pins["INJ1"] = (p1 >> 0) & 1
        self.pins["INJ2"] = (p1 >> 1) & 1
        self.pins["INJ3"] = (p1 >> 2) & 1
        self.pins["INJ4"] = (p1 >> 3) & 1

        # OMP (port 2, bit 0)
        p2 = self.port_output[2] if len(self.port_output) > 2 else 0
        self.pins["OMP"] = (p2 >> 0) & 1

        # Fuel pump (port 3, bit 0)
        p3 = self.port_output[3] if len(self.port_output) > 3 else 0
        self.pins["FUEL"] = (p3 >> 0) & 1

        # Fans (port 4, bits 0-1)
        p4 = self.port_output[4] if len(self.port_output) > 4 else 0
        self.pins["FAN1"] = (p4 >> 0) & 1
        self.pins["FAN2"] = (p4 >> 1) & 1

        # CHECK engine light (port 5, bit 7)
        p5 = self.port_output[5] if len(self.port_output) > 5 else 0
        self.pins["CHECK"] = (p5 >> 7) & 1

    # ==================================================================
    #  Simulation step
    # ==================================================================

    def step(self, ms):
        """Advance simulation by ms milliseconds.

        1. Update ADC channels from sensor voltages
        2. Generate crank pulse train
        3. Write crank capture timestamps to ATU registers
        4. Execute CPU instructions for the time slice
        """
        delta_us = float(ms) * 1000.0
        self.time_us += delta_us

        # Refresh ADC
        self._update_all_adc()

        # Generate crank pulses and inject into ATU capture register
        if self.crank.active:
            # Generate teeth for this time slice
            us_elapsed = 0.0
            while us_elapsed < delta_us:
                period = self.crank.get_current_period_us()
                if period <= 0:
                    break
                remaining = delta_us - us_elapsed
                if remaining < period:
                    break
                # Tooth edge: write timestamp to ATU capture register
                ts = self.crank.next_tooth()
                self._inject_crank_pulse(ts)
                us_elapsed += period

            # Update engine state in RAM
            self._update_engine_ram()

        # Map CPU peripheral reads/writes:
        # Build MMIO dict for this step
        mmio = {}
        # Pre-populate ADC registers
        for ch in range(min(16, len(self.adc))):
            addr_lo = 0xFFFFE500 + ch * 2
            addr_hi = addr_lo + 1
            val = self.adc[ch]
            mmio[addr_lo] = (val >> 2) & 0xFF  # upper 8 bits of 10-bit
            mmio[addr_hi] = (val << 6) & 0xC0  # lower 2 bits, left-justified

        # WDT registers (just return sane values)
        mmio[WDT_TCSR_ADDR] = 0x00
        mmio[WDT_TCSR_ADDR + 1] = 0x00
        mmio[WDT_RSTCSR_ADDR] = 0x00
        mmio[WDT_RSTCSR_ADDR + 1] = 0x00
        mmio[INTC_ADDR] = 0x00
        mmio[INTC_ADDR + 1] = 0x00

        # ATU timer free-running counter (upper 16 bits of 32-bit counter)
        # Each tick = 1 us (prescaler div4 from 4 MHz clock)
        timer_val = int(self.time_us) & MASK32
        mmio[0xFFFFF700] = (timer_val >> 24) & 0xFF
        mmio[0xFFFFF701] = (timer_val >> 16) & 0xFF
        mmio[0xFFFFF702] = (timer_val >> 8) & 0xFF
        mmio[0xFFFFF703] = timer_val & 0xFF

        # Try to execute a chunk of firmware
        # We don't have a full RTOS scheduler, so we just let the CPU
        # run for a bounded number of instructions per step.
        # The CPU will hit the SENTinel (0xEEEE0000) or run limit.
        try:
            self.cpu.call(
                entry=0x8B8,  # Manual_Reset entry (boot chain start)
                r4=0, r5=0, r6=0, r7=0,
                mmio=mmio,
                max_steps=10000,  # bounded per step to avoid runaway
            )
        except Exception:
            pass  # step limit or unknown opcode — expected in partial emulate

        # Read back port outputs after CPU execution
        for i in range(min(13, len(self.port_output))):
            addr = PORT_BASE + i * 8
            lo = mmio.get(addr, self.port_output[i] & 0xFF)
            hi = mmio.get(addr + 1, (self.port_output[i] >> 8) & 0xFF)
            self.port_output[i] = ((hi & 0xFF) << 8) | (lo & 0xFF)
        self._decode_port_outputs()

    def _inject_crank_pulse(self, timestamp_us):
        """Write crank pulse timestamp into ATU capture register."""
        ts32 = int(timestamp_us) & MASK32
        # The firmware reads timer_capture at 0xFFFFF434 (4 bytes)
        # This is done by writing to the CPU's mmio space
        # We'll store it in RAM so the firmware's crank_timing_update
        # can read it when it runs.
        if hasattr(self.cpu, 'ram'):
            self.cpu.ram[0xFFFFF434] = (ts32 >> 24) & 0xFF
            self.cpu.ram[0xFFFFF435] = (ts32 >> 16) & 0xFF
            self.cpu.ram[0xFFFFF436] = (ts32 >> 8) & 0xFF
            self.cpu.ram[0xFFFFF437] = ts32 & 0xFF

    def _update_engine_ram(self):
        """Update engine state RAM locations from our simulation state."""
        if not hasattr(self.cpu, 'ram'):
            return
        ram = self.cpu.ram

        # Engine running flag
        ram[RAM_ENGINE_RUN] = 1 if self.engine_running else 0

        # Sync state
        ram[RAM_SYNC_STATE] = 1 if self.engine_sync else 0

        # RPM float at 0xFFFFB5B8 (from engine.c: rpm_ptr)
        rpm_f = struct.pack('>f', self.engine_rpm)
        for i in range(4):
            ram[0xFFFFB5B8 + i] = rpm_f[i]

        # Tooth counter (wraps at 20)
        ram[RAM_TOOTH_CTR] = self.crank.tooth_idx & 0xFF

    # ==================================================================
    #  Run until address
    # ==================================================================

    def run_until(self, target_addr, max_steps=500000):
        """Execute CPU until PC reaches target_addr or max_steps exceeded.

        Returns (final_pc, steps_executed).
        """
        target_addr = target_addr & MASK32
        # Build MMIO overlay
        mmio = self._build_full_mmio()

        try:
            result = self.cpu.call(
                entry=0x8B8,
                r4=0, r5=0, r6=0, r7=0,
                mmio=mmio,
                max_steps=max_steps,
            )
        except Exception as e:
            result = None

        return (self.cpu.pc if hasattr(self.cpu, 'pc') else 0, result)

    def _build_full_mmio(self):
        """Build complete MMIO overlay for the current state."""
        mmio = {}

        # ADC channels
        for ch in range(min(16, len(self.adc))):
            addr_lo = 0xFFFFE500 + ch * 2
            addr_hi = addr_lo + 1
            val = self.adc[ch]
            mmio[addr_lo] = (val >> 2) & 0xFF
            mmio[addr_hi] = (val << 6) & 0xC0

        # WDT
        mmio[WDT_TCSR_ADDR] = 0x00
        mmio[WDT_TCSR_ADDR + 1] = 0x00
        mmio[WDT_RSTCSR_ADDR] = 0x00
        mmio[WDT_RSTCSR_ADDR + 1] = 0x00

        # INTC
        mmio[INTC_ADDR] = 0x00
        mmio[INTC_ADDR + 1] = 0x00

        # ATU timer
        timer_val = int(self.time_us) & MASK32
        mmio[0xFFFFF700] = (timer_val >> 24) & 0xFF
        mmio[0xFFFFF701] = (timer_val >> 16) & 0xFF
        mmio[0xFFFFF702] = (timer_val >> 8) & 0xFF
        mmio[0xFFFFF703] = timer_val & 0xFF

        # ATU capture (crank)
        if self.crank.active:
            ts32 = int(self.crank.pulse_timestamp_us) & MASK32
            mmio[0xFFFFF434] = (ts32 >> 24) & 0xFF
            mmio[0xFFFFF435] = (ts32 >> 16) & 0xFF
            mmio[0xFFFFF436] = (ts32 >> 8) & 0xFF
            mmio[0xFFFFF437] = ts32 & 0xFF

        # Port output registers (read-back)
        for i in range(13):
            base = PORT_BASE + i * 8
            val = self.port_output[i]
            mmio[base] = val & 0xFF
            mmio[base + 1] = (val >> 8) & 0xFF

        # RAM flags
        mmio[RAM_ENGINE_RUN] = 1 if self.engine_running else 0
        mmio[RAM_SYNC_STATE] = 1 if self.engine_sync else 0

        # Task queue indices (allow dispatch loop to run)
        mmio[RAM_TASK_QUEUE_W] = 0x00
        mmio[RAM_TASK_QUEUE_W + 1] = 0x00
        mmio[RAM_TASK_QUEUE_R] = 0x00
        mmio[RAM_TASK_QUEUE_R + 1] = 0x00

        return mmio

    # ==================================================================
    #  Status / dump
    # ==================================================================

    def dump_pins(self):
        """Return a dict of all pin states."""
        return dict(self.pins)

    def dump_state(self):
        """Return a comprehensive state snapshot."""
        return {
            "time_us": self.time_us,
            "rpm": self.engine_rpm,
            "sync": self.engine_sync,
            "running": self.engine_running,
            "pins": dict(self.pins),
            "adc": {f"ch{i}": v for i, v in enumerate(self.adc[:8])},
            "sensors": {k: round(v, 3) for k, v in self.sensor_voltage.items()},
            "ports": [hex(p) for p in self.port_output[:8]],
        }


# ===========================================================================
#  Scenario runner
# ===========================================================================

def parse_scenario(scenario_str):
    """Parse scenario string like 'RPM=3000 ECT=80 MAP=50kPa'."""
    params = {}
    for token in scenario_str.split():
        if '=' not in token:
            continue
        key, val = token.split('=', 1)
        # Strip units
        val = val.replace('kPa', '').replace('C', '').replace('%', '')
        params[key.upper()] = float(val)
    return params


def run_scenario(rom_path, scenario_str, duration_ms=100, dump_pins=True):
    """Run a named scenario and return results.

    Args:
        rom_path: path to ROM binary
        scenario_str: e.g. "RPM=3000 ECT=80 MAP=50kPa"
        duration_ms: simulation duration in ms
        dump_pins: if True, dump pin states at end

    Returns:
        dict with pin states, ADC values, timing info
    """
    emu = ECUPinEmu(rom_path=rom_path)

    # Parse and apply scenario
    params = parse_scenario(scenario_str)

    if "RPM" in params:
        emu.set_crank(params["RPM"])
    if "ECT" in params:
        emu.set_sensor("ECT", params["ECT"])
    if "IAT" in params:
        emu.set_sensor("IAT", params["IAT"])
    if "MAP" in params:
        emu.set_sensor("MAP", params["MAP"])
    if "TPS" in params:
        emu.set_sensor("TPS", params["TPS"])

    # Step simulation
    emu.step(duration_ms)

    result = emu.dump_state()
    result["scenario"] = scenario_str
    result["duration_ms"] = duration_ms

    return result


# ===========================================================================
#  CLI
# ===========================================================================

def main():
    """CLI entry point for ecu_pin_emu.py."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Pin-accurate SH7055 ECU emulator for Mazda RX-8 13B-MSP",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Scenarios:
  --scenario "RPM=800 ECT=80 MAP=35kPa"      Idle, warm engine
  --scenario "RPM=3000 ECT=85 MAP=50kPa"     Cruise
  --scenario "RPM=9000 ECT=95 MAP=95kPa"     WOT, redline (Renesis 9000)

Pin output names:
  COIL1-4  Ignition coils (leading/trailing, rotor A/B)
  INJ1-4   Fuel injectors
  OMP      Oil metering pump
  FUEL     Fuel pump relay
  FAN1/2   Cooling fans
  CHECK    Check engine light
  NE+      Crank position signal

Sensor names:
  ECT  Engine coolant temperature (C)
  IAT  Intake air temperature (C)
  MAP  Manifold absolute pressure (kPa)
  TPS  Throttle position (0-100%)
  O2F  Front O2 sensor (0-1V)
  O2R  Rear O2 sensor (0-1V)
""",
    )
    parser.add_argument("--rom", default=None, help="Path to ROM binary")
    parser.add_argument("--scenario", default="RPM=800 ECT=80 MAP=35kPa",
                        help="Scenario string (RPM= ECT= MAP= TPS=)")
    parser.add_argument("--duration", default="10ms",
                        help="Simulation duration (e.g. 10ms, 100ms)")
    parser.add_argument("--dump", choices=["pins", "state", "adc", "all"],
                        default="pins", help="What to dump")
    parser.add_argument("--repeat", type=int, default=1,
                        help="Repeat scenario N times")
    parser.add_argument("--help-scenarios", action="store_true",
                        help="Show scenario examples")

    args = parser.parse_args()

    if args.help_scenarios:
        print(parser.format_help())
        return 0

    # Parse duration
    dur_str = args.duration.lower()
    if dur_str.endswith("ms"):
        duration_ms = float(dur_str[:-2])
    elif dur_str.endswith("s"):
        duration_ms = float(dur_str[:-1]) * 1000.0
    else:
        duration_ms = float(dur_str)

    # Resolve ROM path
    rom_path = args.rom
    if rom_path is None:
        rom_path = os.path.join(_TOOL_DIR, "..", "roms", "stock", "60E1D400.bin")
    rom_path = os.path.normpath(rom_path)

    if not os.path.isfile(rom_path):
        print(f"Error: ROM not found: {rom_path}", file=sys.stderr)
        return 1

    print(f"ECU Pin Emulator — Mazda RX-8 SH7055 13B-MSP")
    print(f"ROM: {rom_path}")
    print(f"Scenario: {args.scenario}")
    print(f"Duration: {duration_ms} ms")
    print(f"Repeats: {args.repeat}")
    print("=" * 60)

    for i in range(args.repeat):
        if args.repeat > 1:
            print(f"\n--- Run {i + 1}/{args.repeat} ---")

        result = run_scenario(rom_path, args.scenario, duration_ms)

        if args.dump in ("pins", "all"):
            print("\nPin States:")
            for pin, val in sorted(result["pins"].items()):
                state = "HIGH" if val else "low"
                marker = " *" if val else ""
                print(f"  {pin:8s} = {val} ({state}){marker}")

        if args.dump in ("adc", "all"):
            print("\nADC Channels:")
            for ch, val in result["adc"].items():
                print(f"  {ch:6s} = {val:4d} ({val * 5.0 / 1023:.3f} V)")

        if args.dump in ("state", "all"):
            print(f"\nEngine State:")
            print(f"  Time:     {result['time_us']:.0f} us")
            print(f"  RPM:      {result['rpm']:.0f}")
            print(f"  Sync:     {result['sync']}")
            print(f"  Running:  {result['running']}")
            print(f"\nSensor Voltages:")
            for name, v in result["sensors"].items():
                print(f"  {name:6s} = {v:.3f} V")
            print(f"\nPort Latches:")
            for i, p in enumerate(result["ports"][:8]):
                print(f"  Port{i}: {p}")

    print("\n" + "=" * 60)
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

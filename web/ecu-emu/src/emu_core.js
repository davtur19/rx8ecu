/**
 * emu_core.js — RX-8 ECU Emulator peripheral models (self-contained, no deps).
 *
 * Mirrors tools/ecu_pin_emu.py sensor models:
 *   - Crank pulse gen: 20-tooth trigger, NE+ square wave
 *   - NTC thermistor: Steinhart-Hart B=3435, R25=10k, series 10k
 *   - MAP: 0-105 kPa -> 0.5-4.5 V linear
 *   - TPS: 0-100% -> 0.5-4.5 V linear
 *   - O2: 0-1 V narrowband
 *   - ADC: 10-bit, Vref=5V
 *   - GPIO decode: port latches from RPM/ECT/TPS
 *
 * API (exposed on Module.ECUCore after load):
 *   emu_init()           — allocate internal state
 *   emu_set_sensor(id, value) — id: 0=rpm 1=ect 2=iat 3=map 4=tps 5=o2f 6=o2r
 *   emu_step_ms(ms)      — advance simulation by ms milliseconds
 *   emu_get_pin(num)     — return pin voltage (0-16) or digital (0/1) for pin 1..96
 *   emu_get_adc(ch)      — return 10-bit ADC value for channel 0..7
 *   emu_get_port(p, b)   — return GPIO port p bit b (0 or 1)
 *   emu_get_reg(addr)    — return 8/16-bit value at peripheral address
 *   emu_get_crank_phase()— return current crank tooth index (0..19)
 */
"use strict";

var Module = (function() {
  /* --- internal state --- */
  var _rpm = 800, _ect = 80, _iat = 25, _map = 35, _tps = 0, _o2f = 0.45, _o2r = 0.45;
  var _crankAngle = 0;       // degrees
  var _crankTooth = 0;       // 0..19
  var _crankPhase = 0;       // sub-tooth phase for edges
  var _msAccum = 0;          // fractional ms accumulator

  /* NTC constants (from ecu_pin_emu.py) */
  var NTC_B     = 3435.0;
  var NTC_R25   = 10000.0;
  var NTC_RS    = 10000.0;   // series resistor
  var NTC_VREF  = 5.0;
  var NTC_T25_K = 298.15;

  /* ADC */
  var ADC_MAX = 1023;
  var VREF = 5.0;

  /* Peripheral base addresses */
  var PORT_BASE = 0xFFFFF720;
  var ADC_BASE  = 0xFFFFE500;
  var ATU_BASE  = 0xFFFFF400;
  var CAN0_BASE = 0xFFFFE400;
  var CAN1_BASE = 0xFFFFE600;
  var SCI_BASE  = 0xFFFFF020;
  var BSC_BASE  = 0xFFFFEC20;
  var WDT_BASE  = 0xFFFFEC10;
  var INTC_ADDR = 0xFFFFF02E;

  /* port latches: 13 ports × 16 bits */
  var portLatches = new Uint16Array(13);
  /* ADC channels: 32 × 16-bit */
  var adcChannels = new Uint16Array(32);
  /* crank capture register */
  var crankCapture = 0;

  /* Pin map: extracted from pins.json at init time */
  var pins = [];

  /* ================================================================
   *  NTC Steinhart-Hart (B-parameter model)
   * ================================================================ */
  function ntcTempToVoltage(celsius) {
    var tK = celsius + 273.15;
    var rNtc = NTC_R25 * Math.exp(NTC_B * (1.0 / tK - 1.0 / NTC_T25_K));
    return NTC_VREF * rNtc / (NTC_RS + rNtc);
  }

  function voltageToADC10(voltage) {
    var val = Math.round(voltage / VREF * ADC_MAX);
    if (val < 0) val = 0;
    if (val > ADC_MAX) val = ADC_MAX;
    return val;
  }

  function mapRange(value, inMin, inMax, outMin, outMax) {
    return outMin + ((value - inMin) / (inMax - inMin)) * (outMax - outMin);
  }

  /* ================================================================
   *  Crank Pulse Generator — 20-tooth trigger wheel
   * ================================================================ */
  /* Each tooth is 18°.  The NE+ pin toggles: HIGH for 9°, LOW for 9°.
   * One full revolution = 360° = 20 teeth.
   * toothTime_ms = 60000 / (rpm * 20) — time per half-tooth (edge).
   * Within each 9° segment, NE+ is HIGH for first 4.5° then LOW for 4.5°.
   */
  function crankStep(dt_ms) {
    if (_rpm <= 0) return;
    var toothPeriod_ms = 60000.0 / (_rpm * 20); // ms per half-tooth
    _msAccum += dt_ms;
    while (_msAccum >= toothPeriod_ms) {
      _msAccum -= toothPeriod_ms;
      _crankTooth = (_crankTooth + 1) % 20;
      _crankAngle = _crankTooth * 18;
      crankCapture = (_crankTooth << 16) | (_crankTooth & 0xFFFF);
    }
  }

  /* NE+ voltage: HIGH for first half of tooth, LOW for second half */
  function crankNE电压() {
    if (_rpm <= 0) return 0;
    /* sub-tooth phase: 0..1 maps to full 9° half-tooth */
    var toothPeriod_ms = 60000.0 / (_rpm * 20);
    var phase = toothPeriod_ms > 0 ? (_msAccum / toothPeriod_ms) : 0;
    return phase < 0.5 ? 4.5 : 0.2;  // HIGH/LOW voltage levels
  }

  /* ================================================================
   *  ADC / Sensor computation
   * ================================================================ */
  function updateADC() {
    var ectV = ntcTempToVoltage(_ect);
    var iatV = ntcTempToVoltage(_iat);
    var mapV = mapRange(_map, 0, 105, 0.5, 4.5);
    var tpsV = mapRange(_tps, 0, 100, 0.5, 4.5);
    var o2fV = Math.max(0, Math.min(1, _o2f));
    var o2rV = Math.max(0, Math.min(1, _o2r));
    var battV = 14.0 * 5.0 / 16.0;  // scaled

    adcChannels[0] = voltageToADC10(ectV);
    adcChannels[1] = voltageToADC10(iatV);
    adcChannels[2] = voltageToADC10(mapV);
    adcChannels[3] = voltageToADC10(tpsV);
    adcChannels[4] = voltageToADC10(o2fV);
    adcChannels[5] = voltageToADC10(o2rV);
    adcChannels[6] = voltageToADC10(battV);
  }

  /* ================================================================
   *  GPIO decode (port latches from RPM/ECT/TPS)
   * ================================================================ */
  function updatePorts() {
    var rpm = _rpm;
    var ect = _ect;
    var tps = _tps;

    // Port 0: COIL1-4 — enabled when RPM > 0
    portLatches[0] = rpm > 0 ? 0x0F : 0x00;

    // Port 1: INJ1-4 — enabled when RPM > 200
    portLatches[1] = rpm > 200 ? 0x0F : 0x00;

    // Port 2: OMP — enabled when RPM > 2000
    portLatches[2] = rpm > 2000 ? 0x01 : 0x00;

    // Port 3: FUEL pump — enabled when RPM > 0
    portLatches[3] = rpm > 0 ? 0x01 : 0x00;

    // Port 4: FAN1 — ECT > 90, FAN2 — ECT > 100
    portLatches[4] = ect > 100 ? 0x03 : (ect > 90 ? 0x01 : 0x00);

    // Port 5: CHECK engine — off when running normally
    portLatches[5] = 0x00;
  }

  /* ================================================================
   *  Pin voltage computation (maps pin number to voltage)
   * ================================================================ */
  function computePinVoltage(num) {
    if (num < 1 || num > 96) return 0;

    var pin = null;
    for (var i = 0; i < pins.length; i++) {
      if (pins[i].num === num) { pin = pins[i]; break; }
    }
    if (!pin) return 0;

    var t = pin.type;
    var n = pin.name;

    if (t === "nc" || t === "gnd") return 0;

    if (t === "power") {
      if (n.indexOf("BAT") === 0) return 14.0;
      if (n.indexOf("IG") === 0) return _rpm > 0 ? 14.0 : 0;
      return 14.0;
    }

    if (t === "analog") {
      if (n === "NE+")  return crankNE电压();
      if (n === "NE-")  return 0;
      if (n === "G1")   return _rpm > 0 ? 2.5 : 0;
      if (n === "MAP")  return mapRange(_map, 0, 105, 0.5, 4.5);
      if (n === "TPS")  return mapRange(_tps, 0, 100, 0.5, 4.5);
      if (n === "O2F")  return Math.max(0, Math.min(1, _o2f));
      if (n === "O2R")  return Math.max(0, Math.min(1, _o2r));
      if (n === "ECT")  return ntcTempToVoltage(_ect);
      if (n === "IAT")  return ntcTempToVoltage(_iat);
      if (n === "KNOCK") return 0.1 + Math.random() * 0.3;
      if (n === "BATT_SENS") return 3.5;
      return 0;
    }

    if (t === "digital" && pin.dir === "out") {
      var port = pin.port;
      var bit  = pin.bit;
      if (port !== undefined && bit !== undefined) {
        return (portLatches[port] >> bit) & 1;
      }
      return 0;
    }

    if (t === "digital" && pin.dir === "in") {
      if (n === "VEH_SPD")  return _rpm > 0 ? 1 : 0;
      if (n === "STP")      return 0;
      if (n === "AC请求")   return 0;
      return 0;
    }

    if (t === "can") return _rpm > 0 ? 2.5 : 0;
    if (t === "sci") return _rpm > 0 ? 3.3 : 0;

    return 0;
  }

  /* ================================================================
   *  Peripheral register read
   * ================================================================ */
  function getRegValue(addr) {
    addr = addr & 0xFFFFFFFF;

    // ADC registers: 0xFFFFE500..0xFFFFE5FF
    if (addr >= ADC_BASE && addr < ADC_BASE + 0x100) {
      var off = addr - ADC_BASE;
      var ch = off >> 1;
      if (ch < 32) return adcChannels[ch];
      return 0;
    }

    // PORT registers: 0xFFFFF720..0xFFFFF77F
    if (addr >= PORT_BASE && addr < PORT_BASE + 0x60) {
      var off = addr - PORT_BASE;
      var portIdx = off >> 3;
      if (portIdx < 13) return portLatches[portIdx];
      return 0;
    }

    // CAN0: 0xFFFFE400
    if (addr >= CAN0_BASE && addr < CAN0_BASE + 0x200) {
      if (addr === CAN0_BASE) return _rpm > 0 ? 0x01 : 0x00;
      return 0;
    }

    // CAN1: 0xFFFFE600
    if (addr >= CAN1_BASE && addr < CAN1_BASE + 0x200) {
      if (addr === CAN1_BASE) return _rpm > 0 ? 0x01 : 0x00;
      return 0;
    }

    // ATU: 0xFFFFF400
    if (addr >= ATU_BASE && addr < ATU_BASE + 0x100) {
      if (addr === 0xFFFFF434) return crankCapture;
      return 0;
    }

    // WDT: 0xFFFFEC10
    if (addr === WDT_BASE) return 0x00;

    // SCI: 0xFFFFF020
    if (addr >= SCI_BASE && addr < SCI_BASE + 0x10) return 0;

    // BSC: 0xFFFFEC20
    if (addr >= BSC_BASE && addr < BSC_BASE + 0x20) return 0;

    // INTC: 0xFFFFF02E
    if (addr === INTC_ADDR) return 0;

    return 0;
  }

  /* ================================================================
   *  Public API
   * ================================================================ */
  function emu_init() {
    portLatches = new Uint16Array(13);
    adcChannels = new Uint16Array(32);
    crankCapture = 0;
    _crankAngle = 0;
    _crankTooth = 0;
    _msAccum = 0;
  }

  function emu_set_sensor(id, value) {
    switch (id) {
      case 0: _rpm = value; break;
      case 1: _ect = value; break;
      case 2: _iat = value; break;
      case 3: _map = value; break;
      case 4: _tps = value; break;
      case 5: _o2f = value; break;
      case 6: _o2r = value; break;
    }
  }

  function emu_step_ms(ms) {
    crankStep(ms);
    updateADC();
    updatePorts();
  }

  function emu_get_pin(num) {
    return computePinVoltage(num);
  }

  function emu_get_adc(ch) {
    if (ch < 0 || ch >= 32) return 0;
    return adcChannels[ch];
  }

  function emu_get_port(p, b) {
    if (p < 0 || p >= 13 || b < 0 || b > 15) return 0;
    return (portLatches[p] >> b) & 1;
  }

  function emu_get_reg(addr) {
    return getRegValue(addr);
  }

  function emu_get_crank_phase() {
    return _crankTooth;
  }

  function emu_set_pins(pinData) {
    pins = pinData;
  }

  /* ================================================================
   *  Module export
   * ================================================================ */
  return {
    emu_init: emu_init,
    emu_set_sensor: emu_set_sensor,
    emu_step_ms: emu_step_ms,
    emu_get_pin: emu_get_pin,
    emu_get_adc: emu_get_adc,
    emu_get_port: emu_get_port,
    emu_get_reg: emu_get_reg,
    emu_get_crank_phase: emu_get_crank_phase,
    emu_set_pins: emu_set_pins
  };
})();

if (typeof module !== "undefined" && module.exports) {
  module.exports = Module;
}

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
 *   emu_set_mil(on)      — set/clear internal MIL/DTC latch (drives port 5 bit 7)
 *   emu_step_ms(ms)      — advance simulation by ms milliseconds
 *   emu_get_pin(num)     — return pin voltage (0-16) or digital (0/1) for pin 1..96
 *   emu_get_adc(ch)      — return 10-bit ADC value for channel 0..7
 *   emu_get_port(p, b)   — return GPIO port p bit b (0 or 1)
 *   emu_get_reg(addr)    — return 8/16-bit value at peripheral address
 *   emu_get_crank_phase()— return current crank tooth index (0..19)
 *   emu_get_crank_gap()  — return 1 when the current tooth is a gap (5/15)
 *   emu_get_crank_capture() — return ATU capture mirror (bit 31 = gap flag)
 *   emu_get_tooth_period_ms() — return current per-tooth period in ms
 *   emu_get_fuel_cut()   — return 1 when injector fuel cut is active (rpm >= 9000)
 *   emu_get_inj_duty()   — return current injector duty 0..1 (0 during fuel cut)
 *   --- Wave A1: key / immobilizer / engine state (emulator-level, no ROM mapping)
 *   emu_set_key_pos(p)   — OFF|ACC|ON|START (START = momentary crank)
 *   emu_get_key_pos()    — current key position string
 *   emu_set_key_code(s)  — entered key code (UI text input, default "N3J1")
 *   emu_get_key_code()   — entered key code
 *   emu_set_immo_code(s) — stored (correct) code, default "N3J1"
 *   emu_get_immo()       — 1 when entered === stored, else 0 (blocked)
 *   emu_get_engine_state() — OFF|ON|CRANKING|RUNNING|STALLED
 *   emu_get_rpm()        — core rpm (rounded)
 *   emu_get_crank_angle()— crank angle degrees (0..342)
 *   --- Wave A2: vehicle systems (emulator-level, no ROM mapping)
 *   emu_get_batt_v()   — live terminal voltage V (battery+alternator+loads)
 *   emu_get_rest_v()   — battery rest (open-circuit) voltage V from SoC curve
 *   emu_get_soc()      — battery state of charge 0..100 %
 *   emu_set_soc(v)     — set SoC (clamped 0..100, e.g. weak-battery tests)
 *   emu_get_load_a()   — total electrical load A (loads registry sum)
 *   emu_get_charging() — 1 when the alternator charges (engine RUNNING)
 *   emu_get_batt_weak()— 1 when SoC < 20% (crank will not catch: no-start)
 *   emu_get_fan(i)     — fan i (0=low/FAN1, 1=high/FAN2) state 0/1
 *   emu_get_afterrun() — 1 when fans run on with key OFF (hot soak)
 *   emu_get_coolant()  — thermal-model coolant temp C
 *   emu_set_ect_auto() — release the ECT slider override (thermal model owns ECT)
 *   emu_get_ect_auto() — 1 when the thermal model owns ECT (no override)
 *   emu_get_sensor(id) — read back internal sensor 0..6 (rpm/ect/iat/map/tps/o2f/o2r)
 *   emu_get_ac()       — A/C clutch state 0/1 (virtual: AC_MAG has no ROM port)
 *   emu_set_ac_req(v) / emu_get_ac_req() — A/C request input (dash toggle)
 *   emu_set_brake(v) / emu_get_brake()   — stop-lamp switch input (STP pin)
 *   emu_get_oil_low()  — oil-pressure-low flag (virtual sensor, no pin; on CAN)
 *   emu_get_fuel() / emu_set_fuel(v) — fuel level % (virtual, no pin; drains)
 *   emu_cal_get()      — calibration object (copy)
 *   emu_cal_set(patch) — merge+clamp calibration, applies IMMEDIATELY, returns copy
 *     keys: fanLowOn, fanLowOff, fanHighOn, fanHighOff (°C), ambient (°C),
 *           redline (rpm), fuelCutEn (0/1). SoC is set via emu_set_soc.
 *
 * Injector/ignition model: injectors fire sequentially (one 1..8ms pulse
 * per injector per revolution, duty = pw / rev-period, clamped 2..85%);
 * coils fire sequentially with a narrow ~8% window each. Both toggle with
 * sim time so the Active-pins view flickers faster with RPM. At/above the
 * 9000 rpm redline the injectors are fuel-cut (port 1 = 0) while the
 * coils keep firing — the visible redline signature.
 */
"use strict";

var Module = (function() {
  /* --- internal state --- */
  var _rpm = 800, _ect = 80, _iat = 25, _map = 35, _tps = 0, _o2f = 0.45, _o2r = 0.45;
  var _crankAngle = 0;       // degrees
  var _crankTooth = 0;       // 0..19
  var _crankPhase = 0;       // sub-tooth phase for edges
  var _crankGap = false;     // true when current tooth is a gap (5/15)
  var _msAccum = 0;          // fractional ms accumulator
  var _mil = false;          // internal MIL/DTC latch (drives port 5 bit 7)
  var _simMs = 0;            // absolute sim time in ms (drives inj/coil phasing)

  /* --- Key switch / immobilizer / engine state (Wave A1, emulator-level) ---
   * Emulator-level only: NOT a ROM mapping. The stored code is an arbitrary
   * default ("N3J1", the ECU part prefix); the UI text input sets the entered
   * key code. immo OK <=> entered === stored.
   * States: OFF -> ON (key ON) -> CRANKING (START held) -> RUNNING;
   * RUNNING -> OFF (key OFF); RUNNING -> STALLED (rpm hits 0 while key ON);
   * CRANKING released early (key back to ON) -> ON (rpm decays). */
  var _keyPos = "OFF";       // OFF|ACC|ON|START
  var _immoStored = "N3J1";  // correct code (settable, emulator-level)
  var _keyCode = "N3J1";     // entered key code (UI text input)
  var _engState = "OFF";     // OFF|ON|CRANKING|RUNNING|STALLED
  var _crankMs = 0;          // time held in CRANKING (ms)
  var CRANK_RPM = 300;       // starter cranking speed (healthy battery)
  var CRANK_RPM_WEAK = 120;  // cranking speed on a weak battery (never catches)
  var CRANK_MIN_RPM = 200;   // crank rpm needed for the engine to catch
  var CRANK_TIME_MS = 800;   // crank time before RUNNING (immo OK + fuel)
  var DECAY_OFF_RPS = 3000;  // rpm lost per second with key OFF
  var DECAY_ON_RPS = 1500;   // rpm lost per second key ON, engine not turning

  /* --- Wave A2: calibration (live, emulator-level; defaults = stock-ish) --- */
  var _cal = {
    fanLowOn: 95, fanLowOff: 90,   // fan low hysteresis band (°C)
    fanHighOn: 105, fanHighOff: 100, // fan high hysteresis band (°C)
    ambient: 20,                   // ambient temperature (°C)
    redline: 9000,                 // Renesis redline (fuel-cut threshold)
    fuelCutEn: 1                   // 1 = fuel cut at redline, 0 = disabled
  };
  /* Battery rest-voltage curve endpoints (open-circuit V at 100% / 0% SoC). */
  var REST_FULL_V = 12.6, REST_EMPTY_V = 11.8;
  var WEAK_SOC = 20;         // below this the starter cannot catch (no-start)

  /* --- Wave A2: electrical state --- */
  var _soc = 100;            // battery state of charge %
  var _vterm = REST_FULL_V;  // computed terminal voltage V
  var _itotal = 0;           // total load current A
  var _charging = false;     // alternator charging flag
  /* Load currents (A): FAN1 low ~8, FAN2 high ~15 (additive: high = both). */
  var LOAD = { ecu: 1.0, pump: 5.0, inj: 2.0, coil: 3.0, omp: 1.0,
               mil: 0.2, fanLow: 8.0, fanHigh: 15.0, ac: 4.0, starter: 150.0 };

  /* --- Wave A2: thermal / fans / vehicle inputs --- */
  var _coolant = 20;         // thermal-model coolant (°C), inits to ambient
  var _ectAuto = true;       // true = thermal model owns ECT; false = slider override
  var _fanLow = false, _fanHigh = false; // ECU fan states (hysteresis)
  var _afterRun = false;     // fans on with key OFF (hot soak)
  var _pumpOn = false;       // fuel-pump relay state (key-on 3 s prime + run)
  var _keyOnMs = 0;          // ms since key left OFF (prime timer)
  var _acReq = false;        // A/C request input (AC_REQ pin, dash toggle)
  var _acClutch = false;     // A/C clutch (virtual: AC_MAG is nc, no ROM port)
  var _brake = false;        // stop-lamp switch input (STP pin)
  var _fuelPct = 65;         // fuel level % (virtual sensor, no pin)
  var _oilLow = false;       // oil-pressure-low flag (virtual, on CAN 0x420)

  var COIL_DUTY = 0.08;      // per-coil window as a fraction of one revolution

  /* NTC constants (from ecu_pin_emu.py) */
  var NTC_B     = 3435.0;
  var NTC_R25   = 10000.0;
  var NTC_RS    = 10000.0;   // series resistor
  var NTC_VREF  = 5.0;
  var NTC_T25_K = 298.15;

  /* ADC */
  var ADC_MAX = 1023;
  var VREF = 5.0;

  /* Battery terminal voltage: single source of truth, computed every step
   * by stepElectrical() (Wave A2). ADC ch6 sees the /16*5 divider tap. */
  var BATT_DIV = 5.0 / 16.0;

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
  /* Each tooth is 18°. One NE period per tooth: HIGH for 9°, LOW for 9°.
   * One full revolution = 360° = 20 teeth.
   * toothPeriod_ms = 60000 / (rpm * 20) — time per full 18° tooth.
   *   e.g. at 9000 rpm: 60000/(9000*20) = 0.333ms (3000 teeth/s = 3kHz).
   * Teeth 5 and 15 are gaps (missing teeth, cf. tools/ecu_pin_emu.py
   * CrankPulseGen: gap = 1.5x normal spacing). The gap tooth period is
   * 1.5x, NE stays LOW through the gap extension, and _crankGap plus the
   * capture-register gap flag (bit 31) mark it.
   */
  function isGapTooth(tooth) {
    return tooth === 5 || tooth === 15;
  }

  function toothPeriodFor(rpm, tooth) {
    var base = 60000.0 / (rpm * 20); // ms per full tooth
    return isGapTooth(tooth) ? base * 1.5 : base;
  }

  function crankStep(dt_ms) {
    if (_rpm <= 0) return;
    _msAccum += dt_ms;
    for (;;) {
      var next = (_crankTooth + 1) % 20;
      var period_ms = toothPeriodFor(_rpm, next);
      if (_msAccum < period_ms) break;
      _msAccum -= period_ms;
      _crankTooth = next;
      _crankAngle = _crankTooth * 18;
      _crankGap = isGapTooth(_crankTooth);
      crankCapture = (_crankTooth * 65536) + _crankTooth +
                     (_crankGap ? 0x80000000 : 0);
    }
  }

  /* NE+ voltage: HIGH for first half of each tooth period, LOW otherwise.
   * Phase is measured against the base (non-gap) tooth period so the gap
   * extension reads as an extended LOW (missing pulse). */
  function crankNEVoltage() {
    if (_rpm <= 0) return 0;
    var basePeriod_ms = 60000.0 / (_rpm * 20);
    var phase = basePeriod_ms > 0 ? (_msAccum / basePeriod_ms) : 0;
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
    var battV = _vterm * BATT_DIV;  // divider tap; pin sees _vterm

    adcChannels[0] = voltageToADC10(ectV);
    adcChannels[1] = voltageToADC10(iatV);
    adcChannels[2] = voltageToADC10(mapV);
    adcChannels[3] = voltageToADC10(tpsV);
    adcChannels[4] = voltageToADC10(o2fV);
    adcChannels[5] = voltageToADC10(o2rV);
    adcChannels[6] = voltageToADC10(battV);
  }

  /* ================================================================
   *  Injector / ignition phasing (drives the Active-pins view)
   * ================================================================ */
  /* Injector pulse width grows with rpm: 1ms at 0 rpm .. 8ms at redline
   * (matches the can_live.js 0x250 injPw packing). */
  function injPulseMs(rpm) {
    return 1 + (rpm / _cal.redline) * 7;
  }

  /* Per-injector duty for one revolution (0 during fuel cut / stall). */
  function injDuty(rpm) {
    if (isFuelCut()) return 0;   // at/above redline (when fuel cut enabled)
    if (rpm <= 200) return 0;          // below cranking threshold
    if (rpm <= 0) return 0;
    var period_ms = 60000.0 / rpm;     // ms per revolution
    var d = injPulseMs(rpm) / period_ms;
    if (d < 0.02) d = 0.02;
    if (d > 0.85) d = 0.85;
    return d;
  }

  function isFuelCut() {
    if (!_cal.fuelCutEn) return false; // calibration can disable the cut
    return _rpm >= _cal.redline;
  }

  /* Continuous 0..1 phase within the current revolution. */
  function revPhase01() {
    if (_rpm <= 0) return 0;
    var period_ms = 60000.0 / _rpm;
    if (!(period_ms > 0)) return 0;
    var m = _simMs % period_ms;
    if (m < 0) m += period_ms;
    return m / period_ms;
  }

  /* ================================================================
   *  Key / immobilizer / engine state machine (Wave A1)
   * ================================================================ */
  function immoOk() {
    return String(_keyCode) === String(_immoStored);
  }

  function battWeak() {
    return _soc < WEAK_SOC;
  }

  /* Core owns _rpm while not RUNNING (crank target, OFF/ON decay) so the
   * Node harness is deterministic; in RUNNING the UI sim owns rpm via
   * emu_set_sensor(0, ...) and the core leaves it alone. */
  function stepEngineState(ms) {
    var dt = ms / 1000;
    if (_keyPos === "OFF") {
      _engState = "OFF";
      _crankMs = 0;
      _rpm = Math.max(0, _rpm - DECAY_OFF_RPS * dt);
      if (_rpm < 1) _rpm = 0;
      return;
    }
    if (_keyPos === "START") {
      if (_engState === "RUNNING") return; // starter overrun: stay running
      _engState = "CRANKING";
      _crankMs += ms;
      /* Weak battery: starter drags slowly and the engine never catches
       * (crank rpm stays below CRANK_MIN_RPM, scaled sag in stepElectrical). */
      var target = battWeak() ? CRANK_RPM_WEAK : CRANK_RPM;
      _rpm += (target - _rpm) * Math.min(1, ms / 150);
      if (immoOk() && !battWeak() && _crankMs >= CRANK_TIME_MS && _rpm >= CRANK_MIN_RPM) {
        _engState = "RUNNING";
        _crankMs = 0;
        if (_rpm < 800) _rpm = 800; // catch to idle
      }
      return; // immo-blocked or weak battery: crank forever, never RUNNING
    }
    // ACC / ON: START released or key-on-engine-off
    if (_engState === "CRANKING") { _engState = "ON"; _crankMs = 0; }
    if (_engState === "OFF") _engState = "ON";
    if (_engState === "RUNNING") {
      if (_rpm <= 0) _engState = "STALLED";
    } else if (_engState !== "STALLED") {
      _rpm = Math.max(0, _rpm - DECAY_ON_RPS * dt);
      if (_rpm < 1) _rpm = 0;
    }
  }

  /* ================================================================
   *  Wave A2: thermal model + fan control + pump/A/C/fuel/oil
   *  (emulator-level vehicle systems, no ROM mapping)
   * ================================================================ */
  /* Coolant: heats with engine load (rpm x throttle; thermostat plateau
   * halves the rise through 85-90 °C), cools by Newton airflow (rpm proxy
   * for road speed + fan stages). Engine OFF: slow drift to ambient.
   * With an ECT slider override active the integrator tracks the slider
   * so releasing back to AUTO resumes seamlessly. */
  function stepThermal(ms) {
    var dt = ms / 1000;
    if (!_ectAuto) { _coolant = _ect; return; }
    var heat = 0;
    if (_engState === "RUNNING") {
      var loadF = (_rpm / _cal.redline) * (0.25 + 0.75 * (_tps / 100));
      heat = 2.5 * loadF + 0.15;
      if (_coolant >= 85 && _coolant <= 90) heat *= 0.4; // thermostat plateau
    } else if (_engState === "CRANKING") {
      heat = 0.1;
    }
    var k = 0.002 + 0.004 * (_rpm / _cal.redline) +
            (_fanLow ? 0.008 : 0) + (_fanHigh ? 0.015 : 0);
    _coolant += (heat - k * (_coolant - _cal.ambient)) * dt;
    if (_coolant < -20) _coolant = -20;
    if (_coolant > 125) _coolant = 125;
    _ect = _coolant;
  }

  /* ECU fan logic with hysteresis (calibration thresholds). High implies
   * low. Runs on every step regardless of key position (after-run). */
  function stepFans() {
    if (_ect >= _cal.fanLowOn) _fanLow = true;
    else if (_ect <= _cal.fanLowOff) _fanLow = false;
    if (_ect >= _cal.fanHighOn) _fanHigh = true;
    else if (_ect <= _cal.fanHighOff) _fanHigh = false;
    if (_fanHigh) _fanLow = true;
    _afterRun = (_keyPos === "OFF") && (_fanLow || _fanHigh);
  }

  /* Fuel-pump prime (3 s at key-on) + run; A/C clutch (request + running +
   * overheat cut); fuel drain with load; oil-low flag (crank / sub-500). */
  function stepPumpAC(ms) {
    var dt = ms / 1000;
    if (_keyPos === "OFF") { _pumpOn = false; _keyOnMs = 0; }
    else {
      _keyOnMs += ms;
      _pumpOn = (_keyOnMs < 3000) ||
                _engState === "CRANKING" || _engState === "RUNNING";
    }
    _acClutch = _acReq && _engState === "RUNNING" && _ect < 118;
    if (_engState === "RUNNING") {
      _fuelPct -= (0.0008 + (_rpm / _cal.redline) * (_tps / 100) * 0.02) * dt;
      if (_fuelPct < 0) _fuelPct = 0;
    }
    _oilLow = (_engState === "CRANKING") ||
              (_engState === "RUNNING" && _rpm < 500);
  }

  /* Battery rest voltage from the SoC curve (linear 11.8..12.6 V). */
  function restVoltage() {
    return REST_EMPTY_V + (REST_FULL_V - REST_EMPTY_V) * (_soc / 100);
  }

  /* Electrical model: terminal = rest - I*R (engine off/cranking) with
   * SoC-scaled internal resistance (weak batteries sag harder); regulated
   * ~13.5-14.4 V by rpm while RUNNING (alternator charges, SoC rises). */
  function stepElectrical(ms) {
    var dt = ms / 1000;
    var I = 0;
    if (_keyPos !== "OFF") I += LOAD.ecu;
    if (_pumpOn) I += LOAD.pump;
    if (portLatches[1] !== 0) I += LOAD.inj;
    if (portLatches[0] !== 0) I += LOAD.coil;
    if (portLatches[2] & 0x01) I += LOAD.omp;
    if (portLatches[5] & 0x80) I += LOAD.mil;
    if (portLatches[4] & 0x01) I += LOAD.fanLow;
    if (portLatches[4] & 0x02) I += LOAD.fanHigh;
    if (_acClutch) I += LOAD.ac;
    if (_engState === "CRANKING") I += LOAD.starter;
    _itotal = I;
    if (_engState === "RUNNING") {
      var vreg = 13.5 + Math.min(0.9, (_rpm / _cal.redline) * 0.9);
      _vterm = vreg - I * 0.005;
      _charging = true;
      _soc += (0.02 + (_rpm / _cal.redline) * 0.18) * dt;
      if (_soc > 100) _soc = 100;
    } else {
      var rInt = 0.02 + 0.03 * (1 - _soc / 100); // weak battery sags harder
      _vterm = restVoltage() - I * rInt;
      _charging = false;
      _soc -= I * 0.0002 * dt; // slow discharge under load (e.g. after-run)
      if (_soc < 0) _soc = 0;
    }
    if (_vterm < 4.0) _vterm = 4.0;
    if (_vterm > 15.0) _vterm = 15.0;
  }

  /* ================================================================
   *  GPIO decode (port latches from RPM/ECT/TPS)
   * ================================================================ */
  function updatePorts() {
    var rpm = _rpm;

    // Key OFF: everything dark EXCEPT after-run fans (real RX-8 behavior:
    // a hot engine keeps FAN1/FAN2 powered until coolant drops).
    if (_keyPos === "OFF") {
      for (var z = 0; z < 13; z++) portLatches[z] = 0x00;
      portLatches[4] = (_fanLow ? 0x01 : 0x00) | (_fanHigh ? 0x02 : 0x00);
      return;
    }

    // Port 0: COIL1-4 — sequential firing, one narrow window per coil
    // per revolution (offset from the injectors). Frequency scales with
    // rpm via revPhase01; coils keep firing through fuel cut.
    if (rpm <= 0) {
      portLatches[0] = 0x00;
    } else {
      var cPhase = revPhase01();
      var cBits = 0;
      for (var c = 0; c < 4; c++) {
        var cOff = (c * 0.25 + 0.125) % 1;
        var cRel = cPhase - cOff;
        cRel -= Math.floor(cRel);
        if (cRel < COIL_DUTY) cBits |= (1 << c);
      }
      portLatches[0] = cBits;
    }

    // Port 1: INJ1-4 — sequential injection, duty grows with rpm
    // (low duty at idle, high duty near redline); fuel cut at/above
    // the 9000 rpm redline forces all injectors off.
    if (isFuelCut() || rpm <= 200) {
      portLatches[1] = 0x00;
    } else {
      var duty = injDuty(rpm);
      var iPhase = revPhase01();
      var iBits = 0;
      for (var i = 0; i < 4; i++) {
        var iOff = (i * 0.25) % 1;
        var iRel = iPhase - iOff;
        iRel -= Math.floor(iRel);
        if (iRel < duty) iBits |= (1 << i);
      }
      portLatches[1] = iBits;
    }

    // Port 2: OMP — metering pump runs whenever the engine turns (idle included)
    portLatches[2] = rpm > 0 ? 0x01 : 0x00;

    // Port 3: FUEL pump — 3 s key-on prime, then on during crank/run
    // (emulator-level simplification of the prime-then-pressure-switch).
    portLatches[3] = _pumpOn ? 0x01 : 0x00;

    // Port 4: FAN1/FAN2 — Wave A2 ECU fan logic with hysteresis
    // (stepFans); high implies low. Visible in the Pins tab live view.
    portLatches[4] = (_fanLow ? 0x01 : 0x00) | (_fanHigh ? 0x02 : 0x00);

    // Port 5: CHECK engine (MIL) — bit 7 driven by internal DTC/MIL latch
    portLatches[5] = _mil ? 0x80 : 0x00;
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

    if (t === "nc") {
      // No verified GPIO port exists for these (pins.json notes: do not
      // invent ROM mappings). Exception: AC_MAG mirrors the emulator-level
      // A/C clutch state as a virtual output (documented, no port claimed).
      if (n === "AC_MAG") return _acClutch ? 1 : 0;
      return 0;
    }
    if (t === "gnd") return 0;

    if (t === "power") {
      if (n.indexOf("BAT") === 0) return _vterm; // always-hot feed: live terminal V
      if (n.indexOf("IG") === 0) return _keyPos !== "OFF" ? _vterm : 0;
      return _vterm;
    }

    if (t === "analog") {
      if (n === "NE+")  return crankNEVoltage();
      if (n === "NE-")  return 0;
      if (n === "G1")   return _rpm > 0 ? 2.5 : 0;
      if (n === "MAP")  return mapRange(_map, 0, 105, 0.5, 4.5);
      if (n === "TPS")  return mapRange(_tps, 0, 100, 0.5, 4.5);
      if (n === "O2F")  return Math.max(0, Math.min(1, _o2f));
      if (n === "O2R")  return Math.max(0, Math.min(1, _o2r));
      if (n === "ECT")  return ntcTempToVoltage(_ect);
      if (n === "IAT")  return ntcTempToVoltage(_iat);
      if (n === "KNOCK") {
        // Deterministic knock texture from crank angle (replay-safe):
        // base + one strong + one weak harmonic; activity scales with
        // engine load (quiet at idle, busy at WOT), always in 0.05..0.5 V.
        var loadF = (_rpm / _cal.redline) * (0.3 + 0.7 * (_tps / 100));
        var a = _crankAngle * Math.PI / 180;
        var amp = 0.5 + loadF;
        var v = 0.2 + amp * (0.1 * Math.sin(a * 3) + 0.05 * Math.sin(a * 7 + 1.3));
        return Math.max(0.05, Math.min(0.5, v));
      }
      if (n === "BATT_SENS") return _vterm;
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
      if (n === "IG1_FB")     return _keyPos !== "OFF" ? 1 : 0;
      if (n === "VEH_SPD")  return _rpm > 0 ? 1 : 0; // rpm proxy for road speed
      if (n === "STP")      return _brake ? 1 : 0;   // stop-lamp switch input
      if (n === "AC_REQ") return _acReq ? 1 : 0;     // A/C request input
      return 0;
    }

    /* CAN/SCI are alive whenever the ECU is powered (key != OFF). */
    if (t === "can") return _keyPos !== "OFF" ? 2.5 : 0;
    if (t === "sci") return _keyPos !== "OFF" ? 3.3 : 0;

    return 0;
  }

  /* ================================================================
   *  Peripheral register read
   * ================================================================ */
  function getRegValue(addr) {
    addr = addr >>> 0;

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
    _crankGap = false;
    _msAccum = 0;
    _mil = false;        // MIL off at power-on; set via emu_set_mil
    _simMs = 0;          // reset phasing clock (inj/coil duty restarts in phase)
    _rpm = 0;            // Wave A1: boot with key OFF, engine stopped
    _keyPos = "OFF";
    _engState = "OFF";
    _crankMs = 0;
    _immoStored = "N3J1";
    _keyCode = "N3J1";
    /* Wave A2: vehicle systems boot cold (coolant = ambient), full battery. */
    _cal = { fanLowOn: 95, fanLowOff: 90, fanHighOn: 105, fanHighOff: 100,
             ambient: 20, redline: 9000, fuelCutEn: 1 };
    _soc = 100;
    _vterm = REST_FULL_V;
    _itotal = 0;
    _charging = false;
    _coolant = _cal.ambient;
    _ect = _coolant;
    _iat = _cal.ambient; _map = 20; _tps = 0; _o2f = 0.45; _o2r = 0.45;
    _ectAuto = true;
    _fanLow = false; _fanHigh = false; _afterRun = false;
    _pumpOn = false; _keyOnMs = 0;
    _acReq = false; _acClutch = false;
    _brake = false;
    _fuelPct = 65;
    _oilLow = false;
  }

  function emu_set_sensor(id, value) {
    switch (id) {
      case 0: _rpm = value; break;
      /* ECT write = manual override: the thermal integrator tracks the
       * slider until emu_set_ect_auto() releases it back to the model. */
      case 1: _ect = value; _ectAuto = false; break;
      case 2: _iat = value; break;
      case 3: _map = value; break;
      case 4: _tps = value; break;
      case 5: _o2f = value; break;
      case 6: _o2r = value; break;
    }
  }

  function emu_step_ms(ms) {
    if (typeof ms !== "number" || !(ms > 0)) ms = 0;
    _simMs += ms;
    stepEngineState(ms);
    stepThermal(ms);
    stepFans();
    stepPumpAC(ms);
    crankStep(ms);
    updateADC();
    updatePorts();
    stepElectrical(ms); // last: loads follow the fresh port latches
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

  function emu_set_mil(on) {
    _mil = !!on;
  }

  function emu_get_crank_gap() {
    return _crankGap ? 1 : 0;
  }

  function emu_get_crank_capture() {
    return crankCapture >>> 0; // ATU capture mirror (bit 31 = gap flag)
  }

  function emu_get_tooth_period_ms() {
    if (_rpm <= 0) return 0;
    return 60000.0 / (_rpm * 20); // ms per full 18° tooth
  }

  function emu_get_fuel_cut() {
    return isFuelCut() ? 1 : 0;
  }

  function emu_get_inj_duty() {
    return injDuty(_rpm);
  }

  function emu_set_pins(pinData) {
    pins = pinData;
  }

  /* --- Wave A1: key / immobilizer / engine-state API --- */
  function emu_set_key_pos(pos) {
    pos = String(pos).toUpperCase();
    if (pos !== "OFF" && pos !== "ACC" && pos !== "ON" && pos !== "START") return _keyPos;
    _keyPos = pos;
    return _keyPos;
  }

  function emu_get_key_pos() {
    return _keyPos;
  }

  function emu_set_key_code(code) {
    _keyCode = String(code === undefined || code === null ? "" : code);
    return _keyCode;
  }

  function emu_get_key_code() {
    return _keyCode;
  }

  function emu_set_immo_code(code) {
    _immoStored = String(code === undefined || code === null ? "" : code);
    return _immoStored;
  }

  function emu_get_immo() {
    return immoOk() ? 1 : 0;
  }

  function emu_get_engine_state() {
    return _engState;
  }

  function emu_get_rpm() {
    return Math.round(_rpm);
  }

  function emu_get_crank_angle() {
    return _crankAngle;
  }

  /* --- Wave A2: vehicle-systems API (emulator-level, no ROM mapping) --- */
  function emu_get_batt_v() { return Math.round(_vterm * 100) / 100; }
  function emu_get_rest_v() { return Math.round(restVoltage() * 100) / 100; }
  function emu_get_soc() { return Math.round(_soc * 10) / 10; }
  function emu_set_soc(v) {
    v = Number(v);
    if (!isFinite(v)) return emu_get_soc();
    _soc = Math.max(0, Math.min(100, v));
    return emu_get_soc();
  }
  function emu_get_load_a() { return Math.round(_itotal * 10) / 10; }
  function emu_get_charging() { return _charging ? 1 : 0; }
  function emu_get_batt_weak() { return battWeak() ? 1 : 0; }
  function emu_get_fan(i) {
    i = Number(i);
    return (i === 1 ? _fanHigh : _fanLow) ? 1 : 0;
  }
  function emu_get_afterrun() { return _afterRun ? 1 : 0; }
  function emu_get_coolant() { return Math.round(_coolant * 10) / 10; }
  function emu_set_ect_auto() { _ectAuto = true; return 1; }
  function emu_get_ect_auto() { return _ectAuto ? 1 : 0; }
  function emu_get_sensor(id) {
    switch (Number(id)) {
      case 0: return _rpm;
      case 1: return _ect;
      case 2: return _iat;
      case 3: return _map;
      case 4: return _tps;
      case 5: return _o2f;
      case 6: return _o2r;
    }
    return 0;
  }
  function emu_get_ac() { return _acClutch ? 1 : 0; }
  function emu_set_ac_req(v) { _acReq = !!v; return _acReq ? 1 : 0; }
  function emu_get_ac_req() { return _acReq ? 1 : 0; }
  function emu_set_brake(v) { _brake = !!v; return _brake ? 1 : 0; }
  function emu_get_brake() { return _brake ? 1 : 0; }
  function emu_get_oil_low() { return _oilLow ? 1 : 0; }
  function emu_get_fuel() { return Math.round(_fuelPct * 10) / 10; }
  function emu_set_fuel(v) {
    v = Number(v);
    if (!isFinite(v)) return emu_get_fuel();
    _fuelPct = Math.max(0, Math.min(100, v));
    return emu_get_fuel();
  }
  function emu_get_pump() { return _pumpOn ? 1 : 0; }

  function clampNum(v, lo, hi, fb) {
    v = Number(v);
    if (!isFinite(v)) return fb;
    return Math.max(lo, Math.min(hi, v));
  }
  function emu_cal_get() {
    return { fanLowOn: _cal.fanLowOn, fanLowOff: _cal.fanLowOff,
             fanHighOn: _cal.fanHighOn, fanHighOff: _cal.fanHighOff,
             ambient: _cal.ambient, redline: _cal.redline,
             fuelCutEn: _cal.fuelCutEn };
  }
  /* Merge + clamp; each edit takes effect on the running sim immediately.
   * Hysteresis guard: OFF is clamped below its ON (off = on-5 on conflict). */
  function emu_cal_set(patch) {
    if (!patch || typeof patch !== "object") return emu_cal_get();
    if (patch.fanLowOn !== undefined)
      _cal.fanLowOn = clampNum(patch.fanLowOn, 40, 120, _cal.fanLowOn);
    if (patch.fanLowOff !== undefined)
      _cal.fanLowOff = clampNum(patch.fanLowOff, 40, 120, _cal.fanLowOff);
    if (_cal.fanLowOff > _cal.fanLowOn - 1) _cal.fanLowOff = _cal.fanLowOn - 5;
    if (patch.fanHighOn !== undefined)
      _cal.fanHighOn = clampNum(patch.fanHighOn, 40, 120, _cal.fanHighOn);
    if (patch.fanHighOff !== undefined)
      _cal.fanHighOff = clampNum(patch.fanHighOff, 40, 120, _cal.fanHighOff);
    if (_cal.fanHighOff > _cal.fanHighOn - 1) _cal.fanHighOff = _cal.fanHighOn - 5;
    if (patch.ambient !== undefined)
      _cal.ambient = clampNum(patch.ambient, -20, 50, _cal.ambient);
    if (patch.redline !== undefined)
      _cal.redline = Math.round(clampNum(patch.redline, 3000, 9500, _cal.redline));
    if (patch.fuelCutEn !== undefined) _cal.fuelCutEn = patch.fuelCutEn ? 1 : 0;
    return emu_cal_get();
  }

  /* ================================================================
   *  Module export
   * ================================================================ */
  return {
    emu_init: emu_init,
    emu_set_sensor: emu_set_sensor,
    emu_set_mil: emu_set_mil,
    emu_step_ms: emu_step_ms,
    emu_get_pin: emu_get_pin,
    emu_get_adc: emu_get_adc,
    emu_get_port: emu_get_port,
    emu_get_reg: emu_get_reg,
    emu_get_crank_phase: emu_get_crank_phase,
    emu_get_crank_gap: emu_get_crank_gap,
    emu_get_crank_capture: emu_get_crank_capture,
    emu_get_tooth_period_ms: emu_get_tooth_period_ms,
    emu_get_fuel_cut: emu_get_fuel_cut,
    emu_get_inj_duty: emu_get_inj_duty,
    emu_set_pins: emu_set_pins,
    emu_set_key_pos: emu_set_key_pos,
    emu_get_key_pos: emu_get_key_pos,
    emu_set_key_code: emu_set_key_code,
    emu_get_key_code: emu_get_key_code,
    emu_set_immo_code: emu_set_immo_code,
    emu_get_immo: emu_get_immo,
    emu_get_engine_state: emu_get_engine_state,
    emu_get_rpm: emu_get_rpm,
    emu_get_crank_angle: emu_get_crank_angle,
    emu_get_batt_v: emu_get_batt_v,
    emu_get_rest_v: emu_get_rest_v,
    emu_get_soc: emu_get_soc,
    emu_set_soc: emu_set_soc,
    emu_get_load_a: emu_get_load_a,
    emu_get_charging: emu_get_charging,
    emu_get_batt_weak: emu_get_batt_weak,
    emu_get_fan: emu_get_fan,
    emu_get_afterrun: emu_get_afterrun,
    emu_get_coolant: emu_get_coolant,
    emu_set_ect_auto: emu_set_ect_auto,
    emu_get_ect_auto: emu_get_ect_auto,
    emu_get_sensor: emu_get_sensor,
    emu_get_ac: emu_get_ac,
    emu_set_ac_req: emu_set_ac_req,
    emu_get_ac_req: emu_get_ac_req,
    emu_set_brake: emu_set_brake,
    emu_get_brake: emu_get_brake,
    emu_get_oil_low: emu_get_oil_low,
    emu_get_fuel: emu_get_fuel,
    emu_set_fuel: emu_set_fuel,
    emu_get_pump: emu_get_pump,
    emu_cal_get: emu_cal_get,
    emu_cal_set: emu_cal_set
  };
})();

if (typeof module !== "undefined" && module.exports) {
  module.exports = Module;
}

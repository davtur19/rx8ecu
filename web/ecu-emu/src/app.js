/**
 * app.js — RX-8 ECU Emulator webui v2
 *
 * Pure JS, zero deps. Reads pins.json (fetched via fetch("pins.json")), renders
 * the 3-column layout (key panel | viz + tabs | controls), interactive
 * connector pinout with search, text pin inspector, live pin states with
 * sensor sliders, and peripheral register table.
 *
 * Emulator logic lives in emu_core.js — this file is UI only.
 */

"use strict";

/* ======================================================================
 *  Constants
 * ====================================================================== */
const PORT_BASE = 0xFFFFF720;
const ADC_BASE = 0xFFFFE500;
const ATU_BASE = 0xFFFFF400;
const CAN0_BASE = 0xFFFFE400;
const CAN1_BASE = 0xFFFFE600;
const SCI_BASE = 0xFFFFF020;
const BSC_BASE = 0xFFFFEC20;
const WDT_BASE = 0xFFFFEC10;
const INTC_ADDR = 0xFFFFF02E;

/* ======================================================================
 *  State
 * ====================================================================== */
let PINS = [];
let PERIPHERALS = [];
let SCENARIOS = {};
let selectedPin = null;
let sensorState = {
  rpm: 0, ect: 80, iat: 25, map: 20, tps: 0, o2f: 0.45, o2r: 0.45
};
/* Expose to engine_sim.js / can_live.js (they read window.sensorState).
 * `let` at top level does not attach to window, so publish explicitly. */
window.sensorState = sensorState;
window.__emuEngineState = "OFF";
let pinOutputs = {};  // name → live value, populated by computePinStates()
let _booted = false;  // boot() guard: init's fetch path must not double-boot
let _preStart = "ON"; // key position to return to after momentary START
/* Wave A2: ECT slider override. Inactive = the core thermal model owns ECT
 * (coolant heats/cools with load); dragging the ECT slider (or applying a
 * scenario) activates the override so fan crossings can be forced, and the
 * ECT AUTO button releases back to the model. */
let ectOverride = { active: false };
/* Wave A2 calibration persistence. */
const CAL_KEY = "rx8emu.cal.v2";
const CAL_DEFAULTS = { fanLowOn: 95, fanLowOff: 90, fanHighOn: 105,
  fanHighOff: 100, ambient: 20, redline: 9000, fuelCutEn: 1, soc: 100 };

/* ======================================================================
 *  Helpers
 * ====================================================================== */
function voltageToADC10(voltage) {
  const val = Math.round(voltage / 5.0 * 1023);
  return Math.max(0, Math.min(1023, val));
}

function mapRange(value, inMin, inMax, outMin, outMax) {
  return outMin + ((value - inMin) / (inMax - inMin)) * (outMax - outMin);
}

/* ======================================================================
 *  Pin computation — delegates to emu_core.js
 * ====================================================================== */
const SIM_STEP_MS = 10;   // ms of sim time per step
let _simTimer = null;     // real-time sim clock (step only, no DOM render)
function clampSensor(v, min, max, fallback) {
  v = Number(v);
  if (!Number.isFinite(v)) return fallback;
  return Math.max(min, Math.min(max, v));
}

function computePinStates() {
  /* Clamp on the app.js side (emu_core.js is owned by wave3b — do not edit):
   * a NaN or out-of-range sensor must never reach emu_set_sensor. */
  sensorState.rpm = clampSensor(sensorState.rpm, 0, 9000, 800);
  sensorState.ect = clampSensor(sensorState.ect, -20, 120, 80);
  sensorState.iat = clampSensor(sensorState.iat, -20, 60, 25);
  sensorState.map = clampSensor(sensorState.map, 0, 105, 35);
  sensorState.tps = clampSensor(sensorState.tps, 0, 100, 0);
  sensorState.o2f = clampSensor(sensorState.o2f, 0, 1, 0.45);
  sensorState.o2r = clampSensor(sensorState.o2r, 0, 1, 0.45);

  /* Push sensors into the core. ECT is special: the core thermal model
   * owns it unless the slider override is active (emu_set_sensor(1,·) in
   * the core latches the override; emu_set_ect_auto() releases it). */
  Module.emu_set_sensor(0, sensorState.rpm);
  if (ectOverride.active) {
    Module.emu_set_sensor(1, sensorState.ect);
  } else {
    try {
      if (typeof Module.emu_set_ect_auto === "function") Module.emu_set_ect_auto();
      if (typeof Module.emu_get_sensor === "function") {
        const ec = Module.emu_get_sensor(1);
        if (Number.isFinite(ec)) sensorState.ect = Math.round(ec * 10) / 10;
      }
    } catch (e) {}
  }
  Module.emu_set_sensor(2, sensorState.iat);
  Module.emu_set_sensor(3, sensorState.map);
  Module.emu_set_sensor(4, sensorState.tps);
  Module.emu_set_sensor(5, sensorState.o2f);
  Module.emu_set_sensor(6, sensorState.o2r);

  /* Advance SIM_STEP_MS per call — see startSimClock for pacing. */
  Module.emu_step_ms(SIM_STEP_MS);

  /* Read pin voltages from core */
  pinOutputs = {};
  PINS.forEach(p => {
    p._value = Module.emu_get_pin(p.num);
    pinOutputs[p.name] = p._value;
  });
}

/* ======================================================================
 *  Key switch + immobilizer + engine-state badges (Wave A1)
 * ====================================================================== */
function coreState() {
  try {
    if (typeof Module !== "undefined" && Module &&
        typeof Module.emu_get_engine_state === "function") {
      return Module.emu_get_engine_state();
    }
  } catch (e) {}
  return "OFF";
}

function coreImmoOk() {
  try {
    if (typeof Module !== "undefined" && Module &&
        typeof Module.emu_get_immo === "function") {
      return Module.emu_get_immo() === 1;
    }
  } catch (e) {}
  return true;
}

function setKeyPos(pos) {
  try {
    if (typeof Module !== "undefined" && Module &&
        typeof Module.emu_set_key_pos === "function") {
      Module.emu_set_key_pos(pos);
    }
  } catch (e) {}
  document.querySelectorAll(".key-btn").forEach(b => {
    b.classList.toggle("active", b.dataset.keypos === pos);
  });
  try {
    window.__emuKeyPos = pos;
  } catch (e) {}
  refreshBadges();
  return pos;
}

function holdStart(on) {
  const btn = document.getElementById("key-start");
  if (on) {
    try {
      _preStart = (typeof Module !== "undefined" && Module &&
        typeof Module.emu_get_key_pos === "function") ?
        Module.emu_get_key_pos() : "ON";
    } catch (e) { _preStart = "ON"; }
    if (_preStart === "START") _preStart = "ON";
    setKeyPos("START");
    if (btn) btn.classList.add("cranking");
  } else {
    setKeyPos((_preStart === "OFF" || _preStart === "ACC") ? _preStart : "ON");
    if (btn) btn.classList.remove("cranking");
  }
  refresh();
}

function applyKeyCode() {
  const el = document.getElementById("key-code");
  const code = el ? el.value.trim() : "";
  setKeyCode(code);
}

function setKeyCode(code) {
  code = String(code === undefined || code === null ? "" : code);
  try {
    if (typeof Module !== "undefined" && Module &&
        typeof Module.emu_set_key_code === "function") {
      Module.emu_set_key_code(code);
    }
  } catch (e) {}
  /* Calibration panel mirrors the same single key-code store (linked). */
  try {
    const kc = document.getElementById("key-code");
    if (kc && kc.value !== code) kc.value = code;
    const ck = document.getElementById("cal-keycode");
    if (ck && ck.value !== code) ck.value = code;
  } catch (e) {}
  refreshBadges();
  refresh();
}

function refreshBadges() {
  const st = coreState();
  window.__emuEngineState = st;
  const immoOk = coreImmoOk();

  const eb = document.getElementById("engine-state-badge");
  if (eb) {
    eb.textContent = st;
    eb.className = "engine-badge st-" + st.toLowerCase();
  }
  const he = document.getElementById("hdr-engine");
  if (he) {
    he.textContent = "ENGINE: " + st;
    he.className = "hdr-badge" +
      (st === "RUNNING" ? " eng-running" : st === "CRANKING" ? " eng-cranking" : "");
  }
  const ib = document.getElementById("immo-badge");
  if (ib) {
    const keyPos = (function() {
      try {
        return (typeof Module !== "undefined" && Module &&
          typeof Module.emu_get_key_pos === "function") ?
          Module.emu_get_key_pos() : "?";
      } catch (e) { return "?"; }
    })();
    const blocked = !immoOk && (st === "CRANKING" || keyPos === "START" || keyPos === "ON");
    ib.textContent = immoOk ? "IMMO OK" : "IMMO BLOCKED";
    ib.className = "immo-badge " + (immoOk ? "immo-ok" : "immo-blocked");
    void blocked;
  }
  const hi = document.getElementById("hdr-immo");
  if (hi) {
    hi.textContent = immoOk ? "IMMO: OK" : "IMMO: BLOCKED";
    hi.className = "hdr-badge " + (immoOk ? "immo-ok" : "immo-blocked");
  }
}

/* ======================================================================
 *  Tabs
 * ====================================================================== */
function switchTab(name) {
  document.querySelectorAll(".tab-btn").forEach(b => {
    const on = b.dataset.tab === name;
    b.classList.toggle("active", on);
    b.setAttribute("aria-selected", on ? "true" : "false");
  });
  document.querySelectorAll(".tab-page").forEach(p => {
    p.classList.toggle("active", p.id === "tab-" + name);
  });
}

/* ======================================================================
 *  Rendering: Connector pinout (all 96 pins, searchable, scrollable)
 * ====================================================================== */
function pinMatches(p, q) {
  if (!q) return true;
  q = q.toLowerCase();
  return String(p.num).indexOf(q) >= 0 ||
    (p.name && p.name.toLowerCase().indexOf(q) >= 0) ||
    (p.goes_to && p.goes_to.toLowerCase().indexOf(q) >= 0);
}

function applyPinoutFilter() {
  const el = document.getElementById("pinout-search");
  const q = el ? el.value.trim() : "";
  let shown = 0;
  document.querySelectorAll("#tab-pins .pin-cell").forEach(cell => {
    const num = Number(cell.dataset.num);
    const p = PINS.find(x => x.num === num);
    const ok = p ? pinMatches(p, q) : true;
    cell.classList.toggle("hidden", !ok);
    if (ok) shown++;
  });
  const cnt = document.getElementById("pinout-count");
  if (cnt) cnt.textContent = shown + " / " + PINS.length + " pins";
}

function renderPinout() {
  const connA = document.getElementById("connector-a");
  const connB = document.getElementById("connector-b");

  // Clear existing pins (keep header)
  connA.querySelectorAll(".pin-cell").forEach(el => el.remove());
  connB.querySelectorAll(".pin-cell").forEach(el => el.remove());

  PINS.forEach(p => {
    const cell = document.createElement("div");
    cell.className = "pin-cell";
    cell.dataset.type = p.type;
    cell.dataset.num = p.num;
    /* XSS-hardened: pin names come from pins.json — render via textContent. */
    const indicator = document.createElement("div");
    indicator.className = "pin-indicator";
    const numEl = document.createElement("span");
    numEl.className = "pin-num";
    numEl.textContent = String(p.num);
    const nameEl = document.createElement("span");
    nameEl.className = "pin-name";
    nameEl.textContent = p.name;
    cell.append(indicator, numEl, nameEl);
    /* Keyboard a11y: pin cells act as buttons. */
    cell.setAttribute("role", "button");
    cell.setAttribute("tabindex", "0");
    cell.setAttribute("aria-label", `Pin ${p.num}: ${p.name}`);
    const activate = () => selectPin(p);
    cell.addEventListener("click", activate);
    cell.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " " || e.key === "Spacebar") {
        e.preventDefault();
        activate();
      }
    });
    cell.addEventListener("mouseenter", () => showPinInfo(p));
    cell.addEventListener("focus", () => showPinInfo(p));

    if (p.num <= 48) {
      connA.appendChild(cell);
    } else {
      connB.appendChild(cell);
    }
  });
  applyPinoutFilter();
}

/* ======================================================================
 *  Rendering: Pin inspector (Wave A1 replaces the unreadable schematic
 *  miniature with a readable text inspector — defect 6)
 * ====================================================================== */
function regTextFor(pin) {
  if (pin.adc_ch !== undefined) {
    return `ADC ch${pin.adc_ch} @ 0x${(ADC_BASE + pin.adc_ch * 2).toString(16).toUpperCase()}`;
  } else if (pin.port !== undefined) {
    return `PORT${pin.port} bit${pin.bit} @ 0x${(PORT_BASE + pin.port * 8).toString(16).toUpperCase()}`;
  } else if (pin.can) {
    return `${pin.can} @ 0x${(pin.can === "CAN0_H" || pin.can === "CAN0_L" ? CAN0_BASE : CAN1_BASE).toString(16).toUpperCase()}`;
  }
  return "—";
}

function stateTextFor(pin, val) {
  if (pin.type === "digital") {
    /* Fuel-cut display: injectors read LOW during cut but mean CUT. */
    const fuelCut = (typeof Module !== "undefined" && Module &&
      typeof Module.emu_get_fuel_cut === "function") ? Module.emu_get_fuel_cut() : 0;
    if (fuelCut && pin.name && pin.name.indexOf("INJ") === 0) {
      return { text: "CUT (fuel cut at redline)", color: "var(--red)" };
    }
    return val ?
      { text: "HIGH (1)", color: "var(--green)" } :
      { text: "LOW (0)", color: "var(--muted)" };
  } else if (pin.type === "analog") {
    return { text: `${val.toFixed(3)}V (ADC: ${voltageToADC10(val)})`, color: "var(--cyan)" };
  } else if (pin.type === "power") {
    return { text: `${val.toFixed(1)}V`, color: "var(--yellow)" };
  } else if (pin.type === "can") {
    return val > 0 ?
      { text: "Bus active", color: "var(--cyan)" } :
      { text: "Bus idle", color: "var(--muted)" };
  }
  return { text: "—", color: "var(--muted)" };
}

function showPinInfo(pin) {
  document.getElementById("info-title").textContent = `Pin ${pin.num}: ${pin.name}`;
  document.getElementById("info-type").textContent = pin.type.toUpperCase();
  document.getElementById("info-dir").textContent = pin.dir === "in" ? "Input" : pin.dir === "out" ? "Output" : pin.dir === "io" ? "Bidirectional" : "N/A";
  document.getElementById("info-goes").textContent = pin.goes_to.replace(/_/g, " ");
  document.getElementById("info-voltage").textContent = `${pin.voltage[0]}–${pin.voltage[1]}V`;
  document.getElementById("info-reg").textContent = regTextFor(pin);

  const st = stateTextFor(pin, pin._value || 0);
  const sel = document.getElementById("info-state");
  sel.textContent = st.text;
  sel.style.color = st.color;
  document.getElementById("info-detail").style.display = "grid";
  const hint = document.querySelector("#pin-inspector .key-hint");
  if (hint) hint.style.display = "none";
}

function selectPin(pin) {
  // Deselect previous
  document.querySelectorAll(".pin-cell.selected").forEach(el => el.classList.remove("selected"));

  if (selectedPin && selectedPin.num === pin.num) {
    selectedPin = null;
    document.getElementById("info-title").textContent = "No pin selected";
    document.getElementById("info-detail").style.display = "none";
    const hint = document.querySelector("#pin-inspector .key-hint");
    if (hint) hint.style.display = "";
    return;
  }

  selectedPin = pin;
  document.querySelectorAll(`.pin-cell[data-num="${pin.num}"]`).forEach(cell => cell.classList.add("selected"));
  showPinInfo(pin);
}

/* ======================================================================
 *  Rendering: Live pin states (dynamic HIGH/LOW/CUT list — defect 4)
 * ====================================================================== */
function renderStates() {
  const list = document.getElementById("states-list");
  list.innerHTML = "";

  // Only show non-NC, non-GND pins
  const activePins = PINS.filter(p => p.type !== "nc" && p.type !== "gnd");
  const qEl = document.getElementById("pinlive-search");
  const q = qEl ? qEl.value.trim() : "";

  activePins.forEach(p => {
    if (!pinMatches(p, q)) return;
    const val = p._value || 0;
    const item = document.createElement("div");
    item.className = "state-item";
    item.dataset.num = p.num;
    item.setAttribute("role", "button");
    item.setAttribute("tabindex", "0");
    item.setAttribute("aria-label", `Inspect pin ${p.num} ${p.name}`);

    let displayVal, barPct, barColor, valColor;
    valColor = "";
    if (p.type === "digital") {
      /* Injectors pulse with duty (idle flickers, high rpm mostly HIGH)
       * and read CUT during redline fuel cut — the visible redline change. */
      const fuelCut = (typeof Module !== "undefined" && Module &&
        typeof Module.emu_get_fuel_cut === "function") ? Module.emu_get_fuel_cut() : 0;
      if (fuelCut && p.name && p.name.indexOf("INJ") === 0) {
        displayVal = "CUT";
        barPct = 0;
        barColor = "var(--red)";
        valColor = "var(--red)";
      } else {
        displayVal = val ? "HIGH" : "LOW";
        barPct = val ? 100 : 0;
        barColor = val ? "var(--green)" : "var(--muted)";
      }
    } else if (p.type === "analog") {
      displayVal = `${val.toFixed(2)}V`;
      barPct = (val / 5) * 100;
      barColor = "var(--accent)";
    } else if (p.type === "power") {
      displayVal = `${val.toFixed(1)}V`;
      barPct = (val / 16) * 100;
      barColor = "var(--yellow)";
    } else if (p.type === "can") {
      displayVal = val > 0 ? "Active" : "Idle";
      barPct = val > 0 ? 100 : 0;
      barColor = "var(--cyan)";
    } else if (p.type === "sci") {
      displayVal = val > 0 ? "Idle" : "Off";
      barPct = val > 0 ? 50 : 0;
      barColor = "var(--purple)";
    } else {
      displayVal = "—";
      barPct = 0;
      barColor = "var(--muted)";
    }

    /* XSS-hardened: pin names come from pins.json — render via textContent. */
    const nameDiv = document.createElement("div");
    nameDiv.className = "state-name";
    nameDiv.style.color = getTypeColor(p.type);
    nameDiv.textContent = p.name;
    const barWrap = document.createElement("div");
    barWrap.className = "state-bar";
    const barFill = document.createElement("div");
    barFill.className = "state-bar-fill";
    barFill.style.width = `${barPct}%`;
    barFill.style.background = barColor;
    barWrap.appendChild(barFill);
    const valDiv = document.createElement("div");
    valDiv.className = "state-value";
    valDiv.textContent = displayVal;
    if (valColor) valDiv.style.color = valColor;
    item.append(nameDiv, barWrap, valDiv);
    const pick = () => selectPin(p);
    item.addEventListener("click", pick);
    item.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pick(); }
    });
    list.appendChild(item);
  });
}

function getTypeColor(type) {
  const colors = {
    power:"#e3b341", gnd:"#8b96a3", analog:"#4d7cff", digital:"#7ee787",
    can:"#39c5cf", sci:"#bc8cff", nc:"#333c4a"
  };
  return colors[type] || "#8b96a3";
}

/* ======================================================================
 *  Rendering: Scenario presets (key=ON + throttle profile — Wave A1)
 * ====================================================================== */
function renderScenarios() {
  const container = document.getElementById("scenarios");
  container.innerHTML = "";

  Object.entries(SCENARIOS).forEach(([key, sc]) => {
    const btn = document.createElement("button");
    btn.className = "scenario-btn";
    /* XSS-hardened: scenario keys/descriptions come from pins.json. */
    const scName = document.createElement("div");
    scName.className = "sc-name";
    scName.textContent = key.toUpperCase();
    const scDesc = document.createElement("div");
    scDesc.className = "sc-desc";
    scDesc.textContent = sc.desc;
    btn.append(scName, scDesc);
    btn.addEventListener("click", () => applyScenario(key));
    container.appendChild(btn);
  });
}

function applyScenario(key) {
  const sc = SCENARIOS[key];
  if (!sc) return;
  /* Wave A1: presets set key=ON + throttle profile. They never crank —
   * HOLD TO START is the only start mechanism. */
  if (coreState() === "OFF") setKeyPos("ON");
  sensorState.rpm = sc.rpm;
  sensorState.ect = sc.ect;
  sensorState.iat = sc.iat;
  sensorState.map = sc.map;
  sensorState.tps = sc.tps;
  if (sc.o2f !== undefined) sensorState.o2f = sc.o2f;
  if (sc.o2r !== undefined) sensorState.o2r = sc.o2r;
  /* Wave A2: presets force an ECT override (AUTO releases back to the
   * thermal model); O2/IAT manual holds let the value stick ~5 s. */
  ectOverride.active = true;
  manualHold("o2"); manualHold("iat");
  /* Keep the engine sim from pulling rpm away from the scenario value:
   * drive its throttle from the scenario rpm (neutral rev, load cleared). */
  try {
    if (typeof window.__setSimFromRPM === "function") window.__setSimFromRPM(sc.rpm);
    else if (typeof EngineSim !== "undefined" && EngineSim.setFromRPM) EngineSim.setFromRPM(sc.rpm);
  } catch (e) {}
  if (document.activeElement && document.activeElement.blur) document.activeElement.blur();
  updateSliders();
  refresh();
  // Highlight active scenario
  document.querySelectorAll(".scenario-btn").forEach((btn, i) => {
    btn.classList.toggle("active", Object.keys(SCENARIOS)[i] === key);
  });
}

/* ======================================================================
 *  Rendering: Sensor sliders (Dashboard) + O2R tab
 * ====================================================================== */
function renderSliders() {
  const container = document.getElementById("sliders");
  container.innerHTML = "";

  const sliders = [
    {key:"rpm",  label:"RPM",   min:0, max:9000, step:100, unit:""},
    {key:"ect",  label:"ECT",   min:-20,max:120, step:1,   unit:"°C"},
    {key:"iat",  label:"IAT",   min:-20,max:60,  step:1,   unit:"°C"},
    {key:"map",  label:"MAP",   min:0,  max:105, step:1,   unit:"kPa"},
    {key:"tps",  label:"TPS",   min:0,  max:100, step:1,   unit:"%"},
    {key:"o2f",  label:"O2-F",  min:0,  max:1,   step:0.01,unit:"V"},
    {key:"o2r",  label:"O2-R",  min:0,  max:1,   step:0.01,unit:"V"},
  ];

  sliders.forEach(s => {
    const group = document.createElement("div");
    group.className = "slider-group";
    group.innerHTML = `
      <label for="slider-${s.key}">${s.label} <span id="val-${s.key}">${sensorState[s.key]}${s.unit}</span></label>
      <input type="range" min="${s.min}" max="${s.max}" step="${s.step}" value="${sensorState[s.key]}" id="slider-${s.key}" aria-label="${s.label} sensor">
    `;
    container.appendChild(group);

    const input = group.querySelector("input");
    input.addEventListener("input", () => {
      const v = Number(input.value);
      if (!Number.isFinite(v)) return;
      sensorState[s.key] = Math.max(s.min, Math.min(s.max, v));
      document.getElementById(`val-${s.key}`).textContent = `${sensorState[s.key]}${s.unit}`;
      /* Wave A2: a hand-dragged ECT slider overrides the thermal model
       * (fan crossings can be forced); O2/IAT edits hold ~5 s before
       * engine_sim dynamics resume. */
      if (s.key === "ect") ectOverride.active = true;
      if (s.key === "o2f" || s.key === "o2r") manualHold("o2");
      if (s.key === "iat") manualHold("iat");
      /* A hand-dragged RPM slider must stick: the engine-sim tick pulls
       * rpm toward its throttle target, so drive the sim throttle from the
       * slider value (inverse map, load cleared for a neutral rev). */
      if (s.key === "rpm") {
        try {
          if (typeof window.__setSimFromRPM === "function") window.__setSimFromRPM(sensorState[s.key]);
          else if (typeof EngineSim !== "undefined" && EngineSim.setFromRPM) EngineSim.setFromRPM(sensorState[s.key]);
        } catch (e) {}
      }
      /* A manual slider move leaves the scenario it came from: clear highlight. */
      document.querySelectorAll(".scenario-btn").forEach(b => b.classList.remove("active"));
      refresh();
    });
  });
}

function writeSensor(key, v, min, max) {
  v = Number(v);
  if (!Number.isFinite(v)) return;
  sensorState[key] = Math.max(min, Math.min(max, v));
  if (key === "ect") ectOverride.active = true;
  if (key === "o2f" || key === "o2r") manualHold("o2");
  if (key === "iat") manualHold("iat");
  document.querySelectorAll(".scenario-btn").forEach(b => b.classList.remove("active"));
  updateSliders();
  refresh();
}

/* Tell engine_sim.js that O2/IAT were hand-driven (holds dynamics ~5 s). */
function manualHold(which) {
  try {
    if (which === "o2" && typeof window.__o2ManualHold === "function") window.__o2ManualHold();
    if (which === "iat" && typeof window.__iatManualHold === "function") window.__iatManualHold();
  } catch (e) {}
}

function updateSliders() {
  const units = {rpm:"",ect:"°C",iat:"°C",map:"kPa",tps:"%",o2f:"V",o2r:"V"};
  ["rpm","ect","iat","map","tps","o2f","o2r"].forEach(key => {
    const slider = document.getElementById(`slider-${key}`);
    if (slider && document.activeElement !== slider) {
      const v = Number(sensorState[key]);
      if (Number.isFinite(v)) {
        slider.value = v;
        const valEl = document.getElementById(`val-${key}`);
        if (valEl) valEl.textContent = `${sensorState[key]}${units[key]}`;
      }
    }
  });
  /* O2R-tab mirrors */
  [["o2f-tab", "o2f", "o2f-tab-val"], ["o2r-tab", "o2r", "o2r-tab-val"]].forEach(([id, key, valId]) => {
    const s = document.getElementById(id);
    if (s && document.activeElement !== s) s.value = sensorState[key];
    const ve = document.getElementById(valId);
    if (ve) ve.textContent = Number(sensorState[key]).toFixed(2) + "V";
  });
  /* O2 live readouts (voltage + ADC) */
  try {
    if (typeof Module !== "undefined" && Module && typeof Module.emu_get_adc === "function") {
      const f = document.getElementById("o2f-read");
      if (f) f.textContent = Number(sensorState.o2f).toFixed(2) + " V · ADC " + Module.emu_get_adc(4);
      const r = document.getElementById("o2r-read");
      if (r) r.textContent = Number(sensorState.o2r).toFixed(2) + " V · ADC " + Module.emu_get_adc(5);
    }
  } catch (e) {}
}

/* ======================================================================
 *  Rendering: Register view — reads from emu_core
 * ====================================================================== */
function renderRegisters() {
  const container = document.getElementById("reg-table");
  const rows = [];

  // ADC channels (0-7)
  for (let ch = 0; ch < 8; ch++) {
    const addr = ADC_BASE + ch * 2;
    const val = Module.emu_get_adc(ch);
    rows.push({periph:"ADC", addr:addr, name:`CH${ch}`, value:val, fmt: `0x${(val << 6).toString(16).toUpperCase().padStart(4,"0")}`});
  }

  // Port latches, full 16 bits (port 5 bit 7 = MIL/CHECK_ENG)
  for (let p = 0; p < 6; p++) {
    const addr = PORT_BASE + p * 8;
    let val = 0;
    for (let b = 0; b < 16; b++) val |= (Module.emu_get_port(p, b) << b);
    rows.push({periph:"PORT", addr:addr, name:`P${p}`, value:val, fmt:`0x${val.toString(16).toUpperCase().padStart(4,"0")}`});
  }

  // ATU timer
  rows.push({periph:"ATU", addr:0xFFFFF434, name:"CAPT", value:Module.emu_get_reg(0xFFFFF434), fmt:"0x00000000"});

  // CAN0/1 status
  rows.push({periph:"CAN0", addr:CAN0_BASE, name:"CTL", value:Module.emu_get_reg(CAN0_BASE), fmt:Module.emu_get_reg(CAN0_BASE)?"0x01":"0x00"});
  rows.push({periph:"CAN1", addr:CAN1_BASE, name:"CTL", value:Module.emu_get_reg(CAN1_BASE), fmt:Module.emu_get_reg(CAN1_BASE)?"0x01":"0x00"});

  // WDT
  rows.push({periph:"WDT", addr:WDT_BASE, name:"TCSR", value:Module.emu_get_reg(WDT_BASE), fmt:"0x00"});

  let html = `<table><thead><tr><th>Periph</th><th>Address</th><th>Register</th><th>Value</th><th>Hex</th></tr></thead><tbody>`;
  rows.forEach(r => {
    html += `<tr><td>${r.periph}</td><td class="reg-addr">0x${r.addr.toString(16).toUpperCase()}</td><td>${r.name}</td><td>${r.value}</td><td class="reg-val">${r.fmt}</td></tr>`;
  });
  html += `</tbody></table>`;
  container.innerHTML = html;
}

/* ======================================================================
 *  Crank tooth table (Crank tab detail)
 * ====================================================================== */
function buildCrankTeeth() {
  const tbl = document.getElementById("crank-teeth");
  if (!tbl) return;
  const tr = tbl.querySelector("tr");
  tr.innerHTML = "";
  for (let i = 0; i < 20; i++) {
    const td = document.createElement("td");
    td.textContent = (i === 5 || i === 15) ? "×" : String(i);
    td.title = (i === 5 || i === 15) ? "Gap tooth " + i : "Tooth " + i;
    tr.appendChild(td);
  }
}

/* ======================================================================
 *  Wave A2: live vehicle panel + calibration menu
 * ====================================================================== */
function coreNum(fn, fallback) {
  try {
    if (typeof Module !== "undefined" && Module && typeof Module[fn] === "function") {
      const v = Module[fn]();
      if (typeof v === "number" && Number.isFinite(v)) return v;
    }
  } catch (e) {}
  return fallback;
}

function setText(id, txt) {
  const el = document.getElementById(id);
  if (el) el.textContent = txt;
}

function refreshVehicle() {
  const hasA2 = (typeof Module !== "undefined" && Module &&
    typeof Module.emu_get_batt_v === "function");
  if (!hasA2) return;
  const V = coreNum("emu_get_batt_v", 0);
  const soc = coreNum("emu_get_soc", 0);
  const load = coreNum("emu_get_load_a", 0);
  const charging = coreNum("emu_get_charging", 0) === 1;
  const weak = coreNum("emu_get_batt_weak", 0) === 1;
  const after = coreNum("emu_get_afterrun", 0) === 1;
  const coolant = coreNum("emu_get_coolant", 0);
  const fan0 = coreNum("emu_get_fan", 0) === 1;
  const fan1 = (function() {
    try { return Module.emu_get_fan(1) === 1; } catch (e) { return false; }
  })();
  const fuel = coreNum("emu_get_fuel", 0);
  const oilLow = coreNum("emu_get_oil_low", 0) === 1;
  const ac = coreNum("emu_get_ac", 0) === 1;
  const acReq = coreNum("emu_get_ac_req", 0) === 1;
  const brake = coreNum("emu_get_brake", 0) === 1;

  setText("batt-readout", V.toFixed(2) + " V");
  setText("batt-soc", soc.toFixed(0) + "% (rest " +
    coreNum("emu_get_rest_v", 0).toFixed(2) + " V)");
  setText("batt-load", load.toFixed(1) + " A");
  setText("batt-state", charging ? "CHARGING" :
    (coreState() === "CRANKING" ? "CRANKING" : "ON BATTERY"));
  const wb = document.getElementById("batt-weak");
  if (wb) wb.style.display = weak ? "" : "none";
  const ab = document.getElementById("afterrun-badge");
  if (ab) ab.style.display = after ? "" : "none";

  setText("veh-coolant", coolant.toFixed(1) + " °C" + (ectOverride.active ? " (override)" : " (model)"));
  setText("veh-fans", fan1 ? "HIGH" : (fan0 ? "LOW" : "OFF"));
  setText("fuel-readout", fuel.toFixed(0) + "%");
  setText("oil-readout", oilLow ? "LOW" : "OK");
  setText("ac-readout", ac ? "ENGAGED" : (acReq ? "REQ (idle)" : "OFF"));
  const acB = document.getElementById("ac-req-btn");
  if (acB) {
    acB.textContent = "A/C REQ: " + (acReq ? "ON" : "OFF");
    acB.classList.toggle("active", acReq);
    acB.setAttribute("aria-pressed", acReq ? "true" : "false");
  }
  const brB = document.getElementById("brake-btn");
  if (brB) {
    brB.textContent = "BRAKE: " + (brake ? "ON" : "OFF");
    brB.classList.toggle("active", brake);
    brB.setAttribute("aria-pressed", brake ? "true" : "false");
  }

  /* ECT mode line + AUTO button. */
  setText("ect-mode", ectOverride.active ?
    ("ECT: OVERRIDE @ " + Number(sensorState.ect).toFixed(0) + " °C (slider)") :
    ("ECT: thermal model (AUTO) @ " + coolant.toFixed(1) + " °C"));
  setText("ect-auto-btn", ectOverride.active ? "Release to AUTO" : "ECT: AUTO");

  /* Calibration live-values line. */
  setText("cal-live", "live: coolant " + coolant.toFixed(1) + " °C · fans " +
    (fan1 ? "HIGH" : (fan0 ? "LOW" : "OFF")) + " · " + V.toFixed(2) + " V · SoC " +
    soc.toFixed(0) + "%" + (after ? " · AFTER-RUN" : "") + (weak ? " · WEAK BATT" : ""));
}

function persistCal(obj) {
  try { localStorage.setItem(CAL_KEY, JSON.stringify(obj)); } catch (e) {}
}

function readCalInputs() {
  const num = (id, fb) => {
    const el = document.getElementById(id);
    if (!el) return fb;
    const v = Number(el.value);
    return Number.isFinite(v) ? v : fb;
  };
  const fc = document.getElementById("cal-fuelcut");
  return {
    fanLowOn: num("cal-fanlo-on", CAL_DEFAULTS.fanLowOn),
    fanLowOff: num("cal-fanlo-off", CAL_DEFAULTS.fanLowOff),
    fanHighOn: num("cal-fanhi-on", CAL_DEFAULTS.fanHighOn),
    fanHighOff: num("cal-fanhi-off", CAL_DEFAULTS.fanHighOff),
    ambient: num("cal-ambient", CAL_DEFAULTS.ambient),
    redline: num("cal-redline", CAL_DEFAULTS.redline),
    fuelCutEn: fc ? (fc.checked ? 1 : 0) : 1,
    soc: num("cal-soc", CAL_DEFAULTS.soc)
  };
}

function writeCalInputs(c) {
  const set = (id, v) => { const el = document.getElementById(id); if (el) el.value = v; };
  set("cal-fanlo-on", c.fanLowOn); set("cal-fanlo-off", c.fanLowOff);
  set("cal-fanhi-on", c.fanHighOn); set("cal-fanhi-off", c.fanHighOff);
  set("cal-ambient", c.ambient); set("cal-redline", c.redline);
  set("cal-soc", c.soc);
  setText("cal-soc-val", Math.round(c.soc) + "%");
  const fc = document.getElementById("cal-fuelcut");
  if (fc) fc.checked = !!c.fuelCutEn;
}

/* Push calibration to the running sim immediately + persist. */
function applyCalFromInputs() {
  const c = readCalInputs();
  try {
    if (typeof Module !== "undefined" && Module) {
      if (typeof Module.emu_cal_set === "function") {
        const applied = Module.emu_cal_set(c);
        /* Echo the clamped core values back so the form never lies. */
        c.fanLowOn = applied.fanLowOn; c.fanLowOff = applied.fanLowOff;
        c.fanHighOn = applied.fanHighOn; c.fanHighOff = applied.fanHighOff;
        c.ambient = applied.ambient; c.redline = applied.redline;
        c.fuelCutEn = applied.fuelCutEn;
      }
      if (typeof Module.emu_set_soc === "function") c.soc = Module.emu_set_soc(c.soc);
    }
  } catch (e) {}
  writeCalInputs(c);
  persistCal(c);
  refreshVehicle();
  return c;
}

function loadCal() {
  let c = Object.assign({}, CAL_DEFAULTS);
  try {
    const raw = localStorage.getItem(CAL_KEY);
    if (raw) {
      const saved = JSON.parse(raw);
      if (saved && typeof saved === "object") {
        Object.keys(CAL_DEFAULTS).forEach(k => {
          if (saved[k] !== undefined) c[k] = saved[k];
        });
      }
    }
  } catch (e) {}
  writeCalInputs(c);
  /* Push through the same path (clamp + core + persist). */
  return applyCalFromInputs();
}

/* ======================================================================
 *  Refresh cycle
 * ====================================================================== */
function refresh() {
  computePinStates();
  renderStates();
  renderRegisters();
  updateSliders();
  refreshBadges();
  refreshVehicle();
  if (selectedPin) showPinInfo(selectedPin);
}
/* Published for the engine-sim tick (throttled live-view sync). */
window.refresh = refresh;
window.updateSliders = updateSliders;

/* ======================================================================
 *  Init
 * ====================================================================== */
function init() {
  /* pins.json is fetched exclusively: a <script src="pins.json"> tag leaves
   * textContent empty in spec-compliant browsers, so never rely on it. */
  fetch("pins.json").then(function(r) {
    if (!r.ok) throw new Error("HTTP " + r.status);
    return r.json();
  }).then(function(d) {
    PINS = d.pins;
    PERIPHERALS = d.peripherals || [];
    SCENARIOS = d.scenarios || {};
    boot();
  }).catch(function(err) {
    const host = document.getElementById("states-list") || document.body;
    const msg = document.createElement("div");
    msg.className = "emu-load-error";
    msg.setAttribute("role", "alert");
    msg.textContent = "Failed to load pins.json: " + (err && err.message ? err.message : String(err));
    host.appendChild(msg);
  });
}

/* Real-time sim clock: step the core (no DOM work) so sim time tracks
 * wall time. Rendering stays on the existing paths (engine-tick sync,
 * slider/scenario/key input). Without this the core would advance only
 * SIM_STEP_MS per render (~6Hz), making hold-to-START take ~13 s. */
function startSimClock() {
  if (_simTimer) clearInterval(_simTimer);
  _simTimer = setInterval(() => {
    try { computePinStates(); } catch (e) {}
  }, SIM_STEP_MS);
}

function wireStaticControls() {
  /* Tabs */
  document.querySelectorAll(".tab-btn").forEach(b => {
    b.addEventListener("click", () => {
      switchTab(b.dataset.tab);
      if (document.activeElement && document.activeElement.blur) document.activeElement.blur();
    });
  });
  /* Key position buttons */
  document.querySelectorAll(".key-btn").forEach(b => {
    b.addEventListener("click", () => {
      setKeyPos(b.dataset.keypos);
      refresh();
      if (document.activeElement && document.activeElement.blur) document.activeElement.blur();
    });
  });
  /* Momentary START: press-and-hold (mouse + touch + keyboard) */
  const start = document.getElementById("key-start");
  if (start) {
    start.addEventListener("pointerdown", (e) => { e.preventDefault(); holdStart(true); });
    ["pointerup", "pointerleave", "pointercancel"].forEach(ev =>
      start.addEventListener(ev, () => holdStart(false)));
    start.addEventListener("keydown", (e) => {
      if ((e.key === "Enter" || e.key === " ") && !e.repeat) { e.preventDefault(); holdStart(true); }
    });
    start.addEventListener("keyup", (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); holdStart(false); }
    });
  }
  /* Key code */
  const apply = document.getElementById("key-apply");
  if (apply) apply.addEventListener("click", applyKeyCode);
  const code = document.getElementById("key-code");
  if (code) code.addEventListener("keydown", (e) => {
    if (e.key === "Enter") applyKeyCode();
  });
  /* Wave A2: ECT AUTO release, A/C + brake toggles, refuel */
  const ectAuto = document.getElementById("ect-auto-btn");
  if (ectAuto) ectAuto.addEventListener("click", () => {
    ectOverride.active = false;
    try {
      if (typeof Module !== "undefined" && Module &&
          typeof Module.emu_set_ect_auto === "function") Module.emu_set_ect_auto();
    } catch (e) {}
    refresh();
    if (document.activeElement && document.activeElement.blur) document.activeElement.blur();
  });
  const acB = document.getElementById("ac-req-btn");
  if (acB) acB.addEventListener("click", () => {
    try {
      if (typeof Module !== "undefined" && Module &&
          typeof Module.emu_set_ac_req === "function") {
        Module.emu_set_ac_req(!Module.emu_get_ac_req());
      }
    } catch (e) {}
    refresh();
    if (document.activeElement && document.activeElement.blur) document.activeElement.blur();
  });
  const brB = document.getElementById("brake-btn");
  if (brB) brB.addEventListener("click", () => {
    try {
      if (typeof Module !== "undefined" && Module &&
          typeof Module.emu_set_brake === "function") {
        Module.emu_set_brake(!Module.emu_get_brake());
      }
    } catch (e) {}
    refresh();
    if (document.activeElement && document.activeElement.blur) document.activeElement.blur();
  });
  const rfB = document.getElementById("refuel-btn");
  if (rfB) rfB.addEventListener("click", () => {
    try {
      if (typeof Module !== "undefined" && Module &&
          typeof Module.emu_set_fuel === "function") Module.emu_set_fuel(100);
    } catch (e) {}
    refresh();
    if (document.activeElement && document.activeElement.blur) document.activeElement.blur();
  });
  /* Wave A2: calibration inputs (numbers commit on change, slider/check live) */
  ["cal-fanlo-on", "cal-fanlo-off", "cal-fanhi-on", "cal-fanhi-off",
   "cal-ambient", "cal-redline"].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.addEventListener("change", applyCalFromInputs);
  });
  const socEl = document.getElementById("cal-soc");
  if (socEl) {
    socEl.addEventListener("input", () => {
      setText("cal-soc-val", Math.round(Number(socEl.value) || 0) + "%");
      applyCalFromInputs();
    });
  }
  const fcEl = document.getElementById("cal-fuelcut");
  if (fcEl) fcEl.addEventListener("change", applyCalFromInputs);
  const ckEl = document.getElementById("cal-keycode");
  if (ckEl) {
    ckEl.addEventListener("keydown", (e) => {
      if (e.key === "Enter") setKeyCode(ckEl.value.trim());
    });
    ckEl.addEventListener("change", () => setKeyCode(ckEl.value.trim()));
  }
  const rsEl = document.getElementById("cal-reset");
  if (rsEl) rsEl.addEventListener("click", () => {
    writeCalInputs(Object.assign({}, CAL_DEFAULTS));
    applyCalFromInputs();
    if (document.activeElement && document.activeElement.blur) document.activeElement.blur();
  });
  /* Pinout + live-pin filters */
  const pf = document.getElementById("pinout-search");
  if (pf) pf.addEventListener("input", applyPinoutFilter);
  const lf = document.getElementById("pinlive-search");
  if (lf) lf.addEventListener("input", renderStates);
  /* O2R tab sliders */
  const o2f = document.getElementById("o2f-tab");
  if (o2f) o2f.addEventListener("input", () => writeSensor("o2f", o2f.value, 0, 1));
  const o2r = document.getElementById("o2r-tab");
  if (o2r) o2r.addEventListener("input", () => writeSensor("o2r", o2r.value, 0, 1));
}

function boot() {
  if (_booted) return;
  _booted = true;
  // Initialize the emulator core with pin data (boots key-OFF, engine OFF)
  Module.emu_init();
  Module.emu_set_pins(PINS);

  wireStaticControls();
  renderPinout();
  renderScenarios();
  renderSliders();
  buildCrankTeeth();
  setKeyPos("OFF");
  loadCal(); // Wave A2: stored calibration -> inputs -> running sim
  startSimClock();
  refresh();

  // Initialize engine simulator and CAN monitor
  if (typeof EngineSim !== "undefined") {
    EngineSim.init("engine-sim-container");
  }
  if (typeof CANLive !== "undefined") {
    CANLive.init("can-monitor-container");
  }
}

document.addEventListener("DOMContentLoaded", init);

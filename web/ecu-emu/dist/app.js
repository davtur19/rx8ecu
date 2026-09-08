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
  renderPinLive(pin);
}

/* ======================================================================
 *  Wave A3: per-pin live digital data + waveform in the Pin Inspector
 * ====================================================================== */
function renderPinLive(pin) {
  const wrap = document.getElementById("pin-livedata");
  if (!wrap) return;
  let d = null;
  try {
    if (typeof PinData !== "undefined") d = PinData.liveFor(pin);
  } catch (e) { d = null; }
  if (!d) { wrap.style.display = "none"; return; }
  wrap.style.display = "";
  const body = document.getElementById("livedata-body");
  if (body) {
    body.innerHTML = "";
    d.rows.forEach(r => {
      const row = document.createElement("div");
      row.className = "livedata-row";
      const k = document.createElement("span");
      k.className = "livedata-k";
      k.textContent = r[0];
      const v = document.createElement("span");
      v.className = "livedata-v";
      v.textContent = r[1];
      if (d.kind === "can" && r[0] === "frames") {
        /* Activity indicator: flips each refresh while frames flow. */
        const flip = wrap.dataset.flip === "1" ? "0" : "1";
        wrap.dataset.flip = flip;
        const dot = document.createElement("span");
        dot.id = "can-act";
        dot.className = "can-act" + (flip === "1" ? " on" : "");
        dot.title = "blinks while CAN frames flow";
        v.appendChild(document.createTextNode(" "));
        v.appendChild(dot);
      }
      row.append(k, v);
      body.appendChild(row);
    });
  }
  const note = document.getElementById("livedata-note");
  if (note) {
    note.textContent = d.note || "";
    note.style.display = d.note ? "" : "none";
  }
  const cv = document.getElementById("pin-wave");
  const cap = document.getElementById("wave-cap");
  let caption = "";
  try {
    if (cv && typeof PinData !== "undefined") caption = PinData.drawWave(cv, pin);
  } catch (e) { caption = ""; }
  if (cap) cap.textContent = caption;
}

function selectPin(pin) {
  // Deselect previous
  document.querySelectorAll(".pin-cell.selected").forEach(el => el.classList.remove("selected"));

  if (selectedPin && selectedPin.num === pin.num) {
    selectedPin = null;
    document.getElementById("info-title").textContent = "No pin selected";
    document.getElementById("info-detail").style.display = "none";
    const live = document.getElementById("pin-livedata");
    if (live) live.style.display = "none";
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
    const mainDiv = document.createElement("div");
    mainDiv.textContent = displayVal;
    if (valColor) mainDiv.style.color = valColor;
    valDiv.appendChild(mainDiv);
    /* Wave A3: per-row live data snippet (duty/freq, CAN bytes+counter). */
    try {
      if (typeof PinData !== "undefined") {
        const snip = PinData.rowSnippet(p);
        if (snip) {
          const subDiv = document.createElement("div");
          subDiv.className = "state-sub";
          subDiv.textContent = snip;
          valDiv.appendChild(subDiv);
        }
      }
    } catch (e) {}
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

  // ATU timer (review fix: the hex column used to be a hardcoded
  // "0x00000000" and never showed the live capture value incl. gap bit)
  const atuCapt = Module.emu_get_reg(0xFFFFF434);
  rows.push({periph:"ATU", addr:0xFFFFF434, name:"CAPT", value:atuCapt,
    fmt:"0x"+(atuCapt >>> 0).toString(16).toUpperCase().padStart(8,"0")});

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
    /* Wave A3: feed the waveform sampler (no DOM work here). */
    try {
      if (typeof PinData !== "undefined") PinData.tick(selectedPin);
    } catch (e) {}
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

/* ======================================================================
 *  Wave A3: live digital data on pins ("if digital data passes on a PIN,
 *  I want to see it" — not just static HIGH/LOW).
 *
 *  CAN  (CANH/CANL/MSCANH/MSCANL): last live frame bytes in hex from
 *         can_live.js (real frames, never invented) + TX/RX counters.
 *         Single-bus sim model: all four pins show the same live stream,
 *         labeled as such.
 *  SCI  (TXD/RXD): no SCI/UART traffic is simulated (regs read 0x00) →
 *         register state + explicit "no traffic simulated" note.
 *  PWM  (INJ1-4): live duty % + pulse width ms + freq Hz from the
 *         injector model (emu_get_inj_duty + rpm + redline cal).
 *  PWM  (COIL1-4): 8%-window duty + pulse width + freq from live rpm.
 *  VEH_SPD: rpm-derived pulse frequency, labeled as a digital proxy.
 *  Other digitals: live level + real source (fan hysteresis, pump
 *         prime, MIL latch, key, dash toggles). BSC pins are unmapped by
 *         design → static 0, said explicitly (fail-closed, not invented).
 *
 *  Waveform: PWM/VSS draw an analytic pulse train from the live
 *  duty/freq (a 6 Hz sampler could never resolve a 150 Hz train);
 *  CAN draws a 2 s raster from real frame timestamps; slow digitals
 *  draw a 2 s sampled step plot (100 Hz sim-clock sampling); SCI and
 *  unmapped pins draw a flat line + note.
 * ====================================================================== */
var PinData = (function() {

  var HIST_MAX = 200;      // 2 s @ 100 Hz sim-clock tick
  var WAVE_WIN_MS = 2000;  // waveform window for CAN raster + step plot
  var COIL_DUTY = 0.08;    // per-coil window as a fraction of one rev

  var _hist = [];          // sampled 0/1 for the selected slow-digital pin
  var _histKey = "";       // pin name the history belongs to
  var _canEvents = [];     // { t, dir } pruned to the waveform window
  var _canIdx = 0;         // CAN frames consumed so far
  var _lastTx = -1, _lastRx = -1;  // last consumed CAN counters

  function coreNumA3(fn, fb) {
    try {
      if (typeof Module !== "undefined" && Module &&
          typeof Module[fn] === "function") {
        var v = Module[fn]();
        if (typeof v === "number" && isFinite(v)) return v;
      }
    } catch (e) {}
    return fb;
  }
  function rpmA3() { return coreNumA3("emu_get_rpm", 0); }
  function redlineA3() {
    try {
      if (typeof Module !== "undefined" && Module &&
          typeof Module.emu_cal_get === "function") {
        var r = Module.emu_cal_get().redline;
        if (Number.isFinite(r) && r > 0) return r;
      }
    } catch (e) {}
    return 9000;
  }
  function fuelCutA3() { return coreNumA3("emu_get_fuel_cut", 0) === 1; }
  function injDutyA3() { return coreNumA3("emu_get_inj_duty", 0); }
  function injPwMsA3(r, rl) { return 1 + (r / rl) * 7; } // mirrors the core

  function hexA3(bytes, n) {
    var out = [];
    var m = (n === undefined) ? bytes.length : Math.min(n, bytes.length);
    for (var i = 0; i < m; i++) {
      out.push(("0" + (bytes[i] & 0xFF).toString(16).toUpperCase()).slice(-2));
    }
    return out.join(" ");
  }
  function idHexA3(id) {
    return "0x" + ("000" + id.toString(16).toUpperCase()).slice(-3);
  }

  /* --- CAN tap: real frames from can_live.js, never invented --- */
  function pollCAN() {
    var now = Date.now();
    try {
      if (typeof CANLive !== "undefined" && CANLive &&
          typeof CANLive.since === "function") {
        var r = CANLive.since(_canIdx);
        _canIdx = r.next;
        for (var i = 0; i < r.frames.length; i++) {
          _canEvents.push({ t: r.frames[i].ts, dir: r.frames[i].dir });
        }
      }
    } catch (e) {}
    while (_canEvents.length > 0 && (now - _canEvents[0].t) > WAVE_WIN_MS) {
      _canEvents.shift();
    }
    try {
      if (typeof CANLive !== "undefined" && CANLive &&
          typeof CANLive.counts === "function") {
        var c = CANLive.counts();
        _lastTx = c.tx; _lastRx = c.rx;
      }
    } catch (e) {}
  }
  var _lastDirCache = { TX: null, RX: null };
  var _dirCacheMs = 0;
  function lastFrameA3() {
    try {
      if (typeof CANLive === "undefined" || !CANLive ||
          typeof CANLive.last !== "function") return null;
      return CANLive.last();
    } catch (e) { return null; }
  }
  function refreshDirCache() {
    var nowMs = Date.now();
    if ((nowMs - _dirCacheMs) < 200) return; // live list calls this per row
    _dirCacheMs = nowMs;
    try {
      if (typeof CANLive === "undefined" || !CANLive ||
          typeof CANLive.since !== "function") return;
      var r = CANLive.since(0);
      var tx = null, rx = null;
      for (var i = r.frames.length - 1; i >= 0; i--) {
        var f = r.frames[i];
        if (f.dir === "TX" && !tx) tx = f;
        else if (f.dir === "RX" && !rx) rx = f;
        if (tx && rx) break;
      }
      if (tx) _lastDirCache.TX = tx;
      if (rx) _lastDirCache.RX = rx;
    } catch (e) {}
  }

  /* --- pin classification --- */
  function isINJ(n) { return n === "INJ1" || n === "INJ2" || n === "INJ3" || n === "INJ4"; }
  function isCOIL(n) { return n === "COIL1" || n === "COIL2" || n === "COIL3" || n === "COIL4"; }
  function isCAN(n) { return n === "CANH" || n === "CANL" || n === "MSCANH" || n === "MSCANL"; }
  function isSCI(n) { return n === "TXD" || n === "RXD"; }

  /* Where each generic digital's live level really comes from. */
  var DIN_SRC = {
    OMP: "oil metering pump — runs while the engine turns",
    FUEL_RLY: "fuel pump relay — 3 s key-on prime + crank/run",
    FAN1: "cooling fan low — ECU hysteresis (see calibration)",
    FAN2: "cooling fan high — ECU hysteresis (see calibration)",
    CHECK_ENG: "MIL latch — DTC state (see DTC tab)",
    IG1_FB: "ignition feedback — follows the key switch",
    AC_REQ: "A/C request — dash toggle input",
    STP: "stop lamp — brake toggle input",
    VEH_SPD: "vehicle speed — rpm-derived digital proxy",
    BSC_CLK: "no verified GPIO mapping — static 0 (not invented)",
    BSC_DAT: "no verified GPIO mapping — static 0 (not invented)"
  };

  /* Live descriptor for a pin: { kind, rows, note, wave, pwm? }.
   * Rows are plain strings (caller renders via textContent). */
  function liveFor(pin) {
    if (!pin) return null;
    var n = pin.name, t = pin.type;
    if (t !== "digital" && t !== "can" && t !== "sci") return null;
    pollCAN();
    refreshDirCache();

    if (isCAN(n)) {
      var tx = _lastDirCache.TX, rx = _lastDirCache.RX;
      var bus = (n === "CANH" || n === "CANL") ? "HS-CAN" : "MS-CAN";
      return { kind: "can", wave: "can", bus: bus, note: "",
        rows: [
          ["bus", bus + " · shared live stream (single-bus sim model)"],
          ["last TX", tx ? (idHexA3(tx.id) + "  " + hexA3(tx.data) + "  (" + tx.dlc + "B)") : "— none yet"],
          ["last RX", rx ? (idHexA3(rx.id) + "  " + hexA3(rx.data) + "  (" + rx.dlc + "B)") : "— none yet"],
          ["frames", "TX " + _lastTx + " · RX " + _lastRx]
        ] };
    }

    if (isSCI(n)) {
      var sciReg = 0;
      try {
        if (typeof Module !== "undefined" && Module &&
            typeof Module.emu_get_reg === "function") {
          sciReg = Module.emu_get_reg(0xFFFFF020) >>> 0;
        }
      } catch (e) {}
      return { kind: "sci", wave: "flat",
        note: "no traffic simulated — the sim models no SCI/UART frames",
        rows: [
          ["register", "SCI @ 0xFFFFF020 = 0x" +
            ("00" + (sciReg & 0xFF).toString(16).toUpperCase()).slice(-2)],
          ["line", (pin._value ? "idle HIGH (3.3 V)" : "off (key OFF)")],
          ["baud", "not simulated"]
        ] };
    }

    if (isINJ(n)) {
      var r = rpmA3(), rl = redlineA3(), cut = fuelCutA3();
      var d = cut ? 0 : injDutyA3();
      var pw = cut ? 0 : injPwMsA3(r, rl);
      var f = r > 0 ? r / 60 : 0;
      var per = r > 0 ? 60000 / r : 0;
      return { kind: "pwm-inj", wave: "pwm",
        pwm: { f: f, duty: cut ? 0 : d, cut: cut },
        note: cut ? "fuel cut active — injectors held off, coils still fire" : "",
        rows: [
          ["duty", cut ? "0% (CUT)" : (Math.round(d * 1000) / 10) + "%"],
          ["pulse width", cut ? "0 ms (fuel cut at redline)" : (Math.round(pw * 100) / 100) + " ms"],
          ["frequency", (Math.round(f * 10) / 10) + " Hz (1 pulse/rev)"],
          ["rev period", r > 0 ? (Math.round(per * 100) / 100) + " ms @ " + r + " rpm" : "engine stopped"]
        ] };
    }

    if (isCOIL(n)) {
      var r2 = rpmA3();
      var f2 = r2 > 0 ? r2 / 60 : 0;
      var pw2 = r2 > 0 ? COIL_DUTY * 60000 / r2 : 0;
      return { kind: "pwm-coil", wave: "pwm",
        pwm: { f: f2, duty: r2 > 0 ? COIL_DUTY : 0, cut: false }, note: "",
        rows: [
          ["duty", r2 > 0 ? "8% (sequential window)" : "0% (engine stopped)"],
          ["pulse width", r2 > 0 ? (Math.round(pw2 * 100) / 100) + " ms" : "—"],
          ["frequency", (Math.round(f2 * 10) / 10) + " Hz (1 fire/rev)"],
          ["state", r2 > 0 ? ("firing @ " + r2 + " rpm (fires through fuel cut)") : "engine stopped"]
        ] };
    }

    if (n === "VEH_SPD") {
      var r3 = rpmA3();
      var f3 = r3 > 0 ? r3 / 60 : 0;
      return { kind: "vss", wave: "vss",
        pwm: { f: f3, duty: 0.5, cut: false },
        note: "digital proxy: the sim has no road-speed model, pulses derive from rpm",
        rows: [
          ["level", pin._value ? "HIGH (pulsing)" : "LOW (stopped)"],
          ["pulse freq", (Math.round(f3 * 10) / 10) + " Hz (rpm-derived proxy)"]
        ] };
    }

    var lvl = pin._value ? "HIGH (1)" : "LOW (0)";
    var src = DIN_SRC[n] || ((pin.port !== undefined) ?
      ("PORT" + pin.port + " bit" + pin.bit) : "static");
    return { kind: "din", wave: "dig", rows: [["level", lvl], ["source", src]],
      note: (n === "BSC_CLK" || n === "BSC_DAT") ?
        "unmapped by design (pins.json) — shown as 0, do not invent" : "" };
  }

  /* One-line snippet for the Pins-tab live list (plain string). */
  function rowSnippet(pin) {
    if (!pin) return "";
    pollCAN(); // keep the raster fed even with no pin selected
    var n = pin.name, t = pin.type;
    if (t !== "digital" && t !== "can" && t !== "sci") return "";
    if (isCAN(n)) {
      var f = lastFrameA3();
      var tot = (_lastTx >= 0 && _lastRx >= 0) ? (_lastTx + _lastRx) : 0;
      if (!f) return "n=" + tot;
      return idHexA3(f.id) + " " + hexA3(f.data, 3) + "… n=" + tot;
    }
    if (isSCI(n)) return "no traffic";
    if (isINJ(n)) {
      if (fuelCutA3()) return "CUT";
      return (Math.round(injDutyA3() * 1000) / 10) + "% " +
        (Math.round(rpmA3() / 60 * 10) / 10) + "Hz";
    }
    if (isCOIL(n)) {
      var r2 = rpmA3();
      if (r2 <= 0) return "off";
      return "8% " + (Math.round(r2 / 60 * 10) / 10) + "Hz";
    }
    if (n === "VEH_SPD") {
      var r3 = rpmA3();
      return r3 > 0 ? (Math.round(r3 / 60 * 10) / 10) + "Hz proxy" : "stopped";
    }
    return "";
  }

  /* Sim-clock tick (~100 Hz, no DOM): consume CAN frames into the raster
   * buffer and sample the selected slow-digital pin level. */
  function tick(selPin) {
    pollCAN();
    var key = selPin ? selPin.name : "";
    if (key !== _histKey) { _histKey = key; _hist.length = 0; }
    if (selPin && (selPin.type === "digital") &&
        !isINJ(key) && !isCOIL(key) && !isCAN(key) && !isSCI(key)) {
      _hist.push(selPin._value ? 1 : 0);
      if (_hist.length > HIST_MAX) _hist.shift();
    }
  }

  /* --- waveform rendering (a few dozen canvas ops @ ~6 Hz) --- */
  function setupCtx(cv) {
    var ctx = cv.getContext("2d");
    var W = cv.width, H = cv.height;
    ctx.clearRect(0, 0, W, H);
    ctx.fillStyle = "#0b0e13";
    ctx.fillRect(0, 0, W, H);
    ctx.strokeStyle = "#252c38";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(0, H / 2 + 0.5);
    ctx.lineTo(W, H / 2 + 0.5);
    ctx.stroke();
    return { ctx: ctx, W: W, H: H };
  }
  function yFor(v, H) { return v ? 6 : (H - 6); }
  function drawTag(ctx, W, tag, color) {
    ctx.font = "700 10px monospace";
    ctx.fillStyle = color;
    ctx.textAlign = "right";
    try { ctx.fillText(tag, W - 4, 11); } catch (e) {}
  }
  function drawFlatTrace(cv, level, color, tag) {
    var s = setupCtx(cv), ctx = s.ctx, W = s.W, H = s.H;
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(0, yFor(level, H));
    ctx.lineTo(W, yFor(level, H));
    ctx.stroke();
    drawTag(ctx, W, tag, color);
  }

  function drawPWM(cv, pwm, color) {
    if (pwm.cut) {
      drawFlatTrace(cv, 0, "#f85149", "CUT");
      return "held LOW — fuel cut";
    }
    if (!(pwm.f > 0) || !(pwm.duty > 0)) {
      drawFlatTrace(cv, 0, color, "LOW");
      return "flat LOW — engine stopped";
    }
    var s = setupCtx(cv), ctx = s.ctx, W = s.W, H = s.H;
    var N = 4; // zoomed: 4 periods across the strip
    var pp = W / N;
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.beginPath();
    var yEdge = yFor(0, H);
    for (var p = 0; p < N; p++) {
      var x0 = p * pp;
      var x1 = x0 + pwm.duty * pp;
      ctx.lineTo(x0, yFor(0, H));
      ctx.lineTo(x0, yFor(1, H));
      ctx.lineTo(x1, yFor(1, H));
      ctx.lineTo(x1, yFor(0, H));
      yEdge = yFor(0, H);
    }
    ctx.lineTo(W, yFor(0, H));
    ctx.stroke();
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(W - 3, yEdge, 2.5, 0, Math.PI * 2);
    ctx.fill();
    drawTag(ctx, W, pwm.duty >= 0.5 ? "HIGH" : "LOW", color);
    return Math.round(pwm.f * 10) / 10 + " Hz · " +
      (Math.round(pwm.duty * 1000) / 10) + "% · 4 periods shown";
  }

  function drawCAN(cv) {
    var s = setupCtx(cv), ctx = s.ctx, W = s.W, H = s.H;
    var now = Date.now();
    var n = 0;
    for (var i = 0; i < _canEvents.length; i++) {
      var age = now - _canEvents[i].t;
      if (age < 0 || age > WAVE_WIN_MS) continue;
      var x = W - (age / WAVE_WIN_MS) * W;
      var isTx = _canEvents[i].dir === "TX";
      ctx.strokeStyle = isTx ? "#39c5cf" : "#bc8cff";
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      if (isTx) { ctx.moveTo(x, 5); ctx.lineTo(x, H - 5); }
      else { ctx.moveTo(x, H / 2 - 10); ctx.lineTo(x, H / 2 + 10); }
      ctx.stroke();
      n++;
    }
    var col = n > 0 ? "#39c5cf" : "#8b96a3";
    drawTag(ctx, W, n > 0 ? n + " frames/2s" : "bus idle", col);
    return n > 0 ? (n + " frames in the last 2 s (tall=TX, short=RX)") :
      "flat — no frames in the last 2 s (key OFF = RX only)";
  }

  function drawDig(cv, pin) {
    var cur = pin._value ? 1 : 0;
    if (_hist.length < 2) {
      drawFlatTrace(cv, cur, "#7ee787", cur ? "HIGH" : "LOW");
      return "flat — sampling…";
    }
    var s = setupCtx(cv), ctx = s.ctx, W = s.W, H = s.H;
    ctx.strokeStyle = "#7ee787";
    ctx.lineWidth = 2;
    ctx.beginPath();
    var m = _hist.length;
    for (var i = 0; i < m; i++) {
      var x = (i / (HIST_MAX - 1)) * W;
      var y = yFor(_hist[i], H);
      if (i === 0) { ctx.moveTo(x, y); }
      else {
        var py = yFor(_hist[i - 1], H);
        if (py !== y) ctx.lineTo(x, py); // vertical edge
        ctx.lineTo(x, y);
      }
    }
    ctx.stroke();
    drawTag(ctx, W, cur ? "HIGH" : "LOW", "#7ee787");
    return "2 s window @ 100 Hz · now " + (cur ? "HIGH" : "LOW");
  }

  /* Draw the waveform for the selected pin. Returns the caption string
   * (the caller mirrors it into HTML for headless assertions). */
  function drawWave(cv, pin) {
    if (!cv || !pin) return "";
    var d = liveFor(pin);
    if (!d) return "";
    var cap = "";
    if (d.wave === "pwm" || d.wave === "vss") {
      cap = drawPWM(cv, d.pwm, d.wave === "vss" ? "#e3b341" : "#7ee787");
      if (d.wave === "vss") cap += " · proxy 1 pulse/rev";
    } else if (d.wave === "can") {
      cap = drawCAN(cv);
    } else if (d.wave === "dig") {
      cap = drawDig(cv, pin);
    } else {
      var lvl = pin.type === "sci" ? 1 : (pin._value ? 1 : 0);
      drawFlatTrace(cv, lvl, "#8b96a3",
        pin.type === "sci" ? "IDLE" : (lvl ? "HIGH" : "LOW"));
      cap = pin.type === "sci" ? "flat IDLE — no traffic simulated" :
        "flat — no data on this pin";
    }
    return cap;
  }

  /* Plain-JSON summary for headless test hooks (no DOM). */
  function summary(pin) {
    var d = liveFor(pin);
    if (!d) return null;
    return { kind: d.kind, rows: d.rows, note: d.note, wave: d.wave,
      canEvents: _canEvents.length, tx: _lastTx, rx: _lastRx };
  }

  return {
    liveFor: liveFor,
    rowSnippet: rowSnippet,
    tick: tick,
    drawWave: drawWave,
    summary: summary
  };
})();

/* Wave A3 headless hooks (used by the verification ritual). */
try {
  if (typeof window !== "undefined") {
    window.__selectPinByNum = function(num) {
      num = Number(num);
      const p = PINS.find(x => x.num === num);
      if (!p) return null;
      if (selectedPin && selectedPin.num === p.num) showPinInfo(p);
      else selectPin(p);
      return p.name;
    };
    window.__setKey = setKeyPos;
    window.__holdStart = holdStart;
    window.__pinSummary = function(name) {
      try {
        const p = PINS.find(x => x.name === name);
        if (!p || typeof PinData === "undefined") return null;
        return PinData.summary(p);
      } catch (e) { return null; }
    };
    window.__waveSum = function() {
      try {
        const cv = document.getElementById("pin-wave");
        if (!cv || !(cv.width > 0)) return -1;
        const ctx = cv.getContext("2d");
        const d = ctx.getImageData(0, 0, cv.width, cv.height).data;
        let s = 0;
        for (let i = 0; i < d.length; i += 401) s += d[i];
        return s;
      } catch (e) { return -1; }
    };
  }
} catch (e) {}

document.addEventListener("DOMContentLoaded", init);

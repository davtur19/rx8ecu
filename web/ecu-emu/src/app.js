/**
 * app.js — RX-8 ECU Emulator webui
 *
 * Pure JS, zero deps. Reads pins.json (embedded as script tag), renders
 * interactive connector pinout, schematic view, live pin states with
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
  rpm: 800, ect: 80, iat: 25, map: 35, tps: 0, o2f: 0.45, o2r: 0.45
};

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
function computePinStates() {
  /* Push sensors into the core */
  Module.emu_set_sensor(0, sensorState.rpm);
  Module.emu_set_sensor(1, sensorState.ect);
  Module.emu_set_sensor(2, sensorState.iat);
  Module.emu_set_sensor(3, sensorState.map);
  Module.emu_set_sensor(4, sensorState.tps);
  Module.emu_set_sensor(5, sensorState.o2f);
  Module.emu_set_sensor(6, sensorState.o2r);

  /* Advance 10ms per frame */
  Module.emu_step_ms(10);

  /* Read pin voltages from core */
  PINS.forEach(p => {
    p._value = Module.emu_get_pin(p.num);
  });
}

/* ======================================================================
 *  Rendering: Connector pinout
 * ====================================================================== */
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
    cell.innerHTML = `
      <div class="pin-indicator"></div>
      <span class="pin-num">${p.num}</span>
      <span class="pin-name">${p.name}</span>
    `;
    cell.addEventListener("click", () => selectPin(p));
    cell.addEventListener("mouseenter", () => showPinInfo(p));

    if (p.num <= 48) {
      connA.appendChild(cell);
    } else {
      connB.appendChild(cell);
    }
  });
}

/* ======================================================================
 *  Rendering: Schematic SVG
 * ====================================================================== */
function renderSchematic(pin) {
  const svg = document.getElementById("schematic-svg");
  svg.innerHTML = "";

  if (!pin) {
    drawOverviewSchematic(svg);
    return;
  }

  const type = pin.type;
  const goesTo = pin.goes_to;

  // Background
  addSVG(svg, "rect", {x:0, y:0, width:800, height:500, fill:"#0b0e13"});

  // ECU box
  addSVG(svg, "rect", {x:300, y:80, width:200, height:340, rx:8, fill:"#12161d", stroke:"#252c38", "stroke-width":2});
  addSVG(svg, "text", {x:400, y:105, "text-anchor":"middle", fill:"#4d7cff", "font-family":"monospace", "font-size":14, "font-weight":"bold"}, "ECU (SH7055)");
  addSVG(svg, "text", {x:400, y:122, "text-anchor":"middle", fill:"#8b96a3", "font-family":"monospace", "font-size":10}, "N3J1-18-881L");

  // Pin dot on ECU
  const pinY = 160 + (pin.num % 48) * 5.5;
  const isOut = pin.dir === "out" || pin.dir === "io";
  const dotX = isOut ? 500 : 300;
  addSVG(svg, "circle", {cx:dotX, cy:pinY, r:5, fill:getTypeColor(pin.type)});
  addSVG(svg, "text", {x:dotX + (isOut ? 10 : -10), y:pinY + 4, "text-anchor": isOut ? "start" : "end", fill:"#e6ebf2", "font-family":"monospace", "font-size":10}, pin.name);

  // External component
  const compX = isOut ? 620 : 180;
  drawComponent(svg, compX, pinY, goesTo, pin);

  // Connection line
  addSVG(svg, "line", {x1:dotX + (isOut?5:-5), y1:pinY, x2:compX + (isOut?-30:30), y2:pinY, stroke:getTypeColor(pin.type), "stroke-width":2, "stroke-dasharray": type === "can" ? "6,3" : "none"});

  // Voltage annotation
  const vStr = `${pin.voltage[0]}-${pin.voltage[1]}V`;
  addSVG(svg, "text", {x:400, y:pinY - 12, "text-anchor":"middle", fill:"#39c5cf", "font-family":"monospace", "font-size":9}, vStr);

  // Peripheral register
  if (pin.adc_ch !== undefined) {
    addSVG(svg, "text", {x:400, y:440, "text-anchor":"middle", fill:"#7ee787", "font-family":"monospace", "font-size":10},
      `ADC ch${pin.adc_ch} @ 0x${(ADC_BASE + pin.adc_ch * 2).toString(16).toUpperCase()}`);
  } else if (pin.port !== undefined) {
    addSVG(svg, "text", {x:400, y:440, "text-anchor":"middle", fill:"#7ee787", "font-family":"monospace", "font-size":10},
      `PORT${pin.port} bit${pin.bit} @ 0x${(PORT_BASE + pin.port * 8).toString(16).toUpperCase()}`);
  } else if (pin.can) {
    addSVG(svg, "text", {x:400, y:440, "text-anchor":"middle", fill:"#7ee787", "font-family":"monospace", "font-size":10},
      `${pin.can} @ 0x${(pin.can === "CAN0_H" ? CAN0_BASE : CAN1_BASE).toString(16).toUpperCase()}`);
  }
}

function drawOverviewSchematic(svg) {
  addSVG(svg, "rect", {x:0, y:0, width:800, height:500, fill:"#0b0e13"});

  // ECU box
  addSVG(svg, "rect", {x:300, y:50, width:200, height:400, rx:10, fill:"#12161d", stroke:"#4d7cff", "stroke-width":2});
  addSVG(svg, "text", {x:400, y:80, "text-anchor":"middle", fill:"#4d7cff", "font-family":"monospace", "font-size":16, "font-weight":"bold"}, "ECU");
  addSVG(svg, "text", {x:400, y:98, "text-anchor":"middle", fill:"#8b96a3", "font-family":"monospace", "font-size":10}, "SH7055 · 512KB ROM");

  // Subsystem boxes around ECU
  const subsystems = [
    {x:50, y:60, label:"Battery +12V", color:"#e3b341", pins:["BAT1","BAT2"]},
    {x:50, y:130, label:"Sensors", color:"#4d7cff", pins:["ECT","MAP","TPS","IAT","O2F","NE+"]},
    {x:50, y:240, label:"CAN Bus", color:"#39c5cf", pins:["CANH","CANL"]},
    {x:600, y:60, label:"Ignition", color:"#7ee787", pins:["COIL1","COIL2","COIL3","COIL4"]},
    {x:600, y:160, label:"Fuel", color:"#7ee787", pins:["INJ1","INJ2","INJ3","INJ4","FUEL_RLY"]},
    {x:600, y:260, label:"Actuators", color:"#7ee787", pins:["OMP","FAN1","FAN2","VVT_A"]},
    {x:600, y:350, label:"MIL/Lamps", color:"#e3b341", pins:["CHECK_ENG"]},
  ];

  subsystems.forEach(s => {
    addSVG(svg, "rect", {x:s.x, y:s.y, width:140, height:55, rx:6, fill:"#181d26", stroke:s.color, "stroke-width":1});
    addSVG(svg, "text", {x:s.x+70, y:s.y+22, "text-anchor":"middle", fill:s.color, "font-family":"monospace", "font-size":10, "font-weight":"bold"}, s.label);
    addSVG(svg, "text", {x:s.x+70, y:s.y+40, "text-anchor":"middle", fill:"#8b96a3", "font-family":"monospace", "font-size":8}, s.pins.join(", "));

    // Line to ECU
    const leftSide = s.x < 300;
    addSVG(svg, "line", {
      x1: leftSide ? s.x + 140 : s.x,
      y1: s.y + 27,
      x2: leftSide ? 300 : 500,
      y2: 100 + (s.y / 400) * 300,
      stroke: s.color, "stroke-width": 1, opacity: 0.5
    });
  });

  // RPM indicator
  addSVG(svg, "text", {x:400, y:480, "text-anchor":"middle", fill:"#39c5cf", "font-family":"monospace", "font-size":12},
    `RPM: ${sensorState.rpm}  ECT: ${sensorState.ect}°C  MAP: ${sensorState.map} kPa`);
}

function drawComponent(svg, x, y, goesTo, pin) {
  const color = getTypeColor(pin.type);
  const iconMap = {
    battery:"icon-battery", chassis:"icon-ground", ign_switch:"icon-ign-switch",
    coil_1:"icon-coil", coil_2:"icon-coil", coil_3:"icon-coil", coil_4:"icon-coil",
    injector_1:"icon-injector", injector_2:"icon-injector", injector_3:"icon-injector", injector_4:"icon-injector",
    map_sensor:"icon-map", tps_sensor:"icon-tps",
    o2_front:"icon-o2", o2_rear:"icon-o2",
    ect_sensor:"icon-thermistor", iat_sensor:"icon-thermistor",
    omp_pump:"icon-omp", fuel_pump:"icon-fuel-pump",
    fan_1:"icon-fan", fan_2:"icon-fan",
    mil_lamp:"icon-mil",
    can_bus:"icon-can", mscan_bus:"icon-can", obd_scanner:"icon-sci",
    crank_sensor:"icon-crank", cam_sensor:"icon-cam",
    knock_sensor:"icon-knock", vvt_solenoid:"icon-vvt",
    ac_clutch:"icon-ac", speed_sensor:"icon-speed",
    stop_lamp:"icon-stop-lamp", bsc_bus:"icon-bsc",
    nc:"icon-ecu"
  };
  const labels = {
    battery:"+12V", chassis:"GND", coil_1:"COIL L-A", coil_2:"COIL T-A",
    coil_3:"COIL L-B", coil_4:"COIL T-B", injector_1:"INJ A1", injector_2:"INJ A2",
    injector_3:"INJ B1", injector_4:"INJ B2", map_sensor:"MAP", tps_sensor:"TPS",
    o2_front:"O2-front", o2_rear:"O2-rear", ect_sensor:"ECT", iat_sensor:"IAT",
    omp_pump:"OMP", fuel_pump:"FUEL", fan_1:"FAN-1", fan_2:"FAN-2",
    mil_lamp:"MIL", can_bus:"HS-CAN", mscan_bus:"MS-CAN", obd_scanner:"OBD",
    crank_sensor:"NE", cam_sensor:"G1", knock_sensor:"KNOCK",
    vvt_solenoid:"VVT", ac_clutch:"A/C", speed_sensor:"VSS",
    stop_lamp:"STOP", ign_switch:"IGN", bsc_bus:"BSC", nc:"NC"
  };
  const label = labels[goesTo] || goesTo;
  const iconId = iconMap[goesTo] || "icon-ecu";

  // Card background
  addSVG(svg, "rect", {x:x-35, y:y-22, width:70, height:44, rx:5, fill:"#181d26", stroke:color, "stroke-width":1, class:"component-card"});

  // Icon
  const icon = addSVG(svg, "use", {href:`#${iconId}`, x:x-25, y:y-16, width:18, height:18});
  icon.setAttribute("color", color);

  // Label
  addSVG(svg, "text", {x:x, y:y+6, "text-anchor":"middle", fill:color, "font-family":"monospace", "font-size":8, "font-weight":"bold"}, label);

  // Live value below
  const val = pinOutputs[pin.name];
  let valStr = "";
  if (pin.type === "digital") valStr = val ? "HIGH" : "LOW";
  else if (pin.type === "analog") valStr = `${val.toFixed(2)}V`;
  else if (pin.type === "power") valStr = `${val.toFixed(1)}V`;
  else if (pin.type === "can") valStr = val > 0 ? "Active" : "Idle";
  else if (pin.type === "sci") valStr = val > 0 ? "Idle" : "Off";
  if (valStr) addSVG(svg, "text", {x:x, y:y+18, "text-anchor":"middle", fill:"#8b96a3", "font-family":"monospace", "font-size":7}, valStr);
}

function addSVG(parent, tag, attrs, text) {
  const el = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  if (text !== undefined) el.textContent = text;
  parent.appendChild(el);
  return el;
}

function getTypeColor(type) {
  const colors = {
    power:"#e3b341", gnd:"#8b96a3", analog:"#4d7cff", digital:"#7ee787",
    can:"#39c5cf", sci:"#bc8cff", nc:"#333c4a"
  };
  return colors[type] || "#8b96a3";
}

/* ======================================================================
 *  Rendering: Pin info overlay
 * ====================================================================== */
function showPinInfo(pin) {
  const overlay = document.getElementById("schematic-info");
  overlay.style.display = "block";
  document.getElementById("info-title").textContent = `Pin ${pin.num}: ${pin.name}`;
  document.getElementById("info-type").textContent = pin.type.toUpperCase();
  document.getElementById("info-dir").textContent = pin.dir === "in" ? "Input" : pin.dir === "out" ? "Output" : pin.dir === "io" ? "Bidirectional" : "N/A";
  document.getElementById("info-goes").textContent = pin.goes_to.replace(/_/g, " ");
  document.getElementById("info-voltage").textContent = `${pin.voltage[0]}–${pin.voltage[1]}V`;

  const val = pin._value || 0;
  if (pin.type === "digital") {
    document.getElementById("info-state").textContent = val ? "HIGH (1)" : "LOW (0)";
    document.getElementById("info-state").style.color = val ? "var(--green)" : "var(--muted)";
  } else if (pin.type === "analog") {
    document.getElementById("info-state").textContent = `${val.toFixed(3)}V (ADC: ${voltageToADC10(val)})`;
    document.getElementById("info-state").style.color = "var(--cyan)";
  } else if (pin.type === "power") {
    document.getElementById("info-state").textContent = `${val.toFixed(1)}V`;
    document.getElementById("info-state").style.color = "var(--yellow)";
  } else if (pin.type === "can") {
    document.getElementById("info-state").textContent = val > 0 ? "Bus active" : "Bus idle";
    document.getElementById("info-state").style.color = "var(--cyan)";
  } else {
    document.getElementById("info-state").textContent = "—";
    document.getElementById("info-state").style.color = "var(--muted)";
  }

  renderSchematic(pin);
}

function selectPin(pin) {
  // Deselect previous
  document.querySelectorAll(".pin-cell.selected").forEach(el => el.classList.remove("selected"));

  if (selectedPin && selectedPin.num === pin.num) {
    selectedPin = null;
    document.getElementById("schematic-info").style.display = "none";
    renderSchematic(null);
    return;
  }

  selectedPin = pin;
  const cell = document.querySelector(`.pin-cell[data-num="${pin.num}"]`);
  if (cell) cell.classList.add("selected");
  showPinInfo(pin);
}

/* ======================================================================
 *  Rendering: Live pin states (right panel)
 * ====================================================================== */
function renderStates() {
  const list = document.getElementById("states-list");
  list.innerHTML = "";

  // Only show non-NC, non-GND pins
  const activePins = PINS.filter(p => p.type !== "nc" && p.type !== "gnd");

  activePins.forEach(p => {
    const val = p._value || 0;
    const item = document.createElement("div");
    item.className = "state-item";

    let displayVal, barPct, barColor;
    if (p.type === "digital") {
      displayVal = val ? "HIGH" : "LOW";
      barPct = val ? 100 : 0;
      barColor = val ? "var(--green)" : "var(--muted)";
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

    item.innerHTML = `
      <div class="state-name" style="color:${getTypeColor(p.type)}">${p.name}</div>
      <div class="state-bar"><div class="state-bar-fill" style="width:${barPct}%;background:${barColor}"></div></div>
      <div class="state-value">${displayVal}</div>
    `;
    list.appendChild(item);
  });
}

/* ======================================================================
 *  Rendering: Scenarios
 * ====================================================================== */
function renderScenarios() {
  const container = document.getElementById("scenarios");
  container.innerHTML = "";

  Object.entries(SCENARIOS).forEach(([key, sc]) => {
    const btn = document.createElement("button");
    btn.className = "scenario-btn";
    btn.innerHTML = `<div class="sc-name">${key.toUpperCase()}</div><div class="sc-desc">${sc.desc}</div>`;
    btn.addEventListener("click", () => applyScenario(key));
    container.appendChild(btn);
  });
}

function applyScenario(key) {
  const sc = SCENARIOS[key];
  if (!sc) return;
  sensorState.rpm = sc.rpm;
  sensorState.ect = sc.ect;
  sensorState.iat = sc.iat;
  sensorState.map = sc.map;
  sensorState.tps = sc.tps;
  updateSliders();
  refresh();
  // Highlight active scenario
  document.querySelectorAll(".scenario-btn").forEach((btn, i) => {
    btn.classList.toggle("active", Object.keys(SCENARIOS)[i] === key);
  });
}

/* ======================================================================
 *  Rendering: Sensor sliders
 * ====================================================================== */
function renderSliders() {
  const container = document.getElementById("sliders");
  container.innerHTML = "";

  const sliders = [
    {key:"rpm",  label:"RPM",   min:0, max:8000, step:100, unit:""},
    {key:"ect",  label:"ECT",   min:-20,max:120, step:1,   unit:"°C"},
    {key:"iat",  label:"IAT",   min:-20,max:60,  step:1,   unit:"°C"},
    {key:"map",  label:"MAP",   min:0,  max:105, step:1,   unit:"kPa"},
    {key:"tps",  label:"TPS",   min:0,  max:100, step:1,   unit:"%"},
    {key:"o2f",  label:"O2-F",  min:0,  max:1,   step:0.01,unit:"V"},
  ];

  sliders.forEach(s => {
    const group = document.createElement("div");
    group.className = "slider-group";
    group.innerHTML = `
      <label>${s.label} <span id="val-${s.key}">${sensorState[s.key]}${s.unit}</span></label>
      <input type="range" min="${s.min}" max="${s.max}" step="${s.step}" value="${sensorState[s.key]}" id="slider-${s.key}">
    `;
    container.appendChild(group);

    const input = group.querySelector("input");
    input.addEventListener("input", () => {
      sensorState[s.key] = parseFloat(input.value);
      document.getElementById(`val-${s.key}`).textContent = `${sensorState[s.key]}${s.unit}`;
      refresh();
    });
  });
}

function updateSliders() {
  ["rpm","ect","iat","map","tps","o2f"].forEach(key => {
    const slider = document.getElementById(`slider-${key}`);
    if (slider) {
      slider.value = sensorState[key];
      const unit = {rpm:"",ect:"°C",iat:"°C",map:"kPa",tps:"%",o2f:"V"}[key];
      const valEl = document.getElementById(`val-${key}`);
      if (valEl) valEl.textContent = `${sensorState[key]}${unit}`;
    }
  });
}

/* ======================================================================
 *  Rendering: Register view (bottom) — reads from emu_core
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

  // Port latches (0-5)
  for (let p = 0; p < 6; p++) {
    const addr = PORT_BASE + p * 8;
    const val = Module.emu_get_port(p, 0) | (Module.emu_get_port(p, 1) << 1) |
               (Module.emu_get_port(p, 2) << 2) | (Module.emu_get_port(p, 3) << 3);
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
 *  Refresh cycle
 * ====================================================================== */
function refresh() {
  computePinStates();
  renderStates();
  renderRegisters();
  if (selectedPin) showPinInfo(selectedPin);
}

/* ======================================================================
 *  Init
 * ====================================================================== */
function init() {
  // Load pin data from embedded JSON
  const dataEl = document.getElementById("pins-data");
  let data;
  try {
    data = JSON.parse(dataEl.textContent);
  } catch(e) {
    // Fallback: try fetch
    fetch("pins.json").then(r => r.json()).then(d => {
      PINS = d.pins;
      PERIPHERALS = d.peripherals || [];
      SCENARIOS = d.scenarios || {};
      boot();
    });
    return;
  }
  PINS = data.pins;
  PERIPHERALS = data.peripherals || [];
  SCENARIOS = data.scenarios || {};
  boot();
}

function boot() {
  // Initialize the emulator core with pin data
  Module.emu_init();
  Module.emu_set_pins(PINS);

  renderPinout();
  renderSchematic(null);
  renderScenarios();
  renderSliders();
  refresh();

  // Apply idle scenario by default
  applyScenario("idle");

  // Initialize engine simulator and CAN monitor
  if (typeof EngineSim !== "undefined") {
    EngineSim.init("engine-sim-container");
  }
  if (typeof CANLive !== "undefined") {
    CANLive.init("can-monitor-container");
  }
}

document.addEventListener("DOMContentLoaded", init);

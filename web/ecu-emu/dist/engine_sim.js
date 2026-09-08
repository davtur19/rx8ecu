/**
 * engine_sim.js — Interactive engine simulator for RX-8 ECU Emulator
 *
 * Throttle slider + load control, animated crank wheel + rotor visualization
 * (canvas-based, technical not playful), RPM/ECT/MAP readouts updating live,
 * DTC/MIL lamp when limits exceeded.
 *
 * Depends on: app.js (sensorState), emu_core.js (Module)
 * No new CSS — uses existing style.css panel classes.
 */
"use strict";

var EngineSim = (function() {

  /* ====================================================================
   *  Constants
   * ==================================================================== */
  var CRANK_TEETH = 20;           // 20-tooth trigger wheel
  var CANVAS_SIZE = 220;          // crank wheel canvas
  var GAUGE_SIZE = 80;            // mini gauge diameter
  var TICK_MS = 33;               // ~30 fps
  var REDLINE = 7500;
  var OVERHEAT = 110;             // ECT DTC threshold (°C)
  var DTC_CODES = {
    P0300: "Random/Multiple misfire",
    P0117: "ECT circuit low",
    P0118: "ECT circuit high",
    P0108: "MAP circuit high",
    P0122: "TPS circuit low",
    P0123: "TPS circuit high",
  };

  /* State */
  var _running = false;
  var _timer = null;
  var _crankPhase = 0;     // angle in radians for animation
  var _throttle = 0;       // 0-100 %
  var _load = 20;          // 0-100 % (simulated load)
  var _dtcs = [];          // active DTCs
  var _milOn = false;
  var _cruiseOn = false;

  /* Canvas contexts */
  var _crankCtx = null;
  var _gaugeRpmCtx = null;
  var _gaugeMapCtx = null;

  /* ====================================================================
   *  Sensor helpers
   * ==================================================================== */
  function getRPM() { return window.sensorState ? window.sensorState.rpm : 0; }
  function getECT() { return window.sensorState ? window.sensorState.ect : 80; }
  function getMAP() { return window.sensorState ? window.sensorState.map : 35; }
  function getTPS() { return window.sensorState ? window.sensorState.tps : 0; }

  function mapRange(v, inMin, inMax, outMin, outMax) {
    return outMin + ((v - inMin) / (inMax - inMin)) * (outMax - outMin);
  }

  /* ====================================================================
   *  DTC Logic
   * ==================================================================== */
  function checkDTCs() {
    _dtcs = [];
    var ect = getECT();
    var map = getMAP();
    var tps = getTPS();
    var rpm = getRPM();

    if (ect > OVERHEAT) _dtcs.push({ code: "P0118", desc: DTC_CODES.P0118, sev: "error" });
    if (ect < -30) _dtcs.push({ code: "P0117", desc: DTC_CODES.P0117, sev: "error" });
    if (map > 100) _dtcs.push({ code: "P0108", desc: DTC_CODES.P0108, sev: "warning" });
    if (tps < 1 && rpm > 2000) _dtcs.push({ code: "P0122", desc: DTC_CODES.P0122, sev: "warning" });
    if (rpm > REDLINE + 200) _dtcs.push({ code: "P0300", desc: DTC_CODES.P0300, sev: "error" });

    _milOn = _dtcs.some(function(d) { return d.sev === "error"; });
  }

  /* ====================================================================
   *  Crank wheel rendering (canvas)
   * ==================================================================== */
  function drawCrankWheel() {
    var ctx = _crankCtx;
    if (!ctx) return;
    var w = CANVAS_SIZE, h = CANVAS_SIZE;
    var cx = w / 2, cy = h / 2;
    var outerR = w * 0.42;
    var innerR = w * 0.28;
    var toothH = w * 0.08;

    ctx.clearRect(0, 0, w, h);

    // Background circle (hub)
    ctx.beginPath();
    ctx.arc(cx, cy, innerR, 0, Math.PI * 2);
    ctx.fillStyle = "#181d26";
    ctx.fill();
    ctx.strokeStyle = "#252c38";
    ctx.lineWidth = 1;
    ctx.stroke();

    // Teeth
    for (var i = 0; i < CRANK_TEETH; i++) {
      var angle = _crankPhase + (i / CRANK_TEETH) * Math.PI * 2;
      var gapAngle = (1 / CRANK_TEETH) * Math.PI * 2;
      var toothWidth = gapAngle * 0.6;

      // Gap positions: teeth 5 and 15 (end of each 6-tooth rotor group)
      if (i === 5 || i === 15) {
        // Missing tooth — draw gap indicator
        ctx.beginPath();
        ctx.arc(cx, cy, outerR + toothH * 0.3, angle - gapAngle * 0.3, angle + gapAngle * 0.3);
        ctx.strokeStyle = "rgba(248, 81, 73, 0.3)";
        ctx.lineWidth = 2;
        ctx.stroke();
        continue;
      }

      var x1 = cx + Math.cos(angle - toothWidth / 2) * outerR;
      var y1 = cy + Math.sin(angle - toothWidth / 2) * outerR;
      var x2 = cx + Math.cos(angle + toothWidth / 2) * outerR;
      var y2 = cy + Math.sin(angle + toothWidth / 2) * outerR;
      var x3 = cx + Math.cos(angle + toothWidth / 2) * (outerR + toothH);
      var y3 = cy + Math.sin(angle + toothWidth / 2) * (outerR + toothH);
      var x4 = cx + Math.cos(angle - toothWidth / 2) * (outerR + toothH);
      var y4 = cy + Math.sin(angle - toothWidth / 2) * (outerR + toothH);

      ctx.beginPath();
      ctx.moveTo(x1, y1);
      ctx.lineTo(x4, y4);
      ctx.lineTo(x3, y3);
      ctx.lineTo(x2, y2);
      ctx.closePath();

      // Color: rotor A (teeth 0-9) cyan, rotor B (10-19) accent
      var color = i < 10 ? "rgba(57, 197, 207, 0.7)" : "rgba(77, 124, 255, 0.7)";
      ctx.fillStyle = color;
      ctx.fill();
    }

    // Rotor reference mark (rotor A = top, rotor B = bottom)
    var refAngle = _crankPhase;
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.lineTo(
      cx + Math.cos(refAngle) * innerR,
      cy + Math.sin(refAngle) * innerR
    );
    ctx.strokeStyle = "#f85149";
    ctx.lineWidth = 2;
    ctx.stroke();

    // Center dot
    ctx.beginPath();
    ctx.arc(cx, cy, 3, 0, Math.PI * 2);
    ctx.fillStyle = "#e3b341";
    ctx.fill();

    // RPM label
    ctx.font = "600 11px monospace";
    ctx.fillStyle = "#8b96a3";
    ctx.textAlign = "center";
    ctx.fillText(getRPM() + " RPM", cx, cy + outerR + toothH + 18);

    // Rotor labels
    ctx.font = "600 9px monospace";
    ctx.fillStyle = "#39c5cf";
    ctx.fillText("ROTOR A", cx, cy + outerR + toothH + 30);
    ctx.fillStyle = "#4d7cff";
    ctx.fillText("ROTOR B", cx, cy + outerR + toothH + 42);
  }

  /* ====================================================================
   *  Mini gauge rendering
   * ==================================================================== */
  function drawGauge(canvasId, value, min, max, label, unit, color, thresholds) {
    var canvas = document.getElementById(canvasId);
    if (!canvas) return;
    var ctx = canvas.getContext("2d");
    var s = GAUGE_SIZE;
    var cx = s / 2, cy = s / 2;
    var r = s * 0.38;

    ctx.clearRect(0, 0, s, s);

    // Arc background
    var startAngle = Math.PI * 0.75;
    var endAngle = Math.PI * 2.25;
    var sweep = endAngle - startAngle;

    ctx.beginPath();
    ctx.arc(cx, cy, r, startAngle, endAngle);
    ctx.strokeStyle = "#252c38";
    ctx.lineWidth = 5;
    ctx.lineCap = "round";
    ctx.stroke();

    // Threshold arc (red zone)
    if (thresholds && thresholds.warn !== undefined) {
      var warnAngle = startAngle + sweep * ((thresholds.warn - min) / (max - min));
      var critAngle = thresholds.crit !== undefined ?
        startAngle + sweep * ((thresholds.crit - min) / (max - min)) : endAngle;
      ctx.beginPath();
      ctx.arc(cx, cy, r, Math.min(warnAngle, critAngle), Math.max(warnAngle, critAngle));
      ctx.strokeStyle = "rgba(248, 81, 73, 0.3)";
      ctx.lineWidth = 5;
      ctx.stroke();
    }

    // Value arc
    var valAngle = startAngle + sweep * Math.max(0, Math.min(1, (value - min) / (max - min)));
    ctx.beginPath();
    ctx.arc(cx, cy, r, startAngle, valAngle);
    ctx.strokeStyle = color;
    ctx.lineWidth = 5;
    ctx.lineCap = "round";
    ctx.stroke();

    // Needle
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.lineTo(
      cx + Math.cos(valAngle) * (r - 8),
      cy + Math.sin(valAngle) * (r - 8)
    );
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.stroke();

    // Center dot
    ctx.beginPath();
    ctx.arc(cx, cy, 3, 0, Math.PI * 2);
    ctx.fillStyle = color;
    ctx.fill();

    // Value text
    ctx.font = "700 13px monospace";
    ctx.fillStyle = "#e6ebf2";
    ctx.textAlign = "center";
    var displayVal = Math.round(value);
    ctx.fillText(displayVal, cx, cy + 4);

    // Label
    ctx.font = "600 8px monospace";
    ctx.fillStyle = "#8b96a3";
    ctx.fillText(label + " " + unit, cx, cy + r + 14);
  }

  /* ====================================================================
   *  Update simulation state from throttle/load
   * ==================================================================== */
  function updateFromThrottle() {
    if (!window.sensorState) return;
    var st = window.sensorState;

    // Target RPM from throttle + load
    var targetRPM = Math.round(mapRange(_throttle, 0, 100, 800, REDLINE));
    // Apply load factor (high load = RPM drops slightly at same throttle)
    targetRPM = Math.round(targetRPM * (1 - _load * 0.001));

    // Smooth RPM transition
    var diff = targetRPM - st.rpm;
    st.rpm = Math.round(st.rpm + diff * 0.15);

    // MAP from throttle + load (kPa)
    st.map = Math.round(mapRange(_throttle * _load / 100, 0, 100, 25, 95));
    st.map = Math.max(20, Math.min(100, st.map));

    // TPS tracks throttle directly
    st.tps = _throttle;
  }

  /* ====================================================================
   *  DTC panel rendering
   * ==================================================================== */
  function renderDTCs() {
    var el = document.getElementById("engine-dtc-list");
    if (!el) return;

    if (_dtcs.length === 0) {
      el.innerHTML = '<div class="dtc-none">No DTCs</div>';
      return;
    }

    var html = '';
    for (var i = 0; i < _dtcs.length; i++) {
      var d = _dtcs[i];
      var sevClass = d.sev === "error" ? "dtc-error" : "dtc-warning";
      html += '<div class="dtc-item ' + sevClass + '">' +
        '<span class="dtc-code">' + d.code + '</span>' +
        '<span class="dtc-desc">' + d.desc + '</span>' +
        '</div>';
    }
    el.innerHTML = html;
  }

  /* ====================================================================
   *  MIL lamp
   * ==================================================================== */
  function updateMIL() {
    var el = document.getElementById("engine-mil");
    if (!el) return;
    if (_milOn) {
      el.classList.add("mil-on");
      el.textContent = "MIL ON";
    } else {
      el.classList.remove("mil-on");
      el.textContent = "MIL OFF";
    }
  }

  /* ====================================================================
   *  Main tick
   * ==================================================================== */
  function tick() {
    // Update simulation from user inputs
    updateFromThrottle();

    // Advance crank animation
    var rpm = getRPM();
    if (rpm > 0) {
      var degPerMs = (rpm / 60) * 360 / 1000;
      _crankPhase += (degPerMs * TICK_MS) * Math.PI / 180;
      _crankPhase %= Math.PI * 2;
    }

    // Redraw crank wheel
    drawCrankWheel();

    // Update gauges
    drawGauge("gauge-rpm", rpm, 0, 9000, "RPM", "", "#39c5cf",
      { warn: 7000, crit: 7500 });
    drawGauge("gauge-ect", getECT(), -20, 120, "ECT", "°C", "#7ee787",
      { warn: 100, crit: 110 });
    drawGauge("gauge-map", getMAP(), 0, 105, "MAP", "kPa", "#4d7cff",
      { warn: 90, crit: 100 });

    // Check DTCs and update MIL
    checkDTCs();
    renderDTCs();
    updateMIL();
  }

  /* ====================================================================
   *  Build engine sim panel HTML
   * ==================================================================== */
  function buildPanel(containerId) {
    var container = document.getElementById(containerId);
    if (!container) return;

    container.innerHTML =
      '<div class="engine-sim-panel">' +

        /* --- Crank wheel --- */
        '<div class="esim-section">' +
          '<div class="esim-label">CRANK TRIGGER (20-TOOTH)</div>' +
          '<canvas id="crank-canvas" width="' + CANVAS_SIZE + '" height="' + CANVAS_SIZE + '"></canvas>' +
        '</div>' +

        /* --- Gauges row --- */
        '<div class="esim-gauges">' +
          '<canvas id="gauge-rpm" width="' + GAUGE_SIZE + '" height="' + GAUGE_SIZE + '"></canvas>' +
          '<canvas id="gauge-ect" width="' + GAUGE_SIZE + '" height="' + GAUGE_SIZE + '"></canvas>' +
          '<canvas id="gauge-map" width="' + GAUGE_SIZE + '" height="' + GAUGE_SIZE + '"></canvas>' +
        '</div>' +

        /* --- Controls --- */
        '<div class="esim-section">' +
          '<div class="esim-label">THROTTLE</div>' +
          '<div class="esim-slider-row">' +
            '<input type="range" id="esim-throttle" min="0" max="100" value="0" step="1">' +
            '<span id="esim-throttle-val">0%</span>' +
          '</div>' +
          '<div class="esim-label" style="margin-top:6px">LOAD</div>' +
          '<div class="esim-slider-row">' +
            '<input type="range" id="esim-load" min="0" max="100" value="20" step="1">' +
            '<span id="esim-load-val">20%</span>' +
          '</div>' +
        '</div>' +

        /* --- MIL + DTCs --- */
        '<div class="esim-section">' +
          '<div class="esim-mil-row">' +
            '<div id="engine-mil" class="mil-lamp">MIL OFF</div>' +
          '</div>' +
          '<div class="esim-label">DTCs</div>' +
          '<div id="engine-dtc-list" class="dtc-list"><div class="dtc-none">No DTCs</div></div>' +
        '</div>' +

      '</div>';
  }

  /* ====================================================================
   *  Init
   * ==================================================================== */
  function init(containerId) {
    buildPanel(containerId);

    // Get canvas contexts
    var crankCanvas = document.getElementById("crank-canvas");
    if (crankCanvas) _crankCtx = crankCanvas.getContext("2d");

    // Wire throttle slider
    var throttleEl = document.getElementById("esim-throttle");
    if (throttleEl) {
      throttleEl.addEventListener("input", function() {
        _throttle = parseInt(this.value);
        document.getElementById("esim-throttle-val").textContent = _throttle + "%";
      });
    }

    // Wire load slider
    var loadEl = document.getElementById("esim-load");
    if (loadEl) {
      loadEl.addEventListener("input", function() {
        _load = parseInt(this.value);
        document.getElementById("esim-load-val").textContent = _load + "%";
      });
    }

    // Start tick
    _running = true;
    _timer = setInterval(tick, TICK_MS);
  }

  function stop() {
    _running = false;
    if (_timer) { clearInterval(_timer); _timer = null; }
  }

  return { init: init, stop: stop };
})();

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
  var GAUGE_SIZE = 80;            // mini gauge diameter (ECT/MAP)
  var TACHO_SIZE = 220;           // RX-8 style tachometer dial diameter
  var TICK_MS = 33;               // ~30 fps
  var REDLINE = 9000;
  var TACHO_REDLINE = 8500;       // redline flash/glow threshold
  var IDLE_RPM = 800;
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
  var _tachoRPM = 800;   // smoothed needle value (eases toward actual rpm)
  var _tachoAngle = 0;   // last needle angle in radians (exposed for tests)

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
   *  Sim throttle/load control (also driven by the RPM sensor slider)
   *
   *  The 33ms tick pulls sensorState.rpm toward the throttle target, so a
   *  hand-dragged #slider-rpm value would otherwise be overwritten.
   *  app.js calls setFromRPM() on RPM-slider input: throttle is set to the
   *  inverse-mapped value and load is cleared (neutral rev) so the sim
   *  target equals the slider value and the drag sticks. The esim
   *  throttle/load sliders remain the primary sim control afterwards.
   * ==================================================================== */
  function clampThrottle(v) {
    v = Number(v);
    if (isNaN(v)) return 0;
    return Math.max(0, Math.min(100, v));
  }

  function syncSimUI() {
    var tEl = document.getElementById("esim-throttle");
    var tVal = document.getElementById("esim-throttle-val");
    if (tEl) tEl.value = Math.round(_throttle);
    if (tVal) tVal.textContent = Math.round(_throttle) + "%";
    var lEl = document.getElementById("esim-load");
    var lVal = document.getElementById("esim-load-val");
    if (lEl) lEl.value = Math.round(_load);
    if (lVal) lVal.textContent = Math.round(_load) + "%";
  }

  function setThrottle(v) {
    _throttle = clampThrottle(v);
    var tEl = document.getElementById("esim-throttle");
    var tVal = document.getElementById("esim-throttle-val");
    if (tEl) tEl.value = Math.round(_throttle);
    if (tVal) tVal.textContent = Math.round(_throttle) + "%";
    return _throttle;
  }

  function getThrottle() { return _throttle; }

  function setLoad(v) {
    _load = clampThrottle(v);
    var lEl = document.getElementById("esim-load");
    var lVal = document.getElementById("esim-load-val");
    if (lEl) lEl.value = Math.round(_load);
    if (lVal) lVal.textContent = Math.round(_load) + "%";
    return _load;
  }

  function getLoad() { return _load; }

  function setFromRPM(rpm) {
    rpm = Number(rpm);
    if (isNaN(rpm)) return _throttle;
    setThrottle((rpm - IDLE_RPM) / (REDLINE - IDLE_RPM) * 100);
    setLoad(0);
    return _throttle;
  }

  function getTachoRPM() { return _tachoRPM; }
  function getTachoAngle() { return _tachoAngle; }

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
   *  RX-8 style tachometer dial (large canvas, 0-9 x1000 rpm)
   *
   *  Dedicated dial (not drawGauge): numbered 0-9 scale, redline arc
   *  8.5-9.0, smoothed needle, canvas digital readout + #tacho-digital
   *  mirror, red flash/glow above 8500 rpm. Dark-theme palette.
   * ==================================================================== */
  function drawTacho(canvasId, rpm) {
    var canvas = document.getElementById(canvasId);
    if (!canvas) return;
    var ctx = canvas.getContext("2d");
    if (typeof rpm !== "number" || isNaN(rpm)) rpm = getRPM();
    var actual = rpm;

    // Needle smoothing: ease displayed value toward actual rpm.
    var diff = actual - _tachoRPM;
    _tachoRPM += diff * 0.25;
    if (Math.abs(diff) < 1) _tachoRPM = actual;
    var disp = _tachoRPM;

    var s = canvas.width || TACHO_SIZE;
    var cx = s / 2, cy = s / 2;
    var r = s * 0.40;
    var min = 0, max = REDLINE;
    var startAngle = Math.PI * 0.75;
    var endAngle = Math.PI * 2.25;
    var sweep = endAngle - startAngle;
    function rpmToAngle(v) {
      var f = (v - min) / (max - min);
      if (f < 0) f = 0;
      if (f > 1) f = 1;
      return startAngle + sweep * f;
    }
    var needleAngle = rpmToAngle(disp);
    _tachoAngle = needleAngle;
    var isRed = actual > TACHO_REDLINE;

    ctx.clearRect(0, 0, s, s);

    // Bezel
    ctx.beginPath();
    ctx.arc(cx, cy, r + 12, 0, Math.PI * 2);
    ctx.fillStyle = "#12161d";
    ctx.fill();
    ctx.strokeStyle = "#333c4a";
    ctx.lineWidth = 2;
    ctx.stroke();

    // Redline outer flash ring
    if (isRed) {
      var flash = (Math.floor(Date.now() / 300) % 2 === 0) ? 1 : 0.35;
      ctx.save();
      ctx.globalAlpha = 0.25 + 0.55 * flash;
      ctx.beginPath();
      ctx.arc(cx, cy, r + 12, 0, Math.PI * 2);
      ctx.strokeStyle = "#f85149";
      ctx.lineWidth = 4;
      ctx.shadowColor = "#f85149";
      ctx.shadowBlur = 18;
      ctx.stroke();
      ctx.restore();
    }

    // Track background
    ctx.beginPath();
    ctx.arc(cx, cy, r, startAngle, endAngle);
    ctx.strokeStyle = "#252c38";
    ctx.lineWidth = 8;
    ctx.lineCap = "round";
    ctx.stroke();

    // Redline arc 8.5-9.0
    var rlStart = rpmToAngle(8500);
    var rlEnd = rpmToAngle(9000);
    ctx.save();
    ctx.beginPath();
    ctx.arc(cx, cy, r, rlStart, rlEnd);
    ctx.strokeStyle = "#f85149";
    ctx.lineWidth = 8;
    ctx.lineCap = "butt";
    if (isRed) { ctx.shadowColor = "#f85149"; ctx.shadowBlur = 12; }
    ctx.stroke();
    ctx.restore();

    // Value arc
    ctx.beginPath();
    ctx.arc(cx, cy, r, startAngle, needleAngle);
    ctx.strokeStyle = isRed ? "#f85149" : "#39c5cf";
    ctx.lineWidth = 3;
    ctx.lineCap = "round";
    ctx.stroke();

    // Ticks: minor every 500, major every 1000
    var v, a, x1, y1, x2, y2;
    for (v = 0; v <= 9000; v += 500) {
      a = rpmToAngle(v);
      var major = (v % 1000 === 0);
      var inRed = v >= 8500;
      var outer = r - 10;
      var inner = major ? r - 24 : r - 17;
      x1 = cx + Math.cos(a) * inner;
      y1 = cy + Math.sin(a) * inner;
      x2 = cx + Math.cos(a) * outer;
      y2 = cy + Math.sin(a) * outer;
      ctx.beginPath();
      ctx.moveTo(x1, y1);
      ctx.lineTo(x2, y2);
      ctx.strokeStyle = inRed ? "#f85149" : (major ? "#e6ebf2" : "#8b96a3");
      ctx.lineWidth = major ? 2 : 1;
      ctx.stroke();
    }

    // Numerals 0-9 (x1000)
    ctx.font = "700 12px monospace";
    ctx.fillStyle = "#e6ebf2";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    for (v = 0; v <= 9; v++) {
      a = rpmToAngle(v * 1000);
      var nx = cx + Math.cos(a) * (r - 34);
      var ny = cy + Math.sin(a) * (r - 34);
      ctx.fillStyle = (v * 1000 >= 8500) ? "#f85149" : "#e6ebf2";
      ctx.fillText(String(v), nx, ny);
    }

    // Dial labels
    ctx.font = "600 8px monospace";
    ctx.fillStyle = "#8b96a3";
    ctx.fillText("x1000 r/min", cx, cy + r * 0.42);
    ctx.fillStyle = isRed ? "#f85149" : "#39c5cf";
    ctx.font = "700 9px monospace";
    ctx.fillText("RENESIS", cx, cy - r * 0.35);

    // Needle
    ctx.save();
    ctx.beginPath();
    ctx.moveTo(cx - Math.cos(needleAngle) * 8, cy - Math.sin(needleAngle) * 8);
    ctx.lineTo(cx + Math.cos(needleAngle) * (r - 14), cy + Math.sin(needleAngle) * (r - 14));
    ctx.strokeStyle = isRed ? "#f85149" : "#e6ebf2";
    ctx.lineWidth = 3;
    ctx.lineCap = "round";
    if (isRed) { ctx.shadowColor = "#f85149"; ctx.shadowBlur = 10; }
    ctx.stroke();
    ctx.restore();

    // Center cap
    ctx.beginPath();
    ctx.arc(cx, cy, 5, 0, Math.PI * 2);
    ctx.fillStyle = isRed ? "#f85149" : "#e6ebf2";
    ctx.fill();
    ctx.beginPath();
    ctx.arc(cx, cy, 2, 0, Math.PI * 2);
    ctx.fillStyle = "#0b0e13";
    ctx.fill();

    // Canvas digital readout
    ctx.font = "700 15px monospace";
    ctx.fillStyle = isRed ? "#f85149" : "#e6ebf2";
    ctx.fillText(String(Math.round(actual)), cx, cy + r * 0.68);

    // Test hooks + HTML mirror
    try {
      canvas.dataset.rpm = String(Math.round(disp));
      canvas.dataset.angle = String(needleAngle.toFixed(4));
      canvas.dataset.redline = isRed ? "1" : "0";
    } catch (e) {}
    var dig = document.getElementById("tacho-digital");
    if (dig) {
      dig.textContent = Math.round(actual) + " RPM";
      if (isRed) dig.classList.add("tacho-redline");
      else dig.classList.remove("tacho-redline");
    }
    var wrap = document.getElementById("tacho-wrap");
    if (wrap) {
      if (isRed) wrap.classList.add("tacho-redline");
      else wrap.classList.remove("tacho-redline");
    }
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

    // Update gauges: RX-8 tachometer dial + mini ECT/MAP (untouched).
    // Legacy #gauge-rpm mini is still drawn when present (backward compat).
    drawTacho("tacho-canvas", rpm);
    if (document.getElementById("gauge-rpm")) {
      drawGauge("gauge-rpm", rpm, 0, 9000, "RPM", "", "#39c5cf",
        { warn: 8000, crit: 8500 });
    }
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

        /* --- RX-8 tachometer dial --- */
        '<div class="tacho-wrap" id="tacho-wrap">' +
          '<div class="esim-label">TACHOMETER · RENESIS</div>' +
          '<canvas id="tacho-canvas" width="' + TACHO_SIZE + '" height="' + TACHO_SIZE + '" data-rpm="800" data-angle="0" data-redline="0"></canvas>' +
          '<div id="tacho-digital" class="tacho-digital">800 RPM</div>' +
          '<div class="tacho-sub">x1000 r/min · redline 8.5–9.0</div>' +
        '</div>' +

        /* --- Crank wheel --- */
        '<div class="esim-section">' +
          '<div class="esim-label">CRANK TRIGGER (20-TOOTH)</div>' +
          '<canvas id="crank-canvas" width="' + CANVAS_SIZE + '" height="' + CANVAS_SIZE + '"></canvas>' +
        '</div>' +

        /* --- Mini gauges (ECT/MAP) --- */
        '<div class="esim-gauges">' +
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
    syncSimUI();

    // Seed the tachometer needle at the current rpm (avoids sweep from 800
    // when the page boots into a non-idle scenario).
    try { _tachoRPM = getRPM(); } catch (e) {}

    // Get canvas contexts
    var crankCanvas = document.getElementById("crank-canvas");
    if (crankCanvas) _crankCtx = crankCanvas.getContext("2d");

    // Wire throttle slider
    var throttleEl = document.getElementById("esim-throttle");
    if (throttleEl) {
      throttleEl.addEventListener("input", function() {
        setThrottle(parseInt(this.value, 10));
      });
    }

    // Wire load slider
    var loadEl = document.getElementById("esim-load");
    if (loadEl) {
      loadEl.addEventListener("input", function() {
        setLoad(parseInt(this.value, 10));
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

  /* Test/sim-link hooks (available at script load, before init). */
  try {
    if (typeof window !== "undefined") {
      window.__setSimThrottle = setThrottle;
      window.__getSimThrottle = getThrottle;
      window.__setSimLoad = setLoad;
      window.__getSimLoad = getLoad;
      window.__setSimFromRPM = setFromRPM;
      window.__getTachoRPM = getTachoRPM;
      window.__getTachoAngle = getTachoAngle;
    }
  } catch (e) {}

  return {
    init: init, stop: stop,
    setThrottle: setThrottle, getThrottle: getThrottle,
    setLoad: setLoad, getLoad: getLoad,
    setFromRPM: setFromRPM,
    getTachoRPM: getTachoRPM, getTachoAngle: getTachoAngle
  };
})();

/**
 * can_live.js — Live CAN/OBD frame monitor for RX-8 ECU Emulator
 *
 * Generates CAN frames from the current sensor state using the same packing
 * logic as the firmware TX packers (firmware/c/can.c, CAN_PROTOCOL.md).
 *
 * Frames are emitted at realistic intervals matching the ECU's periodic
 * dispatch (CANTX_Main 0xDDF0). Each frame includes timestamp, CAN ID,
 * DLC, data bytes (hex), direction TX/RX, and decoded meaning.
 *
 * Depends on: app.js (sensorState), emu_core.js (Module)
 * Created files: can_live.css (styles)
 */
"use strict";

var CANLive = (function() {

  /* ====================================================================
   *  Constants
   * ==================================================================== */
  var MAX_FRAMES = 500;        // max frames in buffer
  var FRAME_INTERVAL_MS = 50;  // main loop tick (20 fps)

  /* NTC B=3435 for temp→voltage conversion in CAN packers */
  var NTC_B = 3435.0, NTC_R25 = 10000.0, NTC_RS = 10000.0;
  var NTC_VREF = 5.0, NTC_T25_K = 298.15;

  /* CAN ID → description lookup (from CAN_PROTOCOL.md) */
  var CAN_DESC = {
    0x041: "KCM/Immo response",
    0x201: "RPM / VSS / Accel",
    0x203: "Engine torque/status",
    0x212: "ABS/DSC/Brake",
    0x215: "Throttle position",
    0x216: "Unknown RX",
    0x231: "Engine state/Gear",
    0x240: "Transmission/Gear",
    0x250: "Inj pulse/IAT",
    0x251: "Engine data",
    0x420: "Coolant/MIL lamps",
    0x430: "Cluster presence",
    0x47:  "KCM/Immo request",
    0x4B0: "Wheel speeds",
    0x4B1: "DSC request",
    0x4C0: "Short msg",
    0x620: "Fan/AC status",
    0x630: "Cooling fan data",
    0x650: "Cruise lamps",
    0x7DF: "UDS broadcast",
    0x7E0: "UDS physical req",
    0x7E8: "UDS response",
  };

  /* Rate limiters (matching CANTX_Main counters) */
  var _counters = { c201: 0, c215: 0, c251: 0, c650: 0 };

  /* State */
  var _frames = [];
  var _running = false;
  var _timer = null;
  var _paused = false;
  var _filterId = "";       // hex string, empty = show all
  var _stats = { tx: 0, rx: 0 };
  /* Incremental render state: rows are appended, never rebuilt per tick. */
  var _renderedIdx = 0;     // _frames entries already flushed to the tbody
  var _lastFilterKey = "";  // filter string used for the current tbody
  var MAX_RENDERED = 50;    // max rows kept in the DOM

  /* ====================================================================
   *  NTC helper (mirrors ecu_pin_emu.py ntc_temp_to_voltage)
   * ==================================================================== */
  function ntcTempToV(celsius) {
    var tK = celsius + 273.15;
    var r = NTC_R25 * Math.exp(NTC_B * (1.0 / tK - 1.0 / NTC_T25_K));
    return NTC_VREF * r / (NTC_RS + r);
  }

  function mapRange(v, inMin, inMax, outMin, outMax) {
    return outMin + ((v - inMin) / (inMax - inMin)) * (outMax - outMin);
  }

  /* Wave A2: live core readers (fan states, A/C clutch, battery, oil).
   * Fall back to the sensorState snapshot when the core predates the API. */
  function coreFlag(fn, fb) {
    try {
      if (typeof Module !== "undefined" && Module && typeof Module[fn] === "function") {
        return Module[fn]() ? 1 : 0;
      }
    } catch (e) {}
    return fb ? 1 : 0;
  }
  function coreFan(i, fb) {
    try {
      if (typeof Module !== "undefined" && Module && typeof Module.emu_get_fan === "function") {
        return Module.emu_get_fan(i) ? 1 : 0;
      }
    } catch (e) {}
    return fb ? 1 : 0;
  }
  function coreNum(fn, fb) {
    try {
      if (typeof Module !== "undefined" && Module && typeof Module[fn] === "function") {
        var v = Module[fn]();
        if (typeof v === "number" && isFinite(v)) return v;
      }
    } catch (e) {}
    return fb;
  }
  /* Clamp RPM×4 to a u16 (BE split below); guards negative/huge rpm. */
  function rpmRawU16(rpm) {
    var r = (typeof rpm === "number" && isFinite(rpm)) ? rpm : 0;
    if (r < 0) r = 0;
    var raw = Math.round(r * 4);
    if (raw < 0) raw = 0;
    if (raw > 65535) raw = 65535;
    return raw;
  }

  /* Clamp a 0-255 byte value derived from TPS percent. */
  function tpsByte(tps, full) {
    var t = (typeof tps === "number" && isFinite(tps)) ? tps : 0;
    if (t < 0) t = 0;
    if (t > 100) t = 100;
    var v = Math.round(t * full / 100);
    if (v < 0) v = 0;
    if (v > full) v = full;
    return v;
  }

  /* ====================================================================
   *  CAN Frame packers — mirror firmware/c/can.c
   * ==================================================================== */

  /**
   * CAN ID 0x201 — RPM / vehicle speed / accelerator
   * ROM: can201_pack_staging (0x2A004)
   *   bytes 0-1: RPM u16 BE ÷4  (RPM × 4 for raw)
   *   bytes 2-3: vehicle speed u16 BE  ((raw − 10000) / 100 → km/h)
   *   byte 4-5: accelerator u16 BE
   *   byte 6:   accel pedal ÷2
   *   byte 7:   status 0xFF
   */
  function pack0x201(st) {
    var rpmRaw = rpmRawU16(st.rpm);
    var vssRaw = Math.round(st.vss * 100 + 10000);   // vss in km/h
    var accelRaw = tpsByte(st.tps, 255);              // accel 0-255 (255 at 100%)
    var accel2 = tpsByte(st.tps, 127);                // accel÷2 0-127
    return [
      (rpmRaw >> 8) & 0xFF, rpmRaw & 0xFF,
      (vssRaw >> 8) & 0xFF, vssRaw & 0xFF,
      (accelRaw >> 8) & 0xFF, accelRaw & 0xFF,
      accel2 & 0xFF,
      0xFF
    ];
  }

  /**
   * CAN ID 0x203 — Engine torque/status (7 bytes)
   * ROM: can203pack (0x2A274)
   */
  function pack0x203(st) {
    var torque = Math.round(mapRange(st.rpm, 0, 9000, 0, 200));
    return [
      torque & 0xFF,
      st.rpm > 200 ? 0x01 : 0x00,
      st.ect > 100 ? 0x04 : 0x00,
      0x00, 0x00,
      st.tps > 50 ? 0x01 : 0x00,
      0x00
    ];
  }

  /**
   * CAN ID 0x420 — Coolant temp gauge + MIL/warning lamps (7 bytes)
   * ROM: can420TXPack (0x29A0C)
   *   byte 0: ECT raw − 40 (gauge)
   *   byte 1: lamp flags
   */
  function pack0x420(st) {
    var ectRaw = Math.round(st.ect + 40);
    var lamps = 0;
    if (st.ect > 105) lamps |= 0x04;  // water temp warning
    if (st.oilLow)    lamps |= 0x02;  // oil pressure
    if (st.battLow)   lamps |= 0x08;  // battery
    if (st.mil)       lamps |= 0x01;  // check engine
    return [
      ectRaw & 0xFF,
      lamps,
      0x00, 0x00,
      0x00,
      0x00, 0x00
    ];
  }

  /**
   * CAN ID 0x630 — Cooling fan data (8 bytes)
   * ROM: can630TX_dispatch (0x33974)
   * Wave A2: fan bits come from the LIVE core fan states (hysteresis +
   * after-run), not from raw ECT thresholds. Byte 1 carries battery
   * terminal voltage x10 (A2 extension, emulator-level).
   */
  function pack0x630(st) {
    var fan1 = coreFan(0, st.ect > 90);
    var fan2 = coreFan(1, st.ect > 100);
    var bv10 = Math.round(coreNum("emu_get_batt_v", 12.6) * 10);
    return [
      fan1 | (fan2 << 1),
      bv10 & 0xFF,
      0x00, 0x00,
      0x00, 0x00,
      fan2,
      fan1
    ];
  }

  /**
   * CAN ID 0x650 — Cruise control lamps (1 byte)
   * ROM: can650TX_getAndPack (0x2C806)
   */
  function pack0x650(st) {
    return [0x00];  // cruise off
  }

  /**
   * CAN ID 0x041 — KCM/immobiliser (8 bytes, per-cycle)
   * ROM: can41TXPack (0x39348)
   */
  function pack0x041(st) {
    return [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00];
  }

  /**
   * CAN ID 0x620 — Fan/AC status (7 bytes)
   * ROM: can620TX_pack (0x33A68)
   * NOTE: no byte layout is documented in firmware/c/can.c, so this is an
   * emulator best-effort frame carrying the LIVE A2 values (consistent
   * with dlc=7): byte 0 fan flags (bit0 low, bit1 high), byte 1 A/C clutch,
   * byte 2 battery terminal V x10, byte 3 SoC %, byte 4 after-run flag.
   */
  function pack0x620(st) {
    var fan1 = coreFan(0, st.ect > 90);
    var fan2 = coreFan(1, st.ect > 100);
    var ac = coreFlag("emu_get_ac", false);
    var bv10 = Math.round(coreNum("emu_get_batt_v", 12.6) * 10);
    var soc = Math.round(coreNum("emu_get_soc", 100));
    var after = coreFlag("emu_get_afterrun", false);
    return [
      (fan1 | (fan2 << 1)) & 0xFF,
      ac & 0xFF,
      bv10 & 0xFF,
      soc & 0xFF,
      after & 0xFF,
      0x00, 0x00
    ];
  }

  /**
   * CAN ID 0x215 — Throttle position (8 bytes)
   * Mailbox config (CAN_PROTOCOL.md CAN0 TX 0x4EA60): CAN0 MB3, DLC 8.
   * NOTE: firmware/c/can.c counter_check_dispatch_2A242 only forwards
   * CAN_TX_BUF_0215 — no byte layout is documented there, so this is an
   * emulator best-effort 8-byte throttle frame consistent with DLC=8.
   * (Replaces the prior reuse of the 7-byte 0x203 payload, which
   * mismatched the declared dlc=8.)
   */
  function pack0x215(st) {
    var tps10 = Math.round(
      Math.max(0, Math.min(100,
        (typeof st.tps === "number" && isFinite(st.tps)) ? st.tps : 0)) * 100);
    var tpsRaw = tpsByte(st.tps, 255);
    return [
      (tps10 >> 8) & 0xFF, tps10 & 0xFF,
      tpsRaw & 0xFF,
      tpsRaw & 0xFF,
      0x00, 0x00, 0x00, 0x00
    ];
  }

  /**
   * CAN ID 0x251 — Engine data (8 bytes, every 2 cycles)
   * ROM: can251TX_getAndPack (0x2AAB6) — see firmware/c/can.c.
   * KEPT: 0x251 is real firmware traffic (CAN_ID_0251, DLC 8, MB11),
   * also listed in the CANTX_Main dispatch (CAN_PROTOCOL.md).
   */
  function pack0x251(st) {
    var rpmRaw = rpmRawU16(st.rpm);
    var ectRaw = Math.round(mapRange(st.ect, -40, 215, 0, 255));
    var mapRaw = Math.round(mapRange(st.map, 0, 105, 0, 255));
    var tpsRaw = tpsByte(st.tps, 255);
    return [
      (rpmRaw >> 8) & 0xFF,
      rpmRaw & 0xFF,
      ectRaw,
      mapRaw,
      tpsRaw,
      0x00,
      0x00,
      0x00
    ];
  }

  /**
   * CAN ID 0x240 — Transmission/gear (8 bytes)
   * ROM: can240TX_pack (0x4C888)
   */
  function pack0x240(st) {
    return [
      0x00, 0x00,
      0x00, Math.round(st.ect + 40) & 0xFF,
      0x00, 0x00,
      0x00, 0x00
    ];
  }

  /**
   * CAN ID 0x250 — Injection pulse / IAT (8 bytes)
   * ROM: can250TX_pack (0x4C984)
   */
  function pack0x250(st) {
    var iatRaw = Math.round(st.iat + 40);
    var injPw = Math.round(mapRange(st.rpm, 0, 9000, 1, 8));
    return [
      0x00, 0x00,
      0x00, iatRaw & 0xFF,
      0x00, 0x00,
      (injPw >> 8) & 0xFF, injPw & 0xFF
    ];
  }

  /**
   * CAN ID 0x231 — Engine state/gear (5 bytes)
   */
  function pack0x231(st) {
    var rpmRaw = rpmRawU16(st.rpm);
    return [
      st.rpm > 500 ? 0x01 : 0x00,
      0x00,
      (rpmRaw >> 8) & 0xFF,
      rpmRaw & 0xFF,
      0x00
    ];
  }

  /* Key-OFF ambient traffic: RX only, no ECU transmission. */
  function generateRxOnly() {
    var src = window.sensorState;
    function num(v, d) { return (typeof v === "number" && isFinite(v)) ? v : d; }
    var st = { rpm: 0, ect: num(src.ect, 80), iat: num(src.iat, 25),
      map: num(src.map, 20), tps: 0, o2f: 0.45, o2r: 0.45,
      vss: 0, oilLow: false, battLow: false, mil: false };
    var r = Math.random();
    var id, data, desc;
    if (r < 0.4) { id = 0x212; data = packRX0x212(st); desc = CAN_DESC[0x212]; }
    else if (r < 0.7) { id = 0x4B0; data = packRX0x4B0(st); desc = CAN_DESC[0x4B0]; }
    else { id = 0x430; data = packRX0x430(st); desc = CAN_DESC[0x430]; }
    return { ts: Date.now(), id: id, dlc: data.length, data: data,
      dir: "RX", desc: desc || "", uds: false };
  }

  /* ====================================================================
   *  RX frames (simulated bus traffic — ABS/DSC, immo, cluster)
   * ==================================================================== */
  function packRX0x212(st) {
    return [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00];
  }
  function packRX0x4B0(st) {
    var spd = Math.round(st.vss * 100 + 10000);
    return [
      (spd >> 8) & 0xFF, spd & 0xFF,
      (spd >> 8) & 0xFF, spd & 0xFF,
      (spd >> 8) & 0xFF, spd & 0xFF,
      (spd >> 8) & 0xFF, spd & 0xFF
    ];
  }
  function packRX0x47(st) {
    return [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00];
  }
  function packRX0x430(st) {
    return [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00];
  }

  /* Wave A1: engine state published by app.js refresh() (OFF|ON|CRANKING|
   * RUNNING|STALLED). With the key OFF the ECU is dark: TX stops, only
   * ambient RX traffic (cluster/ABS) remains on the bus. */
  function engineOff() {
    try {
      if (typeof window !== "undefined" && window.__emuEngineState === "OFF") return true;
      if (window.sensorState && Number(window.sensorState.rpm) > 0) return false;
      if (typeof window !== "undefined" && window.__emuEngineState) {
        return window.__emuEngineState === "OFF";
      }
    } catch (e) {}
    return false;
  }

  /* ====================================================================
   *  Frame generation — CANTX_Main dispatch emulation
   * ==================================================================== */
  function generateFrame() {
    if (!window.sensorState) return null;
    if (engineOff()) return generateRxOnly();
    // Local derived snapshot — never writes back to the shared
    // window.sensorState object. EngineSim exposes no MIL accessor,
    // so MIL is read read-only from sensorState (never written).
    var src = window.sensorState;
    function num(v, d) { return (typeof v === "number" && isFinite(v)) ? v : d; }
    var st = {
      rpm: num(src.rpm, 0),
      ect: num(src.ect, 80),
      iat: num(src.iat, 25),
      map: num(src.map, 35),
      tps: num(src.tps, 0),
      o2f: num(src.o2f, 0.45),
      o2r: num(src.o2r, 0.45),
      vss: num(src.vss, 0),
      /* Wave A2: oil/battery lamps follow the live core flags. */
      oilLow: coreFlag("emu_get_oil_low", src.oilLow === true) === 1,
      battLow: coreFlag("emu_get_batt_weak", src.battLow === true) === 1,
      mil: src.mil === true
    };

    var id, dlc, data, dir, desc, isUds = false;
    var rand = Math.random();

    // Per-cycle: 0x041
    if (rand < 0.15) {
      id = 0x041; dlc = 8; data = pack0x041(st); dir = "TX"; desc = CAN_DESC[0x041];
    }
    // Every 4: 0x201
    else if (rand < 0.30) {
      _counters.c201++;
      if (_counters.c201 >= 4) { _counters.c201 = 0; id = 0x201; }
      else { id = 0x203; }
      if (id === 0x201) { dlc = 8; data = pack0x201(st); } else { dlc = 7; data = pack0x203(st); }
      dir = "TX"; desc = CAN_DESC[id];
    }
    // Every 4: 0x215
    else if (rand < 0.40) {
      _counters.c215++;
      if (_counters.c215 >= 4) { _counters.c215 = 0; id = 0x215; dlc = 8; data = pack0x215(st); dir = "TX"; desc = CAN_DESC[0x215]; }
      else { id = 0x251; _counters.c251++; dlc = 8; data = pack0x251(st); dir = "TX"; desc = CAN_DESC[0x251]; }
    }
    // Every 2: 0x251
    else if (rand < 0.50) {
      _counters.c251++;
      id = 0x251; dlc = 8; data = pack0x251(st); dir = "TX"; desc = CAN_DESC[0x251];
    }
    // Per-cycle: 0x420
    else if (rand < 0.60) {
      id = 0x420; dlc = 7; data = pack0x420(st); dir = "TX"; desc = CAN_DESC[0x420];
    }
    // Per-cycle: 0x620
    else if (rand < 0.68) {
      id = 0x620; dlc = 7; data = pack0x620(st); dir = "TX"; desc = CAN_DESC[0x620];
    }
    // Per-cycle: 0x630
    else if (rand < 0.74) {
      id = 0x630; dlc = 8; data = pack0x630(st); dir = "TX"; desc = CAN_DESC[0x630];
    }
    // Every 12: 0x650
    else if (rand < 0.80) {
      _counters.c650++;
      if (_counters.c650 >= 12) { _counters.c650 = 0; id = 0x650; dlc = 1; data = pack0x650(st); dir = "TX"; desc = CAN_DESC[0x650]; }
      else { id = 0x240; dlc = 8; data = pack0x240(st); dir = "TX"; desc = CAN_DESC[0x240]; }
    }
    // Periodic: 0x250
    else if (rand < 0.86) {
      id = 0x250; dlc = 8; data = pack0x250(st); dir = "TX"; desc = CAN_DESC[0x250];
    }
    // Periodic: 0x231
    else if (rand < 0.90) {
      id = 0x231; dlc = 5; data = pack0x231(st); dir = "TX"; desc = CAN_DESC[0x231];
    }
    // RX frames (ABS/DSC, immo, cluster)
    else if (rand < 0.93) {
      id = 0x212; dlc = 7; data = packRX0x212(st); dir = "RX"; desc = CAN_DESC[0x212];
    }
    else if (rand < 0.95) {
      id = 0x4B0; dlc = 8; data = packRX0x4B0(st); dir = "RX"; desc = CAN_DESC[0x4B0];
    }
    else if (rand < 0.97) {
      id = 0x47; dlc = 8; data = packRX0x47(st); dir = "RX"; desc = CAN_DESC[0x47]; isUds = true;
    }
    else {
      id = 0x430; dlc = 7; data = packRX0x430(st); dir = "RX"; desc = CAN_DESC[0x430];
    }

    return { ts: Date.now(), id: id, dlc: dlc, data: data, dir: dir, desc: desc || "", uds: isUds };
  }

  /* ====================================================================
   *  Rendering
   * ==================================================================== */
  function dataToHex(data) {
    var parts = [];
    for (var i = 0; i < data.length; i++) {
      parts.push(("0" + data[i].toString(16).toUpperCase()).slice(-2));
    }
    return parts.join(" ");
  }

  function tsStr(ts) {
    var d = new Date(ts);
    return ("0" + d.getHours()).slice(-2) + ":" +
           ("0" + d.getMinutes()).slice(-2) + ":" +
           ("0" + d.getSeconds()).slice(-2) + "." +
           ("00" + d.getMilliseconds()).slice(-3);
  }

  /* Parse the hex filter box; empty/invalid → 0 (show all). */
  function parseFilterId() {
    if (!_filterId) return 0;
    var v = parseInt(_filterId, 16);
    return isNaN(v) ? 0 : v;
  }

  function frameRow(f) {
    var tr = document.createElement("tr");
    tr.className = f.dir === "TX" ? "can-row-tx" : "can-row-rx";
    if (f.uds) tr.className += " can-row-uds";

    tr.innerHTML =
      '<td class="ts-col">' + tsStr(f.ts) + '</td>' +
      '<td class="id-col">0x' + ("000" + f.id.toString(16).toUpperCase()).slice(-3) + '</td>' +
      '<td class="dlc-col">' + f.dlc + '</td>' +
      '<td class="data-col">' + dataToHex(f.data) + '</td>' +
      '<td class="dir-col"><span class="' + f.dir.toLowerCase() + '">' + f.dir + '</span></td>' +
      '<td class="desc-col">' + f.desc + '</td>';
    return tr;
  }

  function renderTable() {
    var tbody = document.getElementById("can-frame-body");
    if (!tbody) return;
    var wrap = document.getElementById("can-frame-wrap");
    // Capture stick-to-bottom BEFORE mutating the DOM.
    var nearBottom = true;
    if (wrap) {
      nearBottom = (wrap.scrollHeight - wrap.scrollTop - wrap.clientHeight) < 40;
    }
    var filter = parseFilterId();
    var key = _filterId || "";

    // Filter changed (or first run): rebuild only the last-50 window.
    if (key !== _lastFilterKey) {
      _lastFilterKey = key;
      tbody.innerHTML = "";
      var match = [];
      for (var k = 0; k < _frames.length; k++) {
        var mf = _frames[k];
        if (!filter || mf.id === filter) match.push(mf);
      }
      var start = Math.max(0, match.length - MAX_RENDERED);
      var frag0 = document.createDocumentFragment();
      for (var j = start; j < match.length; j++) frag0.appendChild(frameRow(match[j]));
      tbody.appendChild(frag0);
      _renderedIdx = _frames.length;
    } else {
      // Incremental: append only frames added since the last tick.
      if (_renderedIdx < 0) _renderedIdx = 0;
      if (_renderedIdx > _frames.length) _renderedIdx = _frames.length;
      var frag = document.createDocumentFragment();
      for (var i = _renderedIdx; i < _frames.length; i++) {
        var f = _frames[i];
        if (filter && f.id !== filter) continue;
        frag.appendChild(frameRow(f));
      }
      _renderedIdx = _frames.length;
      tbody.appendChild(frag);
      // Cap DOM rows to the last MAX_RENDERED.
      while (tbody.children.length > MAX_RENDERED) {
        tbody.removeChild(tbody.firstChild);
      }
    }

    // Autoscroll ONLY if the user was already near the bottom.
    if (wrap && nearBottom) wrap.scrollTop = wrap.scrollHeight;
  }

  function updateStats() {
    var el = document.getElementById("can-stats");
    if (!el) return;
    var filter = parseFilterId();
    var visible = filter ? _frames.filter(function(f) {
      return f.id === filter;
    }).length : _frames.length;
    el.innerHTML =
      '<span class="tx-count">TX: ' + _stats.tx + '</span>' +
      '<span class="rx-count">RX: ' + _stats.rx + '</span>' +
      '<span>Frames: ' + visible + '</span>';
  }

  /* ====================================================================
   *  Main loop
   * ==================================================================== */
  function tick() {
    if (_paused) return;
    var frame = generateFrame();
    if (!frame) return;

    _frames.push(frame);
    if (frame.dir === "TX") _stats.tx++; else _stats.rx++;

    // Trim (keep render index aligned with the shifted buffer)
    while (_frames.length > MAX_FRAMES) { _frames.shift(); if (_renderedIdx > 0) _renderedIdx--; }

    renderTable();
    updateStats();
  }

  /* ====================================================================
   *  Public API
   * ==================================================================== */

  /** Build and inject CAN panel into a container element */
  function init(containerId) {
    if(_timer)clearInterval(_timer);
    var container = document.getElementById(containerId);
    if (!container) return;

    container.innerHTML =
      '<div class="can-panel" id="can-panel">' +
        '<div class="can-toolbar">' +
          '<label>Filter</label>' +
          '<input type="text" id="can-filter" placeholder="ID hex">' +
          '<button class="can-btn" id="can-pause-btn">Pause</button>' +
          '<button class="can-btn" id="can-clear-btn">Clear</button>' +
          '<div class="can-stats" id="can-stats">' +
            '<span class="tx-count">TX: 0</span>' +
            '<span class="rx-count">RX: 0</span>' +
            '<span>Frames: 0</span>' +
          '</div>' +
        '</div>' +
        '<div class="can-paused-badge" id="can-paused-badge">PAUSED</div>' +
        '<div class="can-frame-wrap" id="can-frame-wrap">' +
          '<table class="can-frame-table">' +
            '<thead><tr>' +
              '<th>Time</th><th>ID</th><th>DLC</th><th>Data</th><th>Dir</th><th>Description</th>' +
            '</tr></thead>' +
            '<tbody id="can-frame-body"></tbody>' +
          '</table>' +
        '</div>' +
      '</div>';

    var _table = container.querySelector(".can-frame-table");
    if (_table) {
      var _cap = document.createElement("caption");
      _cap.textContent = "Live CAN frames \u2014 time, ID, DLC, data bytes, direction, description";
      _table.insertBefore(_cap, _table.firstChild);
    }

    // Wire controls
    document.getElementById("can-filter").addEventListener("input", function(e) {
      _filterId = e.target.value.trim();
      renderTable();
      updateStats();
    });

    document.getElementById("can-pause-btn").addEventListener("click", function() {
      _paused = !_paused;
      this.textContent = _paused ? "Resume" : "Pause";
      this.classList.toggle("active", _paused);
      document.getElementById("can-paused-badge").classList.toggle("visible", _paused);
    });

    document.getElementById("can-clear-btn").addEventListener("click", function() {
      _frames = [];
      _stats.tx = 0;
      _stats.rx = 0;
      _renderedIdx = 0;
      _lastFilterKey = "\0"; // force renderTable() to rebuild (empty) tbody
      renderTable();
      updateStats();
    });

    // Start
    _running = true;
    _renderedIdx = 0;
    _lastFilterKey = "\0"; // force first renderTable() to build the window
    _timer = setInterval(tick, FRAME_INTERVAL_MS);
  }

  /** Stop the frame generator */
  function stop() {
    _running = false;
    if (_timer) { clearInterval(_timer); _timer = null; }
  }

  /* Wave A3 frame tap: frames added since `idx` (for the per-pin live
   * data + waveform raster). Returns { frames, next }. No DOM touched. */
  function since(idx) {
    if (typeof idx !== "number" || !(idx >= 0)) idx = 0;
    if (idx > _frames.length) idx = _frames.length;
    return { frames: _frames.slice(idx), next: _frames.length };
  }

  /* Wave A3: most recent frame overall (copy) or null when empty. */
  function last() {
    if (_frames.length === 0) return null;
    var f = _frames[_frames.length - 1];
    return { ts: f.ts, id: f.id, dlc: f.dlc, data: f.data.slice(0),
      dir: f.dir, desc: f.desc, uds: f.uds };
  }

  /* Wave A3: most recent frame with a given CAN id (copy) or null. */
  function lastId(id) {
    for (var i = _frames.length - 1; i >= 0; i--) {
      if (_frames[i].id === id) {
        var f = _frames[i];
        return { ts: f.ts, id: f.id, dlc: f.dlc, data: f.data.slice(0),
          dir: f.dir, desc: f.desc, uds: f.uds };
      }
    }
    return null;
  }

  /* Wave A3: live TX/RX counters (copy). */
  function counts() {
    return { tx: _stats.tx, rx: _stats.rx };
  }

  /* Wave A2 headless test hook: pack one frame for `id` from the current
   * live state (core fans/battery + window.sensorState). Returns
   * { id, dlc, data } or null for unknown ids. No DOM touched. */
  function pack(id) {
    if (typeof window === "undefined" || !window.sensorState) return null;
    var src = window.sensorState;
    function num(v, d) { return (typeof v === "number" && isFinite(v)) ? v : d; }
    var st = {
      rpm: num(src.rpm, 0), ect: num(src.ect, 80), iat: num(src.iat, 25),
      map: num(src.map, 35), tps: num(src.tps, 0),
      o2f: num(src.o2f, 0.45), o2r: num(src.o2r, 0.45), vss: num(src.vss, 0),
      oilLow: coreFlag("emu_get_oil_low", false) === 1,
      battLow: coreFlag("emu_get_batt_weak", false) === 1,
      mil: src.mil === true
    };
    var table = { 0x201: 8, 0x203: 7, 0x420: 7, 0x630: 8, 0x620: 7,
      0x215: 8, 0x251: 8, 0x240: 8, 0x250: 8, 0x231: 5, 0x650: 1, 0x041: 8 };
    var fn = { 0x201: pack0x201, 0x203: pack0x203, 0x420: pack0x420,
      0x630: pack0x630, 0x620: pack0x620, 0x215: pack0x215, 0x251: pack0x251,
      0x240: pack0x240, 0x250: pack0x250, 0x231: pack0x231, 0x650: pack0x650,
      0x041: pack0x041 }[id];
    if (!fn || table[id] === undefined) return null;
    var data = fn(st);
    return { id: id, dlc: table[id], data: data };
  }

  return { init: init, stop: stop, pack: pack,
    since: since, last: last, lastId: lastId, counts: counts };
})();

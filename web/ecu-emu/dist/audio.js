/**
 * audio.js — Rotary engine sound for the RX-8 ECU Emulator (Web Audio API).
 *
 * Architecture: pure param-mapping functions (fundHz/paramsFor — testable in
 * node, no browser needed) + a small AudioContext engine that renders them.
 *
 * Physics: a Renesis has 2 rotors x 3 faces = 6 combustion events per
 * revolution, so the exhaust fundamental is RPM/60 x 6 (900 Hz at 9000 rpm).
 * The engine renders an oscillator stack (fundamental + 2nd/3rd harmonics)
 * plus filtered noise (exhaust broadband), with gain following throttle/load
 * and the lowpass cutoff following RPM. While CRANKING the starter chugs at
 * ~150-300 rpm equivalent (a slow amplitude wobble); radiator fans add soft
 * noise when fanLow/fanHigh are on.
 *
 * Autoplay policy: the AudioContext is created/resumed only inside unlock(),
 * which the UI calls from user gestures (first click/keydown) and on tab
 * visibility. Every public method is safe to call with no AudioContext
 * (headless/node): mapping + mute/volume state work, audio output no-ops.
 */
"use strict";

var AudioEngine = (function() {

  /* ====================================================================
   *  Pure param mapping (no DOM, no AudioContext — unit-tested in node)
   * ==================================================================== */
  var MAX_RPM = 12000;      // sim/UI ceiling (mirrors engine_sim/app)
  var EVENTS_PER_REV = 6;   // 2 rotors x 3 faces = 6 combustions per rev

  function safeRPM(rpm) {
    var r = Number(rpm);
    if (!Number.isFinite(r)) return 0; // NaN/Inf -> silent-safe default
    if (r < 0) return 0;
    if (r > MAX_RPM) return MAX_RPM;
    return r;
  }
  function safeLoad(load) {
    var l = Number(load);
    if (!Number.isFinite(l)) return 0; // NaN -> silent-safe default
    if (l < 0) return 0;
    if (l > 100) return 100;
    return l;
  }

  /* Exhaust fundamental in Hz: 900 Hz at 9000 rpm. */
  function fundHz(rpm) {
    return safeRPM(rpm) / 60 * EVENTS_PER_REV;
  }

  /* Full voice params for an (rpm, load%) state.
   * opts: { cranking: bool, fanLow: bool, fanHigh: bool } (all optional).
   * Returns plain JSON (no NaN field on any input, edges included). */
  function paramsFor(rpm, load, opts) {
    var r = safeRPM(rpm);
    var l = safeLoad(load);
    var o = opts || {};
    var fund = r / 60 * EVENTS_PER_REV;
    var gain = 0.04 + 0.45 * (l / 100); // gain follows throttle/load
    if (r <= 0) gain = 0;               // stopped engine: silent
    var cutoff = 300 + 0.5 * r;         // lowpass cutoff follows RPM
    var crank = !!o.cranking;
    var chugHz = crank ? Math.max(1, r / 60) : 0; // rev/s starter wobble
    var fanGain = o.fanHigh ? 0.06 : (o.fanLow ? 0.03 : 0);
    return {
      rpm: r, fund: fund, harm2: fund * 2, harm3: fund * 3,
      gain: gain, cutoff: cutoff,
      cranking: crank, chugHz: chugHz, fanGain: fanGain
    };
  }

  /* ====================================================================
   *  Mute / volume state (persisted in localStorage, guarded for node)
   * ==================================================================== */
  var STORE_KEY = "rx8emu.audio.v1";
  var _muted = true;   // default OFF until the user opts in (autoplay-friendly)
  var _volume = 70;    // 0..100

  function persist() {
    try {
      if (typeof localStorage !== "undefined") {
        localStorage.setItem(STORE_KEY, JSON.stringify({ m: _muted ? 1 : 0, v: _volume }));
      }
    } catch (e) {}
  }
  function restore() {
    try {
      if (typeof localStorage !== "undefined") {
        var raw = localStorage.getItem(STORE_KEY);
        if (raw) {
          var s = JSON.parse(raw);
          if (s && typeof s === "object") {
            if (s.m !== undefined) _muted = !!s.m;
            if (Number.isFinite(Number(s.v))) {
              _volume = Math.max(0, Math.min(100, Math.round(Number(s.v))));
            }
          }
        }
      }
    } catch (e) {}
    return { muted: _muted, volume: _volume };
  }
  restore();

  function isMuted() { return _muted; }
  function toggleMute() { _muted = !_muted; persist(); applyGains(); return _muted; }
  function setMuted(m) { _muted = !!m; persist(); applyGains(); return _muted; }
  function getVolume() { return _volume; }
  function setVolume(v) {
    v = Number(v);
    if (!Number.isFinite(v)) return _volume;
    _volume = Math.max(0, Math.min(100, Math.round(v)));
    persist(); applyGains();
    return _volume;
  }

  /* ====================================================================
   *  AudioContext engine (browser only; every entry no-ops without one)
   * ==================================================================== */
  var _ctx = null;       // AudioContext, created only in unlock()
  var _master = null;    // master volume gain
  var _muteG = null;     // mute gate gain
  var _mixG = null;      // voice mix gain (load-driven)
  var _filt = null;      // lowpass (RPM-driven cutoff)
  var _oscs = [];        // [fund, 2nd, 3rd] oscillators
  var _noiseG = null;    // exhaust-noise gain
  var _fanG = null;      // fan-noise gain
  var _lfo = null;       // cranking chug LFO
  var _lfoG = null;
  var _timer = null;     // poll loop (~10 Hz)

  function hasAudio() {
    try {
      return typeof AudioContext !== "undefined";
    } catch (e) { return false; }
  }

  function applyGains() {
    try {
      if (!_ctx || !_master || !_muteG) return;
      var t = _ctx.currentTime;
      _master.gain.setTargetAtTime(_volume / 100 * 0.9, t, 0.05);
      _muteG.gain.setTargetAtTime(_muted ? 0 : 1, t, 0.05);
    } catch (e) {}
  }

  function makeNoise(ctx) {
    var len = ctx.sampleRate * 1;
    var buf = ctx.createBuffer(1, len, ctx.sampleRate);
    var d = buf.getChannelData(0);
    for (var i = 0; i < len; i++) d[i] = Math.random() * 2 - 1;
    var src = ctx.createBufferSource();
    src.buffer = buf;
    src.loop = true;
    return src;
  }

  /* Create/resume the context. MUST be called from a user gesture
   * (autoplay policy); safe to call anywhere otherwise (no-ops headless). */
  function unlock() {
    if (!hasAudio()) return false;
    try {
      if (!_ctx) {
        var AC = AudioContext;
        _ctx = new AC();
        _master = _ctx.createGain();
        _muteG = _ctx.createGain();
        _mixG = _ctx.createGain();
        _filt = _ctx.createBiquadFilter();
        _filt.type = "lowpass";
        _filt.frequency.value = 800;
        _mixG.connect(_filt);
        _filt.connect(_muteG);
        _muteG.connect(_master);
        _master.connect(_ctx.destination);
        var types = ["sawtooth", "sine", "sine"];
        var gains = [0.5, 0.25, 0.12];
        for (var i = 0; i < 3; i++) {
          var o = _ctx.createOscillator();
          o.type = types[i];
          o.frequency.value = 80 * (i + 1);
          var g = _ctx.createGain();
          g.gain.value = gains[i];
          o.connect(g);
          g.connect(_mixG);
          o.start();
          _oscs.push(o);
        }
        var nz = makeNoise(_ctx);
        _noiseG = _ctx.createGain();
        _noiseG.gain.value = 0.15;
        nz.connect(_noiseG);
        _noiseG.connect(_filt);
        nz.start();
        var fnz = makeNoise(_ctx);
        var fbp = _ctx.createBiquadFilter();
        fbp.type = "bandpass";
        fbp.frequency.value = 1200;
        _fanG = _ctx.createGain();
        _fanG.gain.value = 0;
        fnz.connect(fbp);
        fbp.connect(_fanG);
        _fanG.connect(_muteG);
        fnz.start();
        /* Cranking chug: slow LFO on the mix gain (started on demand). */
        _lfo = _ctx.createOscillator();
        _lfo.type = "sine";
        _lfo.frequency.value = 4;
        _lfoG = _ctx.createGain();
        _lfoG.gain.value = 0;
        _lfo.connect(_lfoG);
        _lfoG.connect(_mixG.gain);
        _lfo.start();
        applyGains();
        startPoll();
      }
      if (_ctx.state === "suspended") _ctx.resume();
      return true;
    } catch (e) { return false; }
  }

  function liveInputs() {
    var rpm = 0, load = 0, cranking = false, fanLow = false, fanHigh = false;
    try {
      if (typeof window !== "undefined" && window.sensorState) {
        var s = window.sensorState;
        if (Number.isFinite(Number(s.rpm))) rpm = Number(s.rpm);
        if (Number.isFinite(Number(s.tps))) load = Number(s.tps);
      }
      if (typeof Module !== "undefined" && Module) {
        if (typeof Module.emu_get_engine_state === "function") {
          cranking = Module.emu_get_engine_state() === "CRANKING";
        }
        if (typeof Module.emu_get_fan === "function") {
          fanLow = Module.emu_get_fan(0) === 1;
          fanHigh = Module.emu_get_fan(1) === 1;
        }
      }
    } catch (e) {}
    return { rpm: rpm, load: load, cranking: cranking, fanLow: fanLow, fanHigh: fanHigh };
  }

  /* Push one param set into the live graph (smooth, no clicks). */
  function render(p) {
    if (!_ctx) return false;
    try {
      var t = _ctx.currentTime;
      var f = Math.max(1, p.fund);
      _oscs[0].frequency.setTargetAtTime(f, t, 0.05);
      _oscs[1].frequency.setTargetAtTime(Math.max(1, p.harm2), t, 0.05);
      _oscs[2].frequency.setTargetAtTime(Math.max(1, p.harm3), t, 0.05);
      _mixG.gain.setTargetAtTime(p.gain, t, 0.08);
      _filt.frequency.setTargetAtTime(p.cutoff, t, 0.08);
      _noiseG.gain.setTargetAtTime(0.05 + 0.3 * (p.gain), t, 0.1);
      _fanG.gain.setTargetAtTime(p.fanGain, t, 0.2);
      _lfo.frequency.setTargetAtTime(p.chugHz > 0 ? p.chugHz : 4, t, 0.1);
      _lfoG.gain.setTargetAtTime(p.cranking ? 0.15 : 0, t, 0.1);
      return true;
    } catch (e) { return false; }
  }

  function poll() {
    if (!_ctx || _muted) return;
    var inp = liveInputs();
    render(paramsFor(inp.rpm, inp.load, inp));
  }
  function startPoll() {
    try {
      if (_timer) clearInterval(_timer);
      _timer = setInterval(poll, 100);
    } catch (e) {}
  }
  function stop() {
    try { if (_timer) { clearInterval(_timer); _timer = null; } } catch (e) {}
    try { if (_ctx) _ctx.close(); } catch (e) {}
    _ctx = null; _oscs = [];
  }

  return {
    MAX_RPM: MAX_RPM, EVENTS_PER_REV: EVENTS_PER_REV,
    fundHz: fundHz, paramsFor: paramsFor, safeRPM: safeRPM, safeLoad: safeLoad,
    isMuted: isMuted, toggleMute: toggleMute, setMuted: setMuted,
    getVolume: getVolume, setVolume: setVolume,
    hasAudio: hasAudio, unlock: unlock, render: render, stop: stop
  };
})();

if (typeof module !== "undefined" && module.exports) {
  module.exports = AudioEngine;
}

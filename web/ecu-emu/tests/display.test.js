"use strict";
/* Display-formatting regression suite (user-reported screenshot bugs):
 *  1. raw floats (20.14572472704549°C) must render rounded, never 15 decimals
 *  2. MAP engine-off must read ~barometric (~100 kPa), not 20 kPa vacuum
 *  3. duplicate 0.45V rows must trace to DISTINCT sources (o2f vs o2r)
 *  4. unit strings take a single space ("20 kPa", "0.45 V", never "20KPA")
 * NaN policy: non-finite or absurd (>=1e15) renders as "—" (explorer
 * policy), never "NaN"/"Infinity"/"undefined"/"1e+21".
 * node stdlib only. */

const { describe, it, beforeEach } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { loadCore, loadPins, loadApp, loadEngineSim } = require("./helpers");

const SRC = path.join(__dirname, "..", "src");
const APP_TEXT = fs.readFileSync(path.join(SRC, "app.js"), "utf8");
const SIM_TEXT = fs.readFileSync(path.join(SRC, "engine_sim.js"), "utf8");
const CORE_TEXT = fs.readFileSync(path.join(SRC, "emu_core.js"), "utf8");
const HTML = fs.readFileSync(path.join(SRC, "index.html"), "utf8");

/* Numeric sensor readout: integer or decimals + optional spaced unit,
 * or the "—" placeholder for non-finite input. */
const NUM_RE = /^-?\d+(\.\d+)?\s?(°C|kPa|V|%|rpm|ms|Hz|A|°\/s)?$/;

const ADVERSARIAL = [20.14572472704549, NaN, Infinity, -Infinity, -0, 1e21, undefined, "junk"];
const SENSOR_KEYS = ["rpm", "ect", "iat", "map", "tps", "o2f", "o2r"];

/* Capture document: every id auto-materializes a stub element so
 * updateSliders/refreshVehicle always have something to write into. */
function makeCaptureDoc() {
  const els = {};
  function get(id) {
    if (!els[id]) {
      els[id] = {
        textContent: "", value: "", style: {}, dataset: {},
        classList: { add() {}, remove() {}, toggle() {} },
      };
    }
    return els[id];
  }
  return {
    els,
    getElementById: (id) => get(id),
    querySelector: () => null,
    querySelectorAll: () => [],
    createElement: () => ({
      children: [], dataset: {},
      classList: { add() {}, remove() {}, toggle() {} },
      appendChild(c) { this.children.push(c); return c; },
      append() {}, setAttribute() {}, addEventListener() {}, style: {},
    }),
    createDocumentFragment: () => ({ appendChild() {} }),
    addEventListener() {},
    activeElement: null,
  };
}

let M, doc, sb;
beforeEach(() => {
  M = loadCore();
  M.emu_init();
  M.emu_set_pins(loadPins().pins);
  doc = makeCaptureDoc();
  sb = loadApp(M, doc);
});

describe("formatter contract (app.js fmt family)", () => {
  it("rounds the screenshot value: 20.14572472704549°C -> 20.1 °C", () => {
    assert.strictEqual(sb.fmtSensor("ect", 20.14572472704549), "20.1 °C");
    assert.strictEqual(sb.fmtTemp(20.14572472704549), "20.1 °C");
  });
  it("per-quantity digits: temps 1, volts 2, rpm/kPa/% integers", () => {
    assert.strictEqual(sb.fmtTemp(80), "80.0 °C");
    assert.strictEqual(sb.fmtVolt(0.45), "0.45 V");
    assert.strictEqual(sb.fmtRPM(800), "800 rpm");
    assert.strictEqual(sb.fmtKPa(100), "100 kPa");
    assert.strictEqual(sb.fmtPct0(25), "25%");
    assert.strictEqual(sb.fmtPct1(12.34), "12.3%");
    assert.strictEqual(sb.fmtHz(50), "50.0 Hz");
    assert.strictEqual(sb.fmtMs2(1.234), "1.23 ms");
    assert.strictEqual(sb.fmtAmps(5.25), "5.3 A");
  });
  it("NaN policy: NaN/Inf/undefined/junk/1e21 -> —, -0 -> 0 (never leaks)", () => {
    for (const bad of [NaN, Infinity, -Infinity, undefined, "junk", 1e21, -1e21]) {
      assert.strictEqual(sb.fmt(bad, 1, "°C"), "—", "fmt(" + String(bad) + ")");
      assert.strictEqual(sb.fmtSensor("ect", bad), "—", "ect(" + String(bad) + ")");
      assert.strictEqual(sb.fmtSensor("map", bad), "—", "map(" + String(bad) + ")");
      assert.strictEqual(sb.fmtSensor("o2f", bad), "—", "o2f(" + String(bad) + ")");
    }
    assert.strictEqual(sb.fmtKPa(-0), "0 kPa", "-0 normalizes");
    assert.strictEqual(sb.fmtRPM(-0), "0 rpm");
  });
  it("unit spacing: single space before °C/kPa/V/rpm/ms/Hz/A, % attaches", () => {
    assert.match(sb.fmtKPa(20), /^20 kPa$/);
    assert.match(sb.fmtVolt(0.45), /^0\.45 V$/);
    assert.match(sb.fmtTemp(20), /^20\.0 °C$/);
    assert.match(sb.fmtRPM(800), /^800 rpm$/);
    assert.match(sb.fmtPct0(50), /^50%$/);
    assert.ok(!sb.fmtKPa(20).includes("KPA"), "no uppercase KPA unit");
    assert.ok(!/20KPA|20kPa|0\.45V/.test(sb.fmtKPa(20) + sb.fmtVolt(0.45)),
      "spaced units, never concatenated");
  });
});

describe("dashboard sensor rows (updateSliders integration)", () => {
  it("every row renders adversarial values without raw floats or NaN leaks", () => {
    for (const key of SENSOR_KEYS) {
      for (const v of ADVERSARIAL) {
        sb.window.sensorState[key] = v;
        sb.updateSliders();
        const txt = doc.els["val-" + key].textContent;
        assert.ok(
          txt === "—" || NUM_RE.test(txt),
          `${key}=${String(v)} rendered as ${JSON.stringify(txt)}`
        );
        assert.ok(!txt.includes("NaN") && !txt.includes("Infinity") &&
          !txt.includes("undefined") && !txt.includes("e+"),
          `${key}=${String(v)} leaks: ${JSON.stringify(txt)}`);
        // 15-decimal floats never survive: at most the quantity's digits
        const frac = (txt.match(/\.(\d+)/) || [])[1] || "";
        assert.ok(frac.length <= 2, `${key} over-precise: ${JSON.stringify(txt)}`);
      }
    }
  });
  it("screenshot case: ECT 20.145... shows 20.1 °C and MAP shows spaced kPa", () => {
    sb.window.sensorState.ect = 20.14572472704549;
    sb.window.sensorState.map = 20;
    sb.updateSliders();
    assert.strictEqual(doc.els["val-ect"].textContent, "20.1 °C");
    assert.strictEqual(doc.els["val-map"].textContent, "20 kPa");
  });
});

describe("duplicate 0.45V verdict (O2 front vs rear)", () => {
  it("O2 tab mirrors track DISTINCT sources (o2f vs o2r), not one binding", () => {
    sb.window.sensorState.o2f = 0.11;
    sb.window.sensorState.o2r = 0.89;
    sb.updateSliders();
    assert.strictEqual(doc.els["o2f-tab-val"].textContent, "0.11 V");
    assert.strictEqual(doc.els["o2r-tab-val"].textContent, "0.89 V");
    assert.notStrictEqual(doc.els["o2f-tab-val"].textContent,
      doc.els["o2r-tab-val"].textContent, "mirrors diverge with distinct inputs");
  });
  it("O2 live readouts track distinct ADC channels (front=ADC4, rear=ADC5)", () => {
    sb.window.sensorState.o2f = 0.11;
    sb.window.sensorState.o2r = 0.89;
    M.emu_set_sensor(5, 0.11);
    M.emu_set_sensor(6, 0.89);
    M.emu_step_ms(10);
    sb.updateSliders();
    const f = doc.els["o2f-read"].textContent;
    const r = doc.els["o2r-read"].textContent;
    assert.ok(f.startsWith("0.11 V"), "front readout follows o2f, got " + f);
    assert.ok(r.startsWith("0.89 V"), "rear readout follows o2r, got " + r);
    assert.ok(f.includes("ADC " + M.emu_get_adc(4)), "front ADC4, got " + f);
    assert.ok(r.includes("ADC " + M.emu_get_adc(5)), "rear ADC5, got " + r);
  });
  it("at rest bias both legitimately read 0.45 V (narrowband rest, not a copy-paste bug)", () => {
    sb.window.sensorState.o2f = 0.45;
    sb.window.sensorState.o2r = 0.45;
    sb.updateSliders();
    assert.strictEqual(doc.els["o2f-tab-val"].textContent, "0.45 V");
    assert.strictEqual(doc.els["o2r-tab-val"].textContent, "0.45 V");
    // sources are distinct bindings that merely converge at rest:
    assert.ok(APP_TEXT.includes('["o2f-tab", "o2f", "o2f-tab-val"]'),
      "front mirror bound to o2f");
    assert.ok(APP_TEXT.includes('["o2r-tab", "o2r", "o2r-tab-val"]'),
      "rear mirror bound to o2r");
    assert.ok(APP_TEXT.includes("Module.emu_get_adc(4)") &&
      APP_TEXT.includes("Module.emu_get_adc(5)"),
      "readouts use distinct ADC channels 4/5");
  });
  it("no two dashboard slider defs share a sensor key", () => {
    const keys = [...APP_TEXT.matchAll(/\{key:"(\w+)"/g)].map((m) => m[1]);
    assert.deepStrictEqual([...keys].sort(),
      ["ect", "iat", "map", "o2f", "o2r", "rpm", "tps"]);
    assert.strictEqual(new Set(keys).size, keys.length, "slider keys unique");
  });
});

describe("MAP engine-off default (~baro, not 20 kPa vacuum)", () => {
  it("app sensorState boots at ~100 kPa", () => {
    assert.ok(Math.abs(sb.window.sensorState.map - 100) <= 2,
      "sensorState.map=" + sb.window.sensorState.map);
  });
  it("core boots at ~100 kPa (emu_init, not decel vacuum)", () => {
    const map = M.emu_get_sensor(3);
    assert.ok(Math.abs(map - 100) <= 2, "core map=" + map);
  });
  it("engine-sim OFF branch holds baro (source guard)", () => {
    assert.ok(/if \(es === "OFF"\) \{ st\.map = 100;/.test(SIM_TEXT),
      "OFF branch sets 100 kPa");
    assert.ok(!/es === "OFF"[^}]*st\.map = 20/.test(SIM_TEXT),
      "no 20 kPa left on the OFF path");
  });
  it("MAP=20 sources are gone from boot defaults (decel scenario keeps its own 20)", () => {
    assert.ok(!/let sensorState = \{[^}]*map: 20/.test(APP_TEXT),
      "app sensorState no longer 20");
    assert.ok(!/_iat = _cal\.ambient; _map = 20;/.test(CORE_TEXT),
      "core emu_init no longer 20");
  });
});

describe("unit-string sweep (no concatenated units)", () => {
  it("no missing-space unit renders survive in src or static HTML", () => {
    for (const bad of ["0.45V", "20KPA", "20kPa", "80°C"]) {
      assert.ok(!APP_TEXT.includes('"' + bad + '"') &&
        !SIM_TEXT.includes('"' + bad + '"'),
        "JS must not contain literal " + bad);
    }
    assert.ok(HTML.includes("0.45 V"), "static O2 tab vals spaced");
    assert.ok(!HTML.includes(">0.45V<"), "no concatenated static O2 volt");
  });
  it("engine-sim formatter matches the app contract", () => {
    const box = loadEngineSim({ rpm: 0, ect: 80, iat: 25, map: 100, tps: 0, o2f: 0.45, o2r: 0.45 });
    const E = box.EngineSim;
    assert.strictEqual(E.fmt(20.14572472704549, 1, "°C"), "20.1 °C");
    assert.strictEqual(E.fmt(NaN, 2, "V"), "—");
    assert.strictEqual(E.fmt(1e21, 0, "kPa"), "—");
  });
});

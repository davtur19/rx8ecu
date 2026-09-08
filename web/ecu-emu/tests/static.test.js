"use strict";
/* Static wiring suite (no browser needed): DOM ids, tab wiring, core-API
 * coverage, calibration keys, pins.json schema, immo single-store, and
 * src->dist sync. Fails on typos/renames that would break the UI silently.
 * node stdlib only. */

const { describe, it } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { srcText, loadCore, loadPins } = require("./helpers");

const DIST = path.join(__dirname, "..", "dist");
const JS_FILES = ["app.js", "engine_sim.js", "can_live.js"];
const JS = Object.fromEntries(JS_FILES.map((f) => [f, srcText(f)]));
const HTML = srcText("index.html");
const CSS = srcText("style.css") + "\n" + srcText("can_live.css");

function htmlIds() {
  return new Set([...HTML.matchAll(/ id="([^"]+)"/g)].map((m) => m[1]));
}
function jsCreatedIds() {
  const out = new Set();
  for (const f of JS_FILES) {
    // id="..." inside JS-built HTML strings, plus el.id = "..." assignments
    for (const m of JS[f].matchAll(/id=\\?"([^"\\]+)"/g)) {
      if (!m[1].includes("${")) out.add(m[1]);
    }
    for (const m of JS[f].matchAll(/\.id\s*=\s*["']([^"']+)["']/g)) out.add(m[1]);
  }
  return out;
}
/* DOM ids referenced positionally: getElementById literals, setText() call
 * args, drawTacho/drawGauge canvas args, cal-* config literals, o2 mirror
 * literals, and static #ids inside querySelector(All). Template-built
 * slider-/val- ids are covered separately (prefix x sensor-key check). */
function referencedIds() {
  const out = new Set();
  const add = (re, f) => {
    for (const m of JS[f].matchAll(re)) if (!m[1].includes("${")) out.add(m[1]);
  };
  for (const f of JS_FILES) {
    add(/getElementById\(\s*["'`]([^"'`]+)["'`]\s*\)/g, f);
    add(/setText\(\s*"([^"]+)"/g, f);
    add(/draw(?:Tacho|Gauge)\(\s*"([^"]+)"/g, f);
    for (const m of JS[f].matchAll(/querySelector(All)?\(\s*["'`]([^"'`]+)["'`]/g)) {
      const sel = m[2];
      if (sel.includes("$") || sel.includes("[")) continue; // dynamic lookup
      for (const h of sel.matchAll(/#([A-Za-z0-9_-]+)/g)) out.add(h[1]);
    }
  }
  for (const m of JS["app.js"].matchAll(/"(cal-[a-z0-9-]+)"/g)) out.add(m[1]);
  for (const m of JS["app.js"].matchAll(/"(o2[fr]-[a-z-]+)"/g)) out.add(m[1]);
  return out;
}

describe("DOM wiring: every referenced id exists", () => {
  // Back-compat guard in engine_sim tick(): drawn only when present.
  const LEGACY_OPTIONAL = new Set(["gauge-rpm"]);
  // renderSliders/updateSliders build slider-<k>/val-<k> per sensor key.
  const TEMPLATE_PREFIX = ["slider-", "val-"];
  const SENSOR_KEYS = ["rpm", "ect", "iat", "map", "tps", "o2f", "o2r"];

  it("referenced ids resolve to index.html or JS-created nodes", () => {
    const have = new Set([...htmlIds(), ...jsCreatedIds()]);
    const missing = [...referencedIds()].filter((id) => {
      if (have.has(id) || LEGACY_OPTIONAL.has(id)) return false;
      if (TEMPLATE_PREFIX.some((p) => id.startsWith(p))) {
        const key = id.slice(id.indexOf("-") + 1);
        return !SENSOR_KEYS.includes(key); // unknown key under a known prefix
      }
      return true;
    });
    assert.deepStrictEqual(missing, [], "unresolvable DOM ids: " + missing.join(", "));
  });

  it("slider/val templates cover exactly the 7 sensor keys", () => {
    for (const k of SENSOR_KEYS) {
      assert.ok(JS["app.js"].includes(`{key:"${k}"`), "slider def for " + k);
    }
  });

  it("tab buttons (data-tab) each have a matching tab-<name> section", () => {
    const tabs = [...HTML.matchAll(/data-tab="([^"]+)"/g)].map((m) => m[1]);
    assert.ok(tabs.length >= 6, "expected the 6 view tabs");
    for (const t of tabs) {
      assert.ok(HTML.includes(`id="tab-${t}"`), "section tab-" + t);
    }
  });

  it("querySelector class targets resolve to HTML/CSS/JS-created classes", () => {
    const known = new Set();
    for (const m of HTML.matchAll(/class="([^"]+)"/g)) {
      for (const c of m[1].split(/\s+/)) known.add(c);
    }
    for (const m of CSS.matchAll(/\.([A-Za-z0-9_-]+)/g)) known.add(m[1]);
    for (const f of JS_FILES) {
      for (const m of JS[f].matchAll(/className\s*=\s*["']([^"'`]+)["']/g)) {
        for (const c of m[1].split(/\s+/)) known.add(c);
      }
      for (const m of JS[f].matchAll(/classList\.(?:add|toggle|remove)\(\s*"([^"]+)"/g)) {
        known.add(m[1]);
      }
    }
    // Dynamic direction words emitted by the CAN row renderer (CSS-defined).
    known.add("tx");
    known.add("rx");
    const bad = [];
    for (const f of JS_FILES) {
      for (const m of JS[f].matchAll(/querySelector(All)?\(\s*["'`]([^"'`]+)["'`]/g)) {
        const sel = m[2];
        if (sel.includes("$") || sel.includes("[") || /^[a-z]+$/.test(sel)) continue;
        for (const c of sel.matchAll(/\.([A-Za-z0-9_-]+)/g)) {
          if (!known.has(c[1])) bad.push(`${f}: .${c[1]}`);
        }
      }
    }
    assert.deepStrictEqual(bad, [], "unresolvable classes: " + bad.join(", "));
  });
});

describe("core API coverage", () => {
  it("every Module.* name used by the UI exists on emu_core", () => {
    const core = loadCore();
    const names = new Set();
    for (const f of JS_FILES) {
      for (const m of JS[f].matchAll(/Module\.([A-Za-z_$][\w$]*)/g)) names.add(m[1]);
      for (const m of JS[f].matchAll(/(?:coreFlag|coreNum[A-Z0-9]*|coreFan)\(\s*"([^"]+)"/g)) {
        names.add(m[1]);
      }
    }
    assert.ok(names.size > 30, "expected a wide API surface, got " + names.size);
    const missing = [...names].filter((n) => typeof core[n] !== "function");
    assert.deepStrictEqual(missing, [], "missing core APIs: " + missing.join(", "));
  });
});

describe("calibration key consistency", () => {
  it("UI CAL_DEFAULTS keys exist in the core (soc rides emu_set_soc)", () => {
    const m = JS["app.js"].match(/CAL_DEFAULTS\s*=\s*\{([^}]+)\}/);
    assert.ok(m, "CAL_DEFAULTS found");
    const uiKeys = [...m[1].matchAll(/(\w+)\s*:/g)].map((x) => x[1]);
    const core = loadCore();
    const coreKeys = Object.keys(core.emu_cal_get());
    const missing = uiKeys.filter((k) => k !== "soc" && !coreKeys.includes(k));
    assert.deepStrictEqual(missing, [], "cal keys missing in core: " + missing.join(", "));
    assert.strictEqual(typeof core.emu_set_soc, "function", "soc path exists");
  });
  it("stock defaults are intact (redline 9000, fans 95/90/105/100)", () => {
    const core = loadCore();
    assert.deepStrictEqual(core.emu_cal_get(), {
      fanLowOn: 95, fanLowOff: 90, fanHighOn: 105, fanHighOff: 100,
      ambient: 20, redline: 9000, fuelCutEn: 1,
    });
  });
  it("key-code single store: UI holds no immo state of its own", () => {
    for (const f of JS_FILES) {
      assert.ok(!/\b(_immoStored|immoStored|_keyCodeStored)\b/.test(JS[f]),
        f + " must not duplicate the stored code");
    }
    assert.ok(JS["app.js"].includes("Module.emu_set_key_code"),
      "key edits flow through the core store");
    assert.ok(JS["app.js"].includes("key-code") && JS["app.js"].includes("cal-keycode"),
      "both key inputs (Vehicle + Calibration) stay linked");
  });
  it("calibration persists under one localStorage key", () => {
    const hits = [...JS["app.js"].matchAll(/CAL_KEY/g)].length;
    assert.ok(hits >= 3, "CAL_KEY declared + getItem + setItem, hits=" + hits);
  });
});

describe("pins.json schema", () => {
  const KNOWN_TYPES = new Set(["power", "gnd", "analog", "digital", "can", "sci", "nc"]);
  const KNOWN_DIRS = new Set(["in", "out", "io", "na"]);
  it("96 pins, numbers 1..96 unique, required fields, known type/dir", () => {
    const pins = loadPins().pins;
    assert.strictEqual(pins.length, 96);
    const nums = pins.map((p) => p.num).sort((a, b) => a - b);
    assert.deepStrictEqual(nums, Array.from({ length: 96 }, (_, i) => i + 1));
    for (const p of pins) {
      for (const k of ["num", "name", "type", "dir", "goes_to", "voltage"]) {
        assert.ok(p[k] !== undefined, `pin ${p.num} missing ${k}`);
      }
      assert.ok(KNOWN_TYPES.has(p.type), `pin ${p.num} type ${p.type}`);
      assert.ok(KNOWN_DIRS.has(p.dir), `pin ${p.num} dir ${p.dir}`);
      assert.ok(Array.isArray(p.voltage) && p.voltage.length === 2, `pin ${p.num} voltage pair`);
      assert.ok(p.voltage[0] <= p.voltage[1], `pin ${p.num} voltage order`);
      if (p.type === "digital" && p.dir === "out") {
        assert.ok(Number.isInteger(p.port) && p.port >= 0 && p.port < 13, `pin ${p.num} port`);
        assert.ok(Number.isInteger(p.bit) && p.bit >= 0 && p.bit < 16, `pin ${p.num} bit`);
      }
    }
  });
  it("every pin name the code special-cases exists in pins.json", () => {
    const names = new Set(loadPins().pins.map((p) => p.name));
    const core = srcText("emu_core.js");
    const needed = new Set();
    for (const m of core.matchAll(/n === "([A-Z0-9_+-]+)"/g)) needed.add(m[1]);
    for (const m of core.matchAll(/\.indexOf\("([A-Z]+)"\) === 0/g)) {
      const hit = [...names].some((n) => n.startsWith(m[1]));
      assert.ok(hit, "prefix " + m[1] + " matches a pin");
    }
    const dinSrc = JS["app.js"].match(/DIN_SRC = \{([\s\S]*?)\};/);
    assert.ok(dinSrc, "DIN_SRC found");
    for (const m of dinSrc[1].matchAll(/^\s*([A-Z0-9_]+)\s*:/gm)) needed.add(m[1]);
    for (const m of JS["app.js"].matchAll(/return n === "([A-Z0-9_]+)"/g)) needed.add(m[1]);
    const missing = [...needed].filter((n) => !names.has(n));
    assert.deepStrictEqual(missing, [], "pins missing: " + missing.join(", "));
  });
  it("scenario presets stay inside the UI slider ranges", () => {
    const sc = loadPins().scenarios;
    assert.ok(sc && sc.idle && sc.wot, "idle/wot scenarios present");
    for (const [k, v] of Object.entries(sc)) {
      assert.ok(v.rpm >= 0 && v.rpm <= 9000, `${k}.rpm`);
      assert.ok(v.ect >= -20 && v.ect <= 120, `${k}.ect`);
      assert.ok(v.tps >= 0 && v.tps <= 100, `${k}.tps`);
    }
  });
});

describe("tracked build output", () => {
  it("dist/ copies are byte-identical to src/ (commit them together)", () => {
    const files = ["app.js", "emu_core.js", "engine_sim.js", "can_live.js",
      "index.html", "style.css", "can_live.css", "pins.json", "icons.svg"];
    const stale = files.filter((f) => {
      const a = fs.readFileSync(path.join(__dirname, "..", "src", f));
      const b = fs.existsSync(path.join(DIST, f))
        ? fs.readFileSync(path.join(DIST, f))
        : null;
      return !b || !a.equals(b);
    });
    assert.deepStrictEqual(stale, [], "rebuild with: make -C web/ecu-emu build");
  });
});

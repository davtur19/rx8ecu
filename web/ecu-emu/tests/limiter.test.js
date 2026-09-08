"use strict";
/* Rev-limiter rework suite: ROM-staged fuel cut (soft per-rotor -> hard),
 * raised MAX_RPM ceilings, working fuel-cut checkbox, cold limits
 * (node stdlib only). */

const { describe, it, beforeEach } = require("node:test");
const assert = require("node:assert/strict");
const { loadCore, loadPins, loadEngineSim, srcText } = require("./helpers");

let M;
beforeEach(() => {
  M = loadCore();
  M.emu_init();
  M.emu_set_pins(loadPins().pins);
});

function bitCount(v) {
  let n = 0;
  for (let b = 0; b < 4; b++) if ((v >> b) & 1) n++;
  return n;
}

describe("fuel-cut checkbox ON: cut engages at the redline", () => {
  it("no cut below, soft stage at, hard stage above redline+500", () => {
    M.emu_set_sensor(0, 8999);
    assert.strictEqual(M.emu_get_fuel_cut(), 0);
    assert.strictEqual(M.emu_get_cut_stage(), 0);
    M.emu_set_sensor(0, 9000);
    assert.strictEqual(M.emu_get_fuel_cut(), 1, "cut active at redline");
    assert.strictEqual(M.emu_get_cut_stage(), 1, "soft per-rotor stage");
    assert.strictEqual(M.emu_get_inj_duty(), 0, "scalar duty reads CUT");
    M.emu_set_sensor(0, 9500);
    assert.strictEqual(M.emu_get_cut_stage(), 2, "hard full cut");
    assert.strictEqual(M.emu_get_port(1, 0), 0, "all injectors off");
    assert.strictEqual(M.emu_get_port(1, 3), 0);
  });
  it("soft stage alternates rotor pairs per revolution (half fuel)", () => {
    /* RUNNING so the core leaves the UI-driven rpm alone (key-ON would
     * decay it and key-OFF darkens the ports). */
    M.emu_set_key_pos("START");
    for (let i = 0; i < 200; i++) M.emu_step_ms(10);
    assert.strictEqual(M.emu_get_engine_state(), "RUNNING");
    M.emu_set_sensor(0, 9200);
    assert.strictEqual(M.emu_get_cut_stage(), 1);
    const seen = new Set();
    let maxBits = 0;
    for (let i = 0; i < 200; i++) {
      M.emu_step_ms(1); // ~30 revs at 9200 rpm
      const p = M.emu_get_port(1, 0) | (M.emu_get_port(1, 1) << 1) |
                (M.emu_get_port(1, 2) << 2) | (M.emu_get_port(1, 3) << 3);
      seen.add(p);
      maxBits = Math.max(maxBits, bitCount(p));
    }
    assert.ok(maxBits <= 2, `half fuel: at most one rotor fires, max ${maxBits}`);
    assert.ok(seen.has(3) || seen.has(1) || seen.has(2), "rotor-A pair fires: " + [...seen]);
    assert.ok(seen.has(12) || seen.has(4) || seen.has(8), "rotor-B pair fires: " + [...seen]);
  });
  it("custom redline moves both stages together", () => {
    M.emu_cal_set({ redline: 6000 });
    M.emu_set_sensor(0, 5999);
    assert.strictEqual(M.emu_get_cut_stage(), 0);
    M.emu_set_sensor(0, 6000);
    assert.strictEqual(M.emu_get_cut_stage(), 1);
    M.emu_set_sensor(0, 6500);
    assert.strictEqual(M.emu_get_cut_stage(), 2);
  });
});

describe("fuel-cut checkbox OFF: over-rev to the ceiling", () => {
  it("no cut at 11000 and injectors still flow", () => {
    M.emu_cal_set({ fuelCutEn: 0 });
    M.emu_set_sensor(0, 11000);
    assert.strictEqual(M.emu_get_fuel_cut(), 0);
    assert.strictEqual(M.emu_get_cut_stage(), 0);
    assert.ok(M.emu_get_inj_duty() > 0, "injects past the old ceiling");
  });
});

describe("cold limits (firmware-published documented estimates)", () => {
  it("3000 below 40 C, 4500 below 70 C, none above", () => {
    for (const [ect, want] of [[20, 3000], [39.9, 3000], [40, 4500], [50, 4500], [69.9, 4500], [70, 0], [95, 0]]) {
      M.emu_set_ect_auto();
      M.emu_set_coolant(ect);
      assert.strictEqual(M.emu_get_cold_limit(), want, `ECT ${ect}`);
    }
  });
});

describe("sim target physics (engine_sim.computeTarget)", () => {
  let E;
  beforeEach(() => {
    E = loadEngineSim({ rpm: 0, ect: 80, iat: 25, map: 35, tps: 0, o2f: 0.45, o2r: 0.45 }).EngineSim;
  });
  it("cut ON clamps the target to the redline; cut OFF reaches past 9000", () => {
    assert.strictEqual(E.computeTarget(100, 0, 9000, true, 80), 9000);
    assert.strictEqual(E.computeTarget(100, 0, 9000, false, 80), 12000);
    const past = E.computeTarget(91, 0, 9000, false, 80); // setFromRPM(11000)
    assert.ok(past > 9000, "over-rev target, got " + past);
  });
  it("cold clamps beat throttle: 3000/4500 limits", () => {
    assert.strictEqual(E.computeTarget(100, 0, 9000, false, 20), 3000);
    assert.strictEqual(E.computeTarget(100, 0, 9000, false, 50), 4500);
    assert.strictEqual(E.coldLimitFor(NaN), 0, "NaN ECT -> no limit");
  });
  it("load droop still applies below the clamps", () => {
    const free = E.computeTarget(50, 0, 9000, false, 80);
    const loaded = E.computeTarget(50, 100, 9000, false, 80);
    assert.ok(loaded < free, `droop ${free} -> ${loaded}`);
  });
});

describe("ceilings raised to MAX_RPM = 12000", () => {
  it("app clamp + RPM slider span the over-rev range", () => {
    const app = srcText("app.js");
    assert.ok(/const MAX_RPM = 12000/.test(app), "MAX_RPM declared");
    assert.ok(/clampSensor\(sensorState\.rpm, 0, MAX_RPM/.test(app), "clamp 0..MAX_RPM");
    assert.ok(/key:"rpm",\s+label:"RPM",\s+min:0, max:MAX_RPM/.test(app), "slider max MAX_RPM");
  });
  it("engine sim maps to MAX_RPM; tacho scale spans 0..12", () => {
    const sim = srcText("engine_sim.js");
    assert.ok(/var MAX_RPM = 12000/.test(sim), "MAX_RPM declared");
    assert.ok(/mapRange\(_throttle, 0, 100, IDLE_RPM, MAX_RPM\)/.test(sim) ||
              /mapRange\(throttle, 0, 100, IDLE_RPM, MAX_RPM\)/.test(sim),
      "target maps to MAX_RPM");
    assert.ok(/v <= MAX_RPM; v \+= 500/.test(sim), "tacho ticks to MAX_RPM");
    assert.ok(/v <= 12; v\+\+/.test(sim), "tacho numerals 0..12");
  });
  it("sound engine + CAN packers share the ceiling", () => {
    assert.ok(/var MAX_RPM = 12000/.test(srcText("audio.js")), "audio ceiling");
    assert.ok(/RPM_FULL = 12000/.test(srcText("can_live.js")), "CAN full scale");
  });
  it("P0300@8800 is labeled a provisional emulator-model zone (not a limiter)", () => {
    const sim = srcText("engine_sim.js");
    assert.ok(/PROVISIONAL emulator-model zone/.test(sim), "code comment relabeled");
    assert.ok(!/near redline \(reachable: slider\/sim max 9000\)/.test(sim), "old comment gone");
  });
});

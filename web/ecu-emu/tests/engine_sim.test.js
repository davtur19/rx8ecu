"use strict";
/* engine_sim.js suite: input clamping, RPM mapping, crank-viz speed law.
 * Loaded in a vm sandbox with stubbed window/document (no browser needed).
 * node stdlib only. */

const { describe, it, beforeEach } = require("node:test");
const assert = require("node:assert/strict");
const { loadEngineSim } = require("./helpers");

let E, window;
beforeEach(() => {
  const box = loadEngineSim({ rpm: 0, ect: 80, iat: 25, map: 35, tps: 0, o2f: 0.45, o2r: 0.45 });
  E = box.EngineSim;
  window = box.window;
});

describe("throttle/load clamping", () => {
  it("setThrottle clamps 0..100 and keeps the previous value on NaN", () => {
    assert.strictEqual(E.setThrottle(50), 50);
    assert.strictEqual(E.setThrottle(NaN), 50);
    assert.strictEqual(E.setThrottle(undefined), 50);
    assert.strictEqual(E.setThrottle(-5), 0);
    assert.strictEqual(E.setThrottle(250), 100);
    assert.strictEqual(E.getThrottle(), 100);
  });
  it("setLoad clamps 0..100 and keeps the previous value on NaN", () => {
    assert.strictEqual(E.setLoad(20), 20);
    assert.strictEqual(E.setLoad(NaN), 20);
    assert.strictEqual(E.setLoad(1e6), 100);
    assert.strictEqual(E.setLoad(-1), 0);
  });
});

describe("setFromRPM inverse map (slider stick)", () => {
  it("idle maps to 0 %, redline to 100 %, midpoint halves", () => {
    assert.strictEqual(E.setFromRPM(800), 0);
    assert.strictEqual(E.setFromRPM(9000), 100);
    const mid = E.setFromRPM(4900);
    assert.ok(Math.abs(mid - 50) < 0.01, "mid throttle, got " + mid);
    assert.strictEqual(E.getLoad(), 0, "load cleared for a neutral rev");
  });
  it("out-of-range rpm clamps; NaN keeps the previous throttle", () => {
    E.setThrottle(30);
    assert.strictEqual(E.setFromRPM(NaN), 30);
    assert.strictEqual(E.setFromRPM(20000), 100);
    assert.strictEqual(E.setFromRPM(0), 0);
  });
});

describe("crank-viz controls", () => {
  it("setCrankSlow accepts only 1/0.5/0.1", () => {
    assert.strictEqual(E.setCrankSlow(0.5), 0.5);
    assert.strictEqual(E.setCrankSlow(0.7), 0.5, "invalid keeps previous");
    assert.strictEqual(E.setCrankSlow("fast"), 0.5);
    assert.strictEqual(E.setCrankSlow(0.1), 0.1);
    assert.strictEqual(E.setCrankSlow(1), 1);
    assert.strictEqual(E.getCrankSlow(), 1);
  });
  it("pause flag round-trips; single-step hook exists", () => {
    assert.strictEqual(E.setCrankPaused(true), true);
    assert.strictEqual(E.getCrankPaused(), true);
    assert.strictEqual(E.setCrankPaused(false), false);
    assert.strictEqual(E.stepCrankOnce(), true);
  });
});

describe("crank speed law (strictly rpm-derived)", () => {
  it("wheel speed scales 10x from idle to 8000 rpm at the same slow-mo", () => {
    E.setCrankSlow(1);
    E.setCrankPaused(false);
    window.sensorState.rpm = 800;
    const idle = E.getCrankDPS();
    window.sensorState.rpm = 8000;
    const high = E.getCrankDPS();
    assert.ok(idle > 0, "spins at idle");
    assert.ok(Math.abs(high / idle - 10) < 1e-9, `10x ratio, got ${high}/${idle}`);
  });
  it("slow-mo scales the speed; paused or stopped means 0", () => {
    window.sensorState.rpm = 3000;
    E.setCrankSlow(1);
    E.setCrankPaused(false);
    const full = E.getCrankDPS();
    E.setCrankSlow(0.1);
    assert.ok(Math.abs(E.getCrankDPS() - full * 0.1) < 1e-9);
    E.setCrankPaused(true);
    assert.strictEqual(E.getCrankDPS(), 0);
    E.setCrankPaused(false);
    window.sensorState.rpm = 0;
    assert.strictEqual(E.getCrankDPS(), 0);
  });
  it("manual O2/IAT holds arm without throwing", () => {
    assert.strictEqual(E.o2ManualHold(), true);
    assert.strictEqual(E.iatManualHold(), true);
  });
});

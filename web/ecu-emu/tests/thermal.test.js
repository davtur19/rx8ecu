"use strict";
/* Thermal rework suite: MAPxRPM fuel-energy heat, staged fan cooling,
 * ROM fan defaults, override vs AUTO paths (node stdlib only). */

const { describe, it, beforeEach } = require("node:test");
const assert = require("node:assert/strict");
const { loadCore, loadPins } = require("./helpers");

let M;
beforeEach(() => {
  M = loadCore();
  M.emu_init();
  M.emu_set_pins(loadPins().pins);
});

function stepMs(n, ms) {
  for (let i = 0; i < n; i++) M.emu_step_ms(ms === undefined ? 10 : ms);
}

/* OFF -> hold START until the engine catches (core owns rpm till RUNNING). */
function crankToRunning() {
  M.emu_set_key_pos("START");
  stepMs(200);
  assert.strictEqual(M.emu_get_engine_state(), "RUNNING");
}

describe("ROM fan defaults", () => {
  it("boots low 97/94, high 101/98 (f32 block 0x07793C-0x077950)", () => {
    assert.deepStrictEqual(M.emu_cal_get(), {
      fanLowOn: 97, fanLowOff: 94, fanHighOn: 101, fanHighOff: 98,
      ambient: 20, redline: 9000, fuelCutEn: 1,
    });
  });
});

describe("thermal vectors (MAPxRPM fuel-energy model)", () => {
  it("cold start warms at idle (coolant 20, light fuel-energy heat)", () => {
    crankToRunning();
    M.emu_set_sensor(0, 800);
    M.emu_set_sensor(3, 30); // idle MAP
    const t0 = M.emu_get_coolant();
    stepMs(600, 100); // 60 sim-seconds
    const t1 = M.emu_get_coolant();
    assert.ok(t1 > t0 + 3, `cold start warms ${t0} -> ${t1}`);
  });
  it("sustained redline UNDER LOAD climbs (heat beats staged fans)", () => {
    crankToRunning();
    M.emu_set_coolant(90); // start hot, AUTO stays on
    M.emu_set_sensor(0, 9000);
    M.emu_set_sensor(3, 95); // WOT MAP
    M.emu_set_sensor(4, 100);
    const t0 = M.emu_get_coolant();
    stepMs(300, 100); // 30 sim-seconds at redline
    const t1 = M.emu_get_coolant();
    assert.ok(t1 > t0 + 10, `redline climbs ${t0} -> ${t1}`);
    assert.strictEqual(M.emu_get_fan(1), 1, "high fan fights it but loses");
  });
  it("idle stabilizes near the thermostat plateau (no runaway)", () => {
    crankToRunning();
    M.emu_set_coolant(85);
    M.emu_set_sensor(0, 800);
    M.emu_set_sensor(3, 25); // idle MAP
    M.emu_set_sensor(4, 0);
    stepMs(600, 100); // 60 sim-seconds
    const t = M.emu_get_coolant();
    assert.ok(t >= 75 && t <= 97, `idle stabilizes, got ${t}`);
  });
  it("fans pull down from 100+ at light load", () => {
    crankToRunning();
    M.emu_set_coolant(105); // both stages on, AUTO stays on
    M.emu_step_ms(10); // let the hysteresis latch
    assert.strictEqual(M.emu_get_fan(1), 1, "high fan on at 105");
    M.emu_set_sensor(0, 800);
    M.emu_set_sensor(3, 25);
    M.emu_set_sensor(4, 0);
    const t0 = M.emu_get_coolant();
    stepMs(300, 100); // 30 sim-seconds
    const t1 = M.emu_get_coolant();
    assert.ok(t1 < t0 - 5, `fans pull down ${t0} -> ${t1}`);
  });
});

describe("override vs AUTO paths", () => {
  it("ECT slider write latches the override; AUTO releases to the model", () => {
    M.emu_set_key_pos("ON");
    M.emu_set_sensor(1, 100);
    assert.strictEqual(M.emu_get_ect_auto(), 0, "slider forces override");
    M.emu_step_ms(10);
    assert.strictEqual(M.emu_get_coolant(), 100, "integrator tracks slider");
    M.emu_set_ect_auto();
    assert.strictEqual(M.emu_get_ect_auto(), 1, "released to AUTO");
  });
  it("scenario-style seed sets INITIAL coolant but keeps AUTO (model runs)", () => {
    M.emu_set_key_pos("ON");
    M.emu_set_coolant(50);
    assert.strictEqual(M.emu_get_ect_auto(), 1, "AUTO untouched by seed");
    assert.strictEqual(M.emu_get_coolant(), 50);
    assert.strictEqual(M.emu_get_sensor(1), 50);
  });
});

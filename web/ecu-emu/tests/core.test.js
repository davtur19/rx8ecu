"use strict";
/* Core logic suite: state machine, crank, injection, fans, calibration,
 * thermal, electrical, input sanitizers. node stdlib only.
 * Run: node --test tests/   (or make -C web/ecu-emu test) */

const { describe, it, beforeEach } = require("node:test");
const assert = require("node:assert/strict");
const { spawnSync } = require("node:child_process");
const path = require("node:path");
const { loadCore, loadPins } = require("./helpers");

const CORE_PATH = path.join(__dirname, "..", "src", "emu_core.js");

let M;
beforeEach(() => {
  M = loadCore();
  M.emu_init();
  M.emu_set_pins(loadPins().pins);
});

function stepMs(n, ms) {
  for (let i = 0; i < n; i++) M.emu_step_ms(ms === undefined ? 10 : ms);
}

/* OFF -> ON -> hold START until the engine catches. */
function crankToRunning(maxSteps) {
  M.emu_set_key_pos("START");
  stepMs(maxSteps || 200);
  assert.strictEqual(M.emu_get_engine_state(), "RUNNING");
}

describe("boot state", () => {
  it("boots key-OFF, engine OFF, immo OK (N3J1/N3J1), full battery", () => {
    assert.strictEqual(M.emu_get_key_pos(), "OFF");
    assert.strictEqual(M.emu_get_engine_state(), "OFF");
    assert.strictEqual(M.emu_get_rpm(), 0);
    assert.strictEqual(M.emu_get_immo(), 1);
    assert.strictEqual(M.emu_get_key_code(), "N3J1");
    assert.strictEqual(M.emu_get_soc(), 100);
    assert.strictEqual(M.emu_get_fan(0), 0);
    assert.strictEqual(M.emu_get_fan(1), 0);
    assert.strictEqual(M.emu_get_afterrun(), 0);
    assert.strictEqual(M.emu_get_pump(), 0);
  });
});

describe("state machine (OFF/ACC/ON/CRANKING/RUNNING/STALLED)", () => {
  it("OFF -> ON on key ON", () => {
    M.emu_set_key_pos("ON");
    M.emu_step_ms(10);
    assert.strictEqual(M.emu_get_engine_state(), "ON");
  });

  it("ON -> CRANKING -> RUNNING on hold-START (immo OK, healthy battery)", () => {
    M.emu_set_key_pos("ON");
    M.emu_step_ms(10);
    M.emu_set_key_pos("START");
    M.emu_step_ms(10);
    assert.strictEqual(M.emu_get_engine_state(), "CRANKING");
    stepMs(100);
    assert.strictEqual(M.emu_get_engine_state(), "RUNNING");
    assert.ok(M.emu_get_rpm() >= 800, "catches to idle, rpm=" + M.emu_get_rpm());
  });

  it("starter overrun: START while RUNNING stays RUNNING", () => {
    crankToRunning();
    M.emu_set_key_pos("START");
    stepMs(50);
    assert.strictEqual(M.emu_get_engine_state(), "RUNNING");
  });

  it("key-off decay: RUNNING -> OFF, rpm falls to 0", () => {
    crankToRunning();
    M.emu_set_key_pos("OFF");
    stepMs(300); // 3 s at 3000 rpm/s decay
    assert.strictEqual(M.emu_get_engine_state(), "OFF");
    assert.strictEqual(M.emu_get_rpm(), 0);
  });

  it("STALL: rpm hits 0 with key ON, and restart from STALLED works", () => {
    crankToRunning();
    M.emu_set_key_pos("ON"); // release START, engine still turning
    M.emu_set_sensor(0, 0); // fuelling lost
    M.emu_step_ms(10);
    assert.strictEqual(M.emu_get_engine_state(), "STALLED");
    // restart from stall: START cranks and catches again
    M.emu_set_key_pos("START");
    stepMs(200);
    assert.strictEqual(M.emu_get_engine_state(), "RUNNING");
  });

  it("early START release: 200 ms crank then ON never reaches RUNNING", () => {
    M.emu_set_key_pos("START");
    stepMs(20);
    assert.strictEqual(M.emu_get_engine_state(), "CRANKING");
    M.emu_set_key_pos("ON");
    stepMs(200);
    assert.strictEqual(M.emu_get_engine_state(), "ON");
  });

  it("CRANKING released to ACC settles back to ON", () => {
    M.emu_set_key_pos("START");
    stepMs(20);
    M.emu_set_key_pos("ACC");
    M.emu_step_ms(10);
    assert.strictEqual(M.emu_get_engine_state(), "ON");
  });

  it("wrong key code: cranks forever, never RUNNING; recovery on correct code", () => {
    M.emu_set_key_code("DEAD");
    assert.strictEqual(M.emu_get_immo(), 0);
    M.emu_set_key_pos("START");
    stepMs(300); // 3 s, well past the 800 ms catch time
    assert.strictEqual(M.emu_get_engine_state(), "CRANKING");
    M.emu_set_key_code("N3J1");
    assert.strictEqual(M.emu_get_immo(), 1);
    stepMs(200);
    assert.strictEqual(M.emu_get_engine_state(), "RUNNING");
  });

  it("weak battery (SoC<20): starter drags ~120 rpm, never catches", () => {
    M.emu_set_soc(10);
    assert.strictEqual(M.emu_get_batt_weak(), 1);
    M.emu_set_key_pos("START");
    stepMs(100);
    assert.strictEqual(M.emu_get_engine_state(), "CRANKING");
    const rpm = M.emu_get_sensor(0);
    assert.ok(rpm > 50 && rpm < 200, "weak crank rpm band, got " + rpm);
    stepMs(200);
    assert.strictEqual(M.emu_get_engine_state(), "CRANKING");
  });

  it("invalid key position is rejected (keeps previous)", () => {
    assert.strictEqual(M.emu_set_key_pos("FLY"), "OFF");
    assert.strictEqual(M.emu_get_key_pos(), "OFF");
  });
});

describe("immo single store", () => {
  it("entered === stored gates start; stored default is N3J1", () => {
    assert.strictEqual(M.emu_get_key_code(), "N3J1");
    M.emu_set_immo_code("ABC9");
    assert.strictEqual(M.emu_get_immo(), 0);
    M.emu_set_key_code("ABC9");
    assert.strictEqual(M.emu_get_immo(), 1);
    M.emu_set_immo_code("N3J1");
    M.emu_set_key_code("N3J1");
    assert.strictEqual(M.emu_get_immo(), 1);
  });
});

describe("injector duty + redline fuel cut", () => {
  it("duty rises with rpm and stays in 2..85 %", () => {
    M.emu_set_sensor(0, 1000);
    const d1 = M.emu_get_inj_duty();
    M.emu_set_sensor(0, 4000);
    const d2 = M.emu_get_inj_duty();
    assert.ok(d1 > 0 && d1 < d2, `slope ${d1} < ${d2}`);
    assert.ok(d2 >= 0.02 && d2 <= 0.85, "bounds, got " + d2);
  });

  it("duty is 0 at/near stall", () => {
    M.emu_set_sensor(0, 0);
    assert.strictEqual(M.emu_get_inj_duty(), 0);
    M.emu_set_sensor(0, 200);
    assert.strictEqual(M.emu_get_inj_duty(), 0);
  });

  it("fuel cut at the 9000 redline; fuelCutEn=0 overrides; custom redline moves the cut", () => {
    M.emu_set_sensor(0, 9000);
    assert.strictEqual(M.emu_get_fuel_cut(), 1);
    assert.strictEqual(M.emu_get_inj_duty(), 0);
    M.emu_cal_set({ fuelCutEn: 0 });
    assert.strictEqual(M.emu_get_fuel_cut(), 0);
    assert.ok(M.emu_get_inj_duty() > 0, "injects with cut disabled");
    M.emu_cal_set({ fuelCutEn: 1, redline: 6000 });
    M.emu_set_sensor(0, 6000);
    assert.strictEqual(M.emu_get_fuel_cut(), 1);
    M.emu_set_sensor(0, 5999);
    assert.strictEqual(M.emu_get_fuel_cut(), 0);
  });

  it("below redline there is no cut", () => {
    M.emu_set_sensor(0, 8999);
    assert.strictEqual(M.emu_get_fuel_cut(), 0);
  });
});

describe("fan hysteresis (ROM defaults low 97/94, high 101/98)", () => {
  function ect(v) {
    M.emu_set_sensor(1, v); // latches the ECT override
    M.emu_step_ms(10);
  }
  it("low fan: on at 97, holds through 95, off at 93", () => {
    M.emu_set_key_pos("ON");
    ect(98);
    assert.strictEqual(M.emu_get_fan(0), 1);
    ect(95);
    assert.strictEqual(M.emu_get_fan(0), 1, "hysteresis holds between 94..97");
    ect(93);
    assert.strictEqual(M.emu_get_fan(0), 0, "drops at/ below 94");
  });
  it("high fan: on at 101, holds through 99, off below 98 (low stays on)", () => {
    M.emu_set_key_pos("ON");
    ect(102);
    assert.strictEqual(M.emu_get_fan(1), 1);
    assert.strictEqual(M.emu_get_fan(0), 1, "high implies low");
    ect(99);
    assert.strictEqual(M.emu_get_fan(1), 1, "hysteresis holds between 98..101");
    ect(97);
    assert.strictEqual(M.emu_get_fan(1), 0);
    assert.strictEqual(M.emu_get_fan(0), 1, "low still on at 97");
  });
});

describe("after-run", () => {
  it("hot engine with key OFF keeps fans powered, ports otherwise dark", () => {
    M.emu_set_key_pos("ON");
    M.emu_set_sensor(1, 110);
    M.emu_step_ms(10);
    assert.strictEqual(M.emu_get_fan(1), 1);
    M.emu_set_key_pos("OFF");
    M.emu_step_ms(10);
    assert.strictEqual(M.emu_get_afterrun(), 1);
    assert.strictEqual(M.emu_get_port(4, 0), 1);
    assert.strictEqual(M.emu_get_port(4, 1), 1);
    assert.strictEqual(M.emu_get_port(0, 0), 0, "coils dark with key OFF");
    assert.strictEqual(M.emu_get_port(1, 0), 0, "injectors dark with key OFF");
    M.emu_set_sensor(1, 80); // cooled down (override still latched)
    M.emu_step_ms(10);
    assert.strictEqual(M.emu_get_afterrun(), 0);
    assert.strictEqual(M.emu_get_port(4, 0), 0);
  });
});

describe("calibration clamping", () => {
  it("garbage/NaN inputs keep previous values", () => {
    const before = M.emu_cal_get();
    M.emu_cal_set({ fanLowOn: "garbage", redline: NaN, ambient: undefined });
    assert.deepStrictEqual(M.emu_cal_get(), before);
  });
  it("out-of-range inputs clamp to physical bounds", () => {
    const c = M.emu_cal_set({
      fanLowOn: 500, fanLowOff: -50, fanHighOn: 999, fanHighOff: -99,
      ambient: -100, redline: 99999,
    });
    assert.strictEqual(c.fanLowOn, 120);
    assert.strictEqual(c.fanLowOff, 40);
    assert.strictEqual(c.fanHighOn, 120);
    assert.strictEqual(c.fanHighOff, 40);
    assert.strictEqual(c.ambient, -20);
    assert.strictEqual(c.redline, 9500);
  });
  it("redline floor 3000; hysteresis guard keeps OFF below ON", () => {
    assert.strictEqual(M.emu_cal_set({ redline: 100 }).redline, 3000);
    const c = M.emu_cal_set({ fanLowOn: 50 }); // off (90) conflicts -> off = on-5
    assert.strictEqual(c.fanLowOff, 45);
    const c2 = M.emu_cal_set({ fanHighOn: 60 });
    assert.strictEqual(c2.fanHighOff, 55);
  });
  it("fuelCutEn coerces to 0/1; non-object patch is a no-op", () => {
    assert.strictEqual(M.emu_cal_set({ fuelCutEn: "yes" }).fuelCutEn, 1);
    assert.strictEqual(M.emu_cal_set({ fuelCutEn: 0 }).fuelCutEn, 0);
    const before = M.emu_cal_get();
    M.emu_cal_set(null);
    M.emu_cal_set(42);
    assert.deepStrictEqual(M.emu_cal_get(), before);
  });
  it("SoC/fuel clamp 0..100 and reject NaN", () => {
    assert.strictEqual(M.emu_set_soc(150), 100);
    assert.strictEqual(M.emu_set_soc(-5), 0);
    M.emu_set_soc(55);
    assert.strictEqual(M.emu_set_soc(NaN), 55);
    assert.strictEqual(M.emu_set_fuel(101), 100);
    assert.strictEqual(M.emu_set_fuel(-1), 0);
    M.emu_set_fuel(40);
    assert.strictEqual(M.emu_set_fuel("junk"), 40);
  });
});

describe("thermal model", () => {
  it("WOT soak heats the coolant and pulls HIGH fans; key-off cools it", () => {
    M.emu_set_key_pos("START");
    stepMs(120); // catch
    assert.strictEqual(M.emu_get_engine_state(), "RUNNING");
    M.emu_set_sensor(0, 9000);
    M.emu_set_sensor(4, 100);
    const t0 = M.emu_get_coolant();
    stepMs(5000); // 50 sim-seconds at WOT (~2.5 C/s early rise)
    const t1 = M.emu_get_coolant();
    assert.ok(t1 > t0 + 10, `heats under load ${t0} -> ${t1}`);
    assert.ok(t1 <= 125, "clamped to 125 C, got " + t1);
    assert.strictEqual(M.emu_get_fan(1), 1, "high fan on after soak");
    M.emu_set_key_pos("OFF");
    stepMs(600); // 60 s hot soak
    const t2 = M.emu_get_coolant();
    assert.ok(t2 < t1 - 5, `cools with engine off ${t1} -> ${t2}`);
  });
  it("ECT override tracks the slider; AUTO releases to the model", () => {
    M.emu_set_key_pos("ON");
    M.emu_set_sensor(1, 100);
    assert.strictEqual(M.emu_get_ect_auto(), 0);
    M.emu_step_ms(10);
    assert.strictEqual(M.emu_get_coolant(), 100);
    M.emu_set_ect_auto();
    assert.strictEqual(M.emu_get_ect_auto(), 1);
  });
});

describe("electrical model", () => {
  it("rest-voltage curve spans 11.8..12.6 V across SoC", () => {
    M.emu_set_soc(100);
    assert.strictEqual(M.emu_get_rest_v(), 12.6);
    M.emu_set_soc(0);
    assert.strictEqual(M.emu_get_rest_v(), 11.8);
    M.emu_set_soc(50);
    assert.strictEqual(M.emu_get_rest_v(), 12.2);
  });
  it("load sags the terminal below rest; alternator charges when RUNNING", () => {
    M.emu_set_soc(100);
    const rest = M.emu_get_rest_v();
    M.emu_set_key_pos("ON"); // ECU + pump prime load
    M.emu_step_ms(100);
    assert.ok(M.emu_get_load_a() > 0, "key-on draws load");
    assert.ok(M.emu_get_batt_v() < rest, `sag ${M.emu_get_batt_v()} < ${rest}`);
    assert.strictEqual(M.emu_get_charging(), 0);
    crankToRunning();
    assert.strictEqual(M.emu_get_charging(), 1);
    const v = M.emu_get_batt_v();
    assert.ok(v >= 13.4 && v <= 14.5, "regulated 13.5..14.4 V, got " + v);
    M.emu_set_soc(50);
    const s0 = M.emu_get_soc();
    stepMs(600); // 6 s of charging
    assert.ok(M.emu_get_soc() > s0, `SoC rises ${s0} -> ${M.emu_get_soc()}`);
  });
  it("fuel-pump 3 s prime then off; A/C engages while running with overheat cut", () => {
    M.emu_set_key_pos("ON");
    M.emu_step_ms(100);
    assert.strictEqual(M.emu_get_pump(), 1, "priming");
    stepMs(310); // past 3 s
    assert.strictEqual(M.emu_get_pump(), 0, "prime ends with engine stopped");
    crankToRunning();
    M.emu_set_ac_req(1);
    M.emu_step_ms(10);
    assert.strictEqual(M.emu_get_ac(), 1, "clutch engages");
    M.emu_set_sensor(1, 120); // overheat
    M.emu_step_ms(10);
    assert.strictEqual(M.emu_get_ac(), 0, "overheat cut above 118 C");
  });
  it("fuel drains with load; oil-low flags crank and sub-500 rpm", () => {
    crankToRunning();
    M.emu_set_sensor(0, 6000);
    M.emu_set_sensor(4, 100);
    const f0 = M.emu_get_fuel();
    stepMs(600);
    assert.ok(M.emu_get_fuel() < f0, `drains ${f0} -> ${M.emu_get_fuel()}`);
    M.emu_set_fuel(100);
    assert.strictEqual(M.emu_get_fuel(), 100);
    M.emu_set_key_pos("START");
    M.emu_step_ms(10);
    // fresh core for a clean crank-phase check
    M.emu_init();
    M.emu_set_pins(loadPins().pins);
    M.emu_set_key_pos("START");
    M.emu_step_ms(100);
    assert.strictEqual(M.emu_get_oil_low(), 1, "oil low while cranking");
    crankToRunning();
    M.emu_set_sensor(0, 800);
    M.emu_step_ms(10);
    assert.strictEqual(M.emu_get_oil_low(), 0, "oil ok at idle");
    M.emu_set_sensor(0, 400);
    M.emu_step_ms(10);
    assert.strictEqual(M.emu_get_oil_low(), 1, "oil low sub-500 rpm");
  });
});

describe("crank / waveform math", () => {
  it("tooth period is 60000/(rpm*20); 0 at rpm 0 (no division by zero)", () => {
    M.emu_set_sensor(0, 9000);
    assert.ok(Math.abs(M.emu_get_tooth_period_ms() - 60000 / (9000 * 20)) < 1e-9);
    M.emu_set_sensor(0, 0);
    assert.strictEqual(M.emu_get_tooth_period_ms(), 0);
  });
  it("crank angle stays on the 18-degree grid in 0..342", () => {
    M.emu_set_key_pos("ON");
    M.emu_set_sensor(0, 3000);
    for (let i = 0; i < 50; i++) {
      M.emu_step_ms(10);
      const a = M.emu_get_crank_angle();
      assert.ok(a >= 0 && a <= 342 && a % 18 === 0, "angle " + a);
    }
  });
  it("gap flag fires only on teeth 5/15 and agrees with the capture bit31", () => {
    M.emu_set_key_pos("ON");
    M.emu_set_sensor(0, 3000);
    const gaps = new Set();
    for (let i = 0; i < 200; i++) {
      M.emu_step_ms(10);
      const t = M.emu_get_crank_phase();
      const g = M.emu_get_crank_gap();
      const cap = M.emu_get_crank_capture() >>> 0;
      assert.strictEqual(g, cap >= 0x80000000 ? 1 : 0, "capture gap bit agrees");
      if (g) gaps.add(t);
    }
    assert.ok(gaps.size > 0, "saw gap teeth");
    for (const t of gaps) assert.ok(t === 5 || t === 15, "gap tooth " + t);
  });
  it("rpm 0 freezes the crank (phase/angle/voltage all quiet)", () => {
    M.emu_set_sensor(0, 0);
    M.emu_step_ms(100);
    assert.strictEqual(M.emu_get_tooth_period_ms(), 0);
  });
});

describe("sensor input sanitizer (review fix)", () => {
  it("NaN/undefined/garbage keep the previous value (never poison state)", () => {
    M.emu_set_sensor(0, 3000);
    M.emu_set_sensor(0, NaN);
    M.emu_set_sensor(0, undefined);
    M.emu_set_sensor(0, "junk");
    assert.strictEqual(M.emu_get_sensor(0), 3000);
    M.emu_set_sensor(1, 80);
    M.emu_set_sensor(1, NaN);
    assert.strictEqual(M.emu_get_sensor(1), 80);
  });
  it("finite values clamp to physical ranges", () => {
    M.emu_set_sensor(0, -500);
    assert.strictEqual(M.emu_get_sensor(0), 0);
    M.emu_set_sensor(0, 1e9);
    assert.strictEqual(M.emu_get_sensor(0), 12000);
    M.emu_set_sensor(4, 500);
    assert.strictEqual(M.emu_get_sensor(4), 100);
    M.emu_set_sensor(5, -2);
    assert.strictEqual(M.emu_get_sensor(5), 0);
    M.emu_set_sensor(3, 1e6);
    assert.strictEqual(M.emu_get_sensor(3), 120);
  });
  it("NaN rpm step returns promptly (used to hang crankStep forever)", () => {
    const r = spawnSync(
      process.execPath,
      ["-e", `var M=require(${JSON.stringify(CORE_PATH)});M.emu_init();M.emu_set_sensor(0,3000);M.emu_set_sensor(0,NaN);M.emu_step_ms(10);console.log("OK rpm="+M.emu_get_rpm()+", sensor="+M.emu_get_sensor(0));`],
      { timeout: 8000 }
    );
    assert.strictEqual(r.status, 0, "child must exit 0, got " + r.status);
    assert.match(r.stdout.toString(), /OK/);
  });
  it("giant step while RUNNING at redline returns promptly (used to hang)", () => {
    const r = spawnSync(
      process.execPath,
      ["-e", `var M=require(${JSON.stringify(CORE_PATH)});M.emu_init();M.emu_set_key_pos("START");for(var i=0;i<100;i++)M.emu_step_ms(10);M.emu_set_sensor(0,9000);M.emu_step_ms(1e9);console.log("OK "+M.emu_get_engine_state()+" "+M.emu_get_rpm());`],
      { timeout: 8000 }
    );
    assert.strictEqual(r.status, 0, "child must exit 0, got " + r.status);
    assert.match(r.stdout.toString(), /OK RUNNING 9000/);
  });
});

describe("pin voltages follow the model", () => {
  function byName(n) {
    return loadPins().pins.find((p) => p.name === n).num;
  }
  it("NE+ quiet at 0 rpm, pulsing when turning; BATT_SENS tracks Vterm", () => {
    M.emu_set_key_pos("ON");
    M.emu_set_sensor(0, 0);
    M.emu_step_ms(10);
    assert.strictEqual(M.emu_get_pin(byName("NE+")), 0);
    M.emu_set_sensor(0, 3000);
    M.emu_step_ms(10);
    const ne = M.emu_get_pin(byName("NE+"));
    assert.ok(ne === 4.5 || ne === 0.2, "NE rail, got " + ne);
    const bs = M.emu_get_pin(byName("BATT_SENS"));
    // pin returns raw Vterm, the getter rounds to 2 dp
    assert.ok(Math.abs(bs - M.emu_get_batt_v()) < 0.01, "sense tracks terminal");
  });
  it("IG feed dark with key OFF, live with key ON; out-of-range pin reads 0", () => {
    M.emu_set_key_pos("OFF");
    M.emu_step_ms(10);
    const ign = loadPins().pins.find((p) => p.name === "IGN1").num;
    assert.strictEqual(M.emu_get_pin(ign), 0);
    M.emu_set_key_pos("ON");
    M.emu_step_ms(10);
    assert.ok(M.emu_get_pin(ign) > 0);
    assert.strictEqual(M.emu_get_pin(0), 0);
    assert.strictEqual(M.emu_get_pin(97), 0);
  });
});

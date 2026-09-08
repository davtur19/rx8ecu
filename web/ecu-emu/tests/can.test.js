"use strict";
/* CAN packer suite: DLC/length/range for every TX id, live-field tracking,
 * extreme-input saturation (review fix on 0x251). node stdlib only. */

const { describe, it, beforeEach } = require("node:test");
const assert = require("node:assert/strict");
const { loadCore, loadPins, loadCanLive } = require("./helpers");

const IDS = [0x201, 0x203, 0x420, 0x630, 0x620, 0x215, 0x251, 0x240, 0x250, 0x231, 0x650, 0x041];

let M, st, CAN, box;
beforeEach(() => {
  M = loadCore();
  M.emu_init();
  M.emu_set_pins(loadPins().pins);
  st = { rpm: 3000, ect: 85, iat: 30, map: 50, tps: 25, o2f: 0.45, o2r: 0.45, vss: 0 };
  box = loadCanLive(M, st);
  CAN = box.CAN;
});

/* vm-sandbox arrays live in another realm: normalize before comparing. */
function bytes(a) {
  return Array.from(a);
}

function assertFrame(f, id) {
  assert.ok(f, "pack(0x" + id.toString(16) + ") non-null");
  assert.strictEqual(f.id, id);
  assert.strictEqual(f.data.length, f.dlc, "data length matches DLC");
  for (const b of f.data) {
    assert.ok(Number.isInteger(b) && b >= 0 && b <= 255, `byte ${b} in range for 0x${id.toString(16)}`);
  }
}

describe("nominal packs", () => {
  it("every TX id packs with matching DLC and bytes in 0..255", () => {
    for (const id of IDS) assertFrame(CAN.pack(id), id);
  });
  it("declared DLCs match the firmware mailbox layout", () => {
    const want = { 0x201: 8, 0x203: 7, 0x420: 7, 0x630: 8, 0x620: 7, 0x215: 8,
      0x251: 8, 0x240: 8, 0x250: 8, 0x231: 5, 0x650: 1, 0x041: 8 };
    for (const id of IDS) {
      assert.strictEqual(CAN.pack(id).dlc, want[id], "DLC 0x" + id.toString(16));
    }
  });
  it("unknown ids and missing sensorState pack to null", () => {
    assert.strictEqual(CAN.pack(0x999), null);
    assert.strictEqual(CAN.pack(0x212), null, "RX-only id has no TX packer");
    box.window.sensorState = undefined;
    assert.strictEqual(CAN.pack(0x251), null, "no state, no frame (never throws)");
  });
});

describe("extreme inputs stay on the wire (review fix)", () => {
  const nasties = [
    { rpm: NaN, ect: NaN, iat: NaN, map: NaN, tps: NaN, o2f: NaN, o2r: NaN, vss: NaN },
    { rpm: -500, ect: -1000, iat: -1000, map: -500, tps: -50, o2f: -1, o2r: -1, vss: -10 },
    { rpm: 1e9, ect: 1e6, iat: 1e6, map: 1e6, tps: 500, o2f: 5, o2r: 5, vss: 1e6 },
    { rpm: undefined, ect: undefined, tps: undefined },
    {},
  ];
  it("all ids x all nasty states: length 8/DLC match, bytes 0..255", () => {
    for (const n of nasties) {
      const c = loadCanLive(M, Object.assign({}, st, n)).CAN;
      for (const id of IDS) assertFrame(c.pack(id), id);
    }
  });
  it("0x251 saturates (not wraps) at the rails", () => {
    const c = loadCanLive(M, Object.assign({}, st, { ect: 1000, map: 1000 })).CAN;
    const f = c.pack(0x251);
    assert.deepStrictEqual(bytes(f.data.slice(2, 4)), [255, 255]);
    const c2 = loadCanLive(M, Object.assign({}, st, { ect: -1000, map: -1000 })).CAN;
    assert.deepStrictEqual(bytes(c2.pack(0x251).data.slice(2, 4)), [0, 0]);
  });
});

describe("live fields track the core/sensors", () => {
  it("rpm encodes x4 BE in 0x201 and 0x251", () => {
    st.rpm = 3000;
    const a = CAN.pack(0x201).data;
    assert.deepStrictEqual(bytes(a.slice(0, 2)), [(12000 >> 8) & 0xff, 12000 & 0xff]);
    const b = CAN.pack(0x251).data;
    assert.deepStrictEqual(bytes(b.slice(0, 2)), [(12000 >> 8) & 0xff, 12000 & 0xff]);
  });
  it("throttle encodes in 0x215 (x100 BE + raw mirror)", () => {
    st.tps = 50;
    const d = CAN.pack(0x215).data;
    assert.deepStrictEqual(bytes(d.slice(0, 2)), [(5000 >> 8) & 0xff, 5000 & 0xff]);
    assert.strictEqual(d[2], 128);
    assert.strictEqual(d[3], 128);
  });
  it("0x420 carries ECT+40 and the oil/battery/MIL lamps", () => {
    st.ect = 80;
    st.mil = true;
    assert.strictEqual(CAN.pack(0x420).data[0], 120);
    assert.ok(CAN.pack(0x420).data[1] & 0x01, "MIL lamp");
    // oil lamp follows the live core flag: crank the engine
    M.emu_set_key_pos("START");
    M.emu_step_ms(100);
    assert.ok(CAN.pack(0x420).data[1] & 0x02, "oil lamp while cranking");
    // battery lamp follows the weak-battery flag
    M.emu_init();
    M.emu_set_pins(loadPins().pins);
    M.emu_set_soc(5);
    const c2 = loadCanLive(M, st).CAN;
    assert.ok(c2.pack(0x420).data[1] & 0x08, "battery lamp when weak");
  });
  it("0x630/0x620 fan bytes follow the live hysteresis states", () => {
    M.emu_set_key_pos("ON");
    M.emu_set_sensor(1, 110); // ECT override: both fans on
    M.emu_step_ms(10);
    assert.strictEqual(CAN.pack(0x630).data[0] & 0x03, 0x03);
    assert.strictEqual(CAN.pack(0x630).data[6], 1, "fan2 mirror byte");
    assert.strictEqual(CAN.pack(0x630).data[7], 1, "fan1 mirror byte");
    assert.strictEqual(CAN.pack(0x620).data[0] & 0x03, 0x03);
    const bv = Math.round(M.emu_get_batt_v() * 10) & 0xff;
    assert.strictEqual(CAN.pack(0x630).data[1], bv, "battery x10 byte");
    assert.strictEqual(CAN.pack(0x620).data[3], Math.round(M.emu_get_soc()) & 0xff, "SoC byte");
  });
  it("injection pulse in 0x250 spans 1..8 ms across the rev range", () => {
    st.rpm = 0;
    let lo = CAN.pack(0x250).data;
    assert.strictEqual((lo[6] << 8) | lo[7], 1);
    st.rpm = 9000;
    let hi = CAN.pack(0x250).data;
    assert.strictEqual((hi[6] << 8) | hi[7], 8);
  });
});

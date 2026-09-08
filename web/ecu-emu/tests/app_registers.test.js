"use strict";
/* app.js register-view suite (runs app.js in a vm sandbox with a stub
 * document): the ATU CAPT hex column must show the LIVE capture value,
 * including the gap-tooth bit31 (review fix: it was hardcoded 0x00000000).
 * node stdlib only. */

const { describe, it, beforeEach } = require("node:test");
const assert = require("node:assert/strict");
const { loadCore, loadPins, loadApp } = require("./helpers");

let M, sb, tables;
beforeEach(() => {
  M = loadCore();
  M.emu_init();
  M.emu_set_pins(loadPins().pins);
  tables = [];
  const document = {
    getElementById: (id) => {
      if (id === "reg-table") return { set innerHTML(v) { tables.push(v); } };
      return null;
    },
    querySelector: () => null,
    querySelectorAll: () => [],
    createElement: () => { throw new Error("no DOM creation on this path"); },
    addEventListener() {},
    activeElement: null,
  };
  sb = loadApp(M, document);
  assert.strictEqual(typeof sb.renderRegisters, "function", "renderRegisters exposed");
});

function lastTable() {
  assert.ok(tables.length > 0, "renderRegisters wrote the table");
  return tables[tables.length - 1];
}

describe("register view", () => {
  it("ATU CAPT hex shows the live capture (not a hardcoded zero)", () => {
    M.emu_set_key_pos("ON");
    M.emu_set_sensor(0, 3000);
    for (let i = 0; i < 50; i++) M.emu_step_ms(10);
    sb.renderRegisters();
    const html = lastTable();
    const expected = "0x" + (M.emu_get_reg(0xfffff434) >>> 0).toString(16).toUpperCase().padStart(8, "0");
    assert.notStrictEqual(expected, "0x00000000", "test needs a nonzero capture");
    assert.ok(html.includes(expected), `table shows live capture ${expected}`);
  });
  it("ATU CAPT shows the gap flag after stepping onto a gap tooth", () => {
    M.emu_set_key_pos("ON");
    M.emu_set_sensor(0, 3000);
    let saw = false;
    for (let i = 0; i < 500 && !saw; i++) {
      M.emu_step_ms(10);
      saw = M.emu_get_crank_gap() === 1;
    }
    assert.ok(saw, "reached a gap tooth");
    sb.renderRegisters();
    const cap = (M.emu_get_reg(0xfffff434) >>> 0).toString(16).toUpperCase().padStart(8, "0");
    assert.ok(cap[0] >= "8", "bit31 set, capture=0x" + cap);
    assert.ok(lastTable().includes("0x" + cap), "gap capture visible in table");
  });
  it("ADC + PORT + CAN rows render with hex", () => {
    M.emu_set_key_pos("ON");
    M.emu_step_ms(10);
    sb.renderRegisters();
    const html = lastTable();
    assert.ok(html.includes("ADC"), "ADC rows");
    assert.ok(html.includes("PORT"), "PORT rows");
    assert.ok(html.includes("CH0"), "ADC channel rows");
    assert.ok(html.includes("0xFFFFF720"), "port base address");
  });
});

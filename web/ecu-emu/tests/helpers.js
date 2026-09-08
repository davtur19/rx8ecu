"use strict";
/* Shared harness: load browser-style sources (plain script files that attach
 * `var X = ...` globals) into a node:vm sandbox with stubbed window/document.
 * node stdlib only. */

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const SRC = path.join(__dirname, "..", "src");

function srcPath(name) {
  return path.join(SRC, name);
}

function srcText(name) {
  return fs.readFileSync(srcPath(name), "utf8");
}

/* Fresh core instance (CommonJS module). Note: require caches per process;
 * node --test isolates files in separate processes, and tests call emu_init()
 * for per-test isolation. */
function loadCore() {
  return require(srcPath("emu_core.js"));
}

function loadPins() {
  return JSON.parse(srcText("pins.json"));
}

function nullEl() {
  return null;
}

/* Minimal document stub: every lookup misses (all call sites null-guard),
 * unless overrides are supplied. */
function makeDocument(overrides) {
  return Object.assign(
    {
      getElementById: nullEl,
      querySelector: nullEl,
      querySelectorAll: () => [],
      createElement: () => ({
        children: [],
        dataset: {},
        classList: { add() {}, remove() {}, toggle() {} },
        appendChild(c) { this.children.push(c); return c; },
        append() {},
        setAttribute() {},
        addEventListener() {},
        style: {},
      }),
      createDocumentFragment: () => ({ appendChild() {} }),
      addEventListener() {},
      activeElement: null,
    },
    overrides || {}
  );
}

function makeWindow(sensorState, extra) {
  return Object.assign({ sensorState: sensorState || {} }, extra || {});
}

/* Run can_live.js in a sandbox; returns { CAN, window } so tests can also
 * simulate an absent sensorState (pack() must return null, not throw). */
function loadCanLive(core, sensorState) {
  const window = makeWindow(sensorState);
  const sb = { window, Module: core, console };
  sb.window.window = sb.window;
  vm.createContext(sb);
  vm.runInContext(srcText("can_live.js"), sb, { filename: "can_live.js" });
  return { CAN: sb.CANLive, window };
}

/* Run engine_sim.js in a sandbox; returns the EngineSim namespace. */
function loadEngineSim(sensorState) {
  const window = makeWindow(sensorState);
  const sb = { window, Module: undefined, document: makeDocument(), console };
  sb.window.window = sb.window;
  vm.createContext(sb);
  vm.runInContext(srcText("engine_sim.js"), sb, { filename: "engine_sim.js" });
  return { EngineSim: sb.EngineSim, window, sb };
}

/* Run app.js in a sandbox; returns the sandbox (renderRegisters and other
 * top-level `function` declarations attach to it). */
function loadApp(core, document) {
  const window = makeWindow({});
  const sb = { window, Module: core, document: document || makeDocument(), console };
  sb.window.window = sb.window;
  vm.createContext(sb);
  vm.runInContext(srcText("app.js"), sb, { filename: "app.js" });
  return sb;
}

module.exports = {
  SRC,
  srcPath,
  srcText,
  loadCore,
  loadPins,
  makeDocument,
  makeWindow,
  loadCanLive,
  loadEngineSim,
  loadApp,
};

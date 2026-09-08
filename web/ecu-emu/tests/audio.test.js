"use strict";
/* audio.js suite: rotary-sound param mapping (node stdlib only).
 * The AudioContext engine itself is NOT tested here (no browser in node) —
 * only the pure mapping (freq/gain/cutoff vectors incl. edges + NaN-safe
 * defaults), the mute/volume toggle logic, and the hasAudio/unlock guard. */

const { describe, it, beforeEach } = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const { srcText } = require("./helpers");

const AUDIO_PATH = path.join(__dirname, "..", "src", "audio.js");

let A;
beforeEach(() => {
  delete require.cache[require.resolve(AUDIO_PATH)];
  A = require(AUDIO_PATH);
  A.setMuted(true);
  A.setVolume(70);
});

describe("fundamental: 6 events/rev (900 Hz @ 9000)", () => {
  it("rpm vectors map to rpm/60*6", () => {
    assert.strictEqual(A.fundHz(0), 0);
    assert.strictEqual(A.fundHz(800), 80);
    assert.strictEqual(A.fundHz(3000), 300);
    assert.strictEqual(A.fundHz(9000), 900);
    assert.strictEqual(A.fundHz(12000), 1200);
  });
  it("edges clamp: negative->0, over-ceiling->12000, NaN/Inf->safe 0", () => {
    assert.strictEqual(A.fundHz(-500), 0);
    assert.strictEqual(A.fundHz(20000), 1200, "clamped to the ceiling");
    assert.strictEqual(A.fundHz(NaN), 0, "NaN -> silent-safe default");
    assert.strictEqual(A.fundHz(Infinity), 0);
    assert.strictEqual(A.fundHz(undefined), 0);
  });
});

describe("paramsFor: harmonics, gain, cutoff, crank, fans", () => {
  it("harmonics are exact 2x/3x multiples", () => {
    const p = A.paramsFor(6000, 50, {});
    assert.strictEqual(p.fund, 600);
    assert.strictEqual(p.harm2, 1200);
    assert.strictEqual(p.harm3, 1800);
  });
  it("gain rises with load at fixed rpm; silent at 0 rpm", () => {
    const lo = A.paramsFor(3000, 10, {});
    const hi = A.paramsFor(3000, 100, {});
    assert.ok(hi.gain > lo.gain, `gain ${lo.gain} -> ${hi.gain}`);
    assert.strictEqual(A.paramsFor(0, 100, {}).gain, 0, "stopped: silent");
  });
  it("cutoff rises with rpm at fixed load", () => {
    const lo = A.paramsFor(800, 50, {});
    const hi = A.paramsFor(11000, 50, {});
    assert.ok(hi.cutoff > lo.cutoff, `cutoff ${lo.cutoff} -> ${hi.cutoff}`);
  });
  it("NaN/edge inputs map to safe defaults (no NaN field)", () => {
    for (const p of [A.paramsFor(NaN, NaN), A.paramsFor(0, 0),
                     A.paramsFor(12000, 100), A.paramsFor(-5, 500)]) {
      for (const k of ["rpm", "fund", "harm2", "harm3", "gain", "cutoff", "chugHz", "fanGain"]) {
        assert.ok(Number.isFinite(p[k]), `${k} finite, got ${p[k]}`);
      }
    }
    const nan = A.paramsFor(NaN, NaN);
    assert.strictEqual(nan.fund, 0);
    assert.strictEqual(nan.gain, 0);
  });
  it("cranking flag yields a starter chug rate; fans add soft noise", () => {
    const c = A.paramsFor(250, 0, { cranking: true });
    assert.strictEqual(c.cranking, true);
    assert.ok(c.chugHz > 0, "chug " + c.chugHz);
    const idle = A.paramsFor(800, 0, {});
    assert.strictEqual(idle.chugHz, 0);
    assert.strictEqual(A.paramsFor(3000, 30, {}).fanGain, 0);
    assert.ok(A.paramsFor(3000, 30, { fanLow: true }).fanGain > 0);
    const hi = A.paramsFor(3000, 30, { fanLow: true, fanHigh: true });
    assert.ok(hi.fanGain > A.paramsFor(3000, 30, { fanLow: true }).fanGain);
  });
});

describe("mute/volume toggle logic", () => {
  it("mute round-trips; volume clamps 0..100 and keeps on NaN", () => {
    assert.strictEqual(A.isMuted(), true);
    assert.strictEqual(A.toggleMute(), false);
    assert.strictEqual(A.isMuted(), false);
    assert.strictEqual(A.setMuted(true), true);
    assert.strictEqual(A.setVolume(50), 50);
    assert.strictEqual(A.setVolume(250), 100);
    assert.strictEqual(A.setVolume(-5), 0);
    assert.strictEqual(A.setVolume(NaN), 0, "NaN keeps the previous value");
  });
});

describe("no-browser guard (no AudioContext in node)", () => {
  it("hasAudio() is false and unlock()/render() no-op without throwing", () => {
    assert.strictEqual(A.hasAudio(), false);
    assert.strictEqual(A.unlock(), false);
    assert.strictEqual(A.render(A.paramsFor(3000, 50, {})), false);
  });
  it("audio.js never touches the DOM at load (mapping only)", () => {
    const src = srcText("audio.js");
    assert.ok(!/document\./.test(src), "no document access in audio.js");
    assert.ok(/typeof AudioContext/.test(src), "AudioContext use is guarded");
  });
});

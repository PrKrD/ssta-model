import { test } from "node:test";
import assert from "node:assert/strict";
import { loadModule } from "./load-module.mjs";

const { PlaybackController, BASE_FRAMES_PER_SECOND } = await loadModule("../src/PlaybackController.ts");

// A manually driven animation clock: no wall-clock sleeps or browser required.
function setup(frameCount = 120) {
  let next = 0;
  const pending = new Map();
  const events = [];
  const clock = {
    request(callback) { const id = next++; pending.set(id, callback); return id; },
    cancel(id) { pending.delete(id); },
    tick(now) {
      const callbacks = [...pending.values()];
      pending.clear();
      callbacks.forEach((callback) => callback(now));
    },
  };
  const player = new PlaybackController(frameCount, (state) => events.push(state), clock);
  return { player, clock, pending, events };
}

test("elapsed timing retains fractional progress across irregular browser refreshes", () => {
  const { player, clock, pending } = setup();
  assert.equal(BASE_FRAMES_PER_SECOND, 6);
  player.play();
  clock.tick(0);
  clock.tick(100);
  assert.equal(player.getState().index, 0);
  clock.tick(250);
  assert.equal(player.getState().index, 1);
  clock.tick(500);
  assert.equal(player.getState().index, 3);
  clock.tick(1000);
  assert.equal(player.getState().index, 6);
  assert.equal(pending.size, 1);
});

test("play and pause are idempotent and never accumulate animation loops", () => {
  const { player, clock, pending } = setup();
  player.play(); player.play(); player.play();
  assert.equal(pending.size, 1);
  clock.tick(0); clock.tick(500);
  assert.equal(player.getState().index, 3);
  player.pause(); player.pause();
  assert.equal(pending.size, 0);
  clock.tick(5000);
  assert.equal(player.getState().index, 3);
  player.play();
  clock.tick(10000); clock.tick(10100);
  assert.equal(player.getState().index, 3, "paused time and partial old progress are excluded");
  clock.tick(10500);
  assert.equal(player.getState().index, 6);
  assert.equal(pending.size, 1);
});

test("playback wraps while manual steps and seeks clamp and pause", () => {
  const { player, clock, pending } = setup(4);
  player.step(-1);
  assert.equal(player.getState().index, 0);
  player.seek(3);
  player.step(1);
  assert.equal(player.getState().index, 3);
  player.play(); clock.tick(0); clock.tick(200);
  assert.equal(player.getState().index, 0);
  player.step(1);
  assert.deepEqual(player.getState(), { index: 1, playing: false, speed: 1 });
  assert.equal(pending.size, 0);
  player.step(-1);
  assert.equal(player.getState().index, 0);
  player.seek(100); assert.equal(player.getState().index, 3);
  player.seek(-5); assert.equal(player.getState().index, 0);
});

test("speed scales elapsed time without changing the frame count or paused index", () => {
  for (const speed of [0.5, 1, 2]) {
    const { player, clock, pending } = setup();
    player.setSpeed(speed);
    assert.equal(pending.size, 0);
    assert.equal(player.getState().index, 0);
    player.play(); clock.tick(0); clock.tick(1000);
    assert.equal(player.getState().index, 6 * speed);
    player.setSpeed(2);
    assert.equal(pending.size, 1);
    assert.equal(player.getState().index, 6 * speed, "speed changes do not advance data");
    clock.tick(2000); clock.tick(2500);
    assert.equal(player.getState().index, 6 * speed + 6);
  }
});

test("hidden tabs suspend scheduling and resume without catching up", () => {
  const { player, clock, pending } = setup();
  player.play(); clock.tick(0); clock.tick(500);
  player.setHidden(true);
  assert.equal(pending.size, 0);
  clock.tick(100000);
  assert.equal(player.getState().index, 3);
  player.setHidden(false);
  assert.equal(pending.size, 1);
  clock.tick(200000);
  assert.equal(player.getState().index, 3);
  clock.tick(200500);
  assert.equal(player.getState().index, 6);
  player.setHidden(true); player.pause(); player.setHidden(false);
  assert.equal(pending.size, 0, "paused players stay paused on visibility changes");
});

test("long stalls are discarded, not replayed as rapid advancement", () => {
  const { player, clock } = setup();
  player.play(); clock.tick(0); clock.tick(100);
  clock.tick(50000);
  assert.equal(player.getState().index, 0);
  clock.tick(50500);
  assert.equal(player.getState().index, 3);
});

test("destroy cancels pending work; invalid counts, speeds and indices are rejected", () => {
  const { player, clock, pending, events } = setup();
  player.play();
  assert.equal(pending.size, 1);
  player.destroy();
  const eventCount = events.length;
  assert.equal(pending.size, 0);
  player.play(); player.step(1); player.setSpeed(2); player.setHidden(false);
  clock.tick(1000);
  assert.equal(events.length, eventCount);
  assert.equal(pending.size, 0);
  const other = setup().player;
  for (const speed of [0, -1, 3, NaN]) assert.throws(() => other.setSpeed(speed));
  for (const index of [0.5, NaN, Infinity]) assert.throws(() => other.seek(index));
  for (const count of [0, -1, 0.5, NaN]) assert.throws(() => setup(count));
  const single = setup(1);
  single.player.play(); single.clock.tick(0); single.clock.tick(1000);
  assert.equal(single.player.getState().index, 0);
});

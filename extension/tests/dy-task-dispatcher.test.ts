/**
 * Tests for the Douyin background task dispatcher's pure helpers.
 *
 * Task 5 of the Douyin bootstrap import plan
 * (docs/plans/2026-05-06-douyin-bootstrap-import.md).
 *
 * Module isolation: zero imports from extension/src/background/xhs-task-dispatcher.
 * The orchestration (chrome.tabs / chrome.runtime / fetch lifecycle) lives in
 * the dispatcher module but isn't unit-tested here — Task 4's chrome-devtools
 * MCP probe already validated the highest-risk seam (fetch-tap in real Chrome).
 */

import test from "node:test";
import assert from "node:assert/strict";

import {
  buildDyTaskUrl,
  buildDyExecuteMessageData,
  computeDyTaskTimeoutMs,
  isValidDyTask,
} from "../src/background/dy-task-dispatcher.ts";

test("buildDyTaskUrl routes bootstrap_profile to the douyin home", () => {
  // The content-script executor will navigate from this initial URL to
  // the per-scope tabs (handled by buildScopeUrl in dy/task-executor.ts).
  // The dispatcher just needs to land us on a douyin.com tab where the
  // SDK + RENDER_DATA are available.
  assert.equal(
    buildDyTaskUrl({ id: "t", type: "bootstrap_profile" }),
    "https://www.douyin.com/",
  );
});

test("buildDyTaskUrl returns null for unknown task types", () => {
  assert.equal(buildDyTaskUrl({ id: "t", type: "unknown" as never }), null);
});

test("isValidDyTask accepts bootstrap_profile with optional payload fields", () => {
  assert.equal(
    isValidDyTask({
      id: "abc",
      type: "bootstrap_profile",
      scopes: ["dy_post", "dy_collect", "dy_like", "dy_follow"],
      max_items_per_scope: 300,
      max_scroll_rounds: 15,
      max_stagnant_scroll_rounds: 5,
    }),
    true,
  );
  // Minimal valid task — id + type only.
  assert.equal(isValidDyTask({ id: "abc", type: "bootstrap_profile" }), true);
});

test("isValidDyTask rejects malformed input", () => {
  assert.equal(isValidDyTask(null), false);
  assert.equal(isValidDyTask("string"), false);
  assert.equal(isValidDyTask({}), false);
  assert.equal(isValidDyTask({ id: "" }), false);
  assert.equal(isValidDyTask({ id: "x", type: "search" }), false); // wrong type
  assert.equal(isValidDyTask({ id: "x", type: "bootstrap_profile", scopes: "not-array" }), false);
  // Unknown scope name slips into the array — must be rejected so we
  // never end up firing buildScopeUrl on an unsupported scope.
  assert.equal(
    isValidDyTask({ id: "x", type: "bootstrap_profile", scopes: ["dy_post", "dy_unknown"] }),
    false,
  );
});

test("computeDyTaskTimeoutMs scales with max_scroll_rounds × number of scopes", () => {
  // Default (no rounds): the floor — 30s — to give the executor time to
  // read RENDER_DATA + extract sec_uid even if there's nothing to scroll.
  assert.equal(
    computeDyTaskTimeoutMs({ id: "t", type: "bootstrap_profile" }),
    30_000,
  );
  // 15 rounds × 4 scopes × 3s/round + 30s base = 30s + 180s = 210s,
  // but capped at the BOOTSTRAP_MAX_TASK_TIMEOUT_MS = 360s.
  const big = computeDyTaskTimeoutMs({
    id: "t",
    type: "bootstrap_profile",
    max_scroll_rounds: 15,
    scopes: ["dy_post", "dy_collect", "dy_like", "dy_follow"],
  });
  assert.ok(big >= 30_000, `expected >= 30s, got ${big}`);
  assert.ok(big <= 360_000, `expected <= 360s ceiling, got ${big}`);
  assert.ok(big > 60_000, `15 rounds × 4 scopes should clear 60s, got ${big}`);
});

test("computeDyTaskTimeoutMs falls back to 4-scope assumption when scopes omitted", () => {
  // The dispatcher may receive a task that doesn't enumerate scopes
  // (CLI default). We compute timeout assuming all four scopes will run.
  const timeout = computeDyTaskTimeoutMs({
    id: "t",
    type: "bootstrap_profile",
    max_scroll_rounds: 5,
  });
  assert.ok(timeout > 30_000, `expected > 30s with 5 rounds, got ${timeout}`);
});

test("buildDyExecuteMessageData includes only the fields the executor needs", () => {
  const data = buildDyExecuteMessageData({
    id: "task-99",
    type: "bootstrap_profile",
    scopes: ["dy_post", "dy_collect"],
    max_items_per_scope: 300,
    max_scroll_rounds: 15,
    max_stagnant_scroll_rounds: 5,
  });
  assert.equal(data.task_id, "task-99");
  assert.equal(data.type, "bootstrap_profile");
  assert.deepEqual(data.scopes, ["dy_post", "dy_collect"]);
  assert.equal(data.max_items_per_scope, 300);
  assert.equal(data.max_scroll_rounds, 15);
  assert.equal(data.max_stagnant_scroll_rounds, 5);
});

test("buildDyExecuteMessageData omits undefined fields (no leaking nullish payload)", () => {
  const data = buildDyExecuteMessageData({ id: "t", type: "bootstrap_profile" });
  assert.equal(data.task_id, "t");
  assert.equal(data.type, "bootstrap_profile");
  assert.equal("scopes" in data, false);
  assert.equal("max_items_per_scope" in data, false);
  assert.equal("max_scroll_rounds" in data, false);
});

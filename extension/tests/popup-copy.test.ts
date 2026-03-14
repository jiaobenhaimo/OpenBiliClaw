import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

test("popup copy uses a more native bilibili-style voice in key entry points", () => {
  const popupHtml = readFileSync(resolve("popup", "popup.html"), "utf8");
  const popupJs = readFileSync(resolve("popup", "popup.js"), "utf8");
  const popupHelpers = readFileSync(resolve("popup", "popup-helpers.js"), "utf8");

  assert.match(popupHtml, /首页先放一边，这里是你最近更可能点开的。/);
  assert.match(popupHtml, /这几条，你大概会点开/);
  assert.match(popupHtml, /换一批/);
  assert.match(popupHtml, /正在给你换一批/);
  assert.match(popupHtml, /当前池子里还有/);
  assert.match(popupHtml, /刚补进/);
  assert.match(popupHtml, /最近在补/);
  assert.match(popupHtml, /阿B 最近新记住了什么/);
  assert.match(popupHtml, /最近你到底在看啥/);
  assert.match(popupHtml, /写点你最近爱看的/);
  assert.match(popupJs, /这对画像的影响/);
  assert.match(popupJs, /为什么这么判断/);
  assert.match(popupJs, /这次依据/);
  assert.match(popupHelpers, /正在往下翻阿B 最近记下的变化。/);
  assert.match(popupHelpers, /这段历史还没拉下来，可以再试一次。/);
  assert.match(popupHelpers, /已经看到最近这段时间的变化了。/);
  assert.doesNotMatch(popupHtml, /对个暗号|来，唠一句/);
});

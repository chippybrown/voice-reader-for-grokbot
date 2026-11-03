const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const { JSDOM } = require("jsdom");

const root = path.join(__dirname, "..");

function loadWindow() {
  const dom = new JSDOM(
    "<!DOCTYPE html><html><head><title>Moya - Grok</title></head><body><h1>Moya</h1><div id=\"a\"></div><div id=\"b\"></div></body></html>",
    { runScripts: "dangerously", url: "https://grok.com/bot/abc-123" }
  );
  const window = dom.window;
  for (const file of ["src/config.js", "src/playback.js", "src/bots.js", "src/updates.js", "src/controls.js"]) {
    window.eval(fs.readFileSync(path.join(root, file), "utf8"));
  }
  return window;
}

const window = loadWindow();
const GV = window.GrokVoice;

test("previous and next walk assistant replies in order", () => {
  const spoken = [];
  const playback = GV.createPlayback({
    onSpeak: function (text) { spoken.push(text); }
  });
  playback.setItems([
    { key: "a", speech: "First reply here." },
    { key: "b", speech: "Second reply here." },
    { key: "c", speech: "Third reply here." }
  ]);
  assert.equal(playback.previous(), "Second reply here.");
  assert.equal(playback.previous(), "First reply here.");
  assert.equal(playback.previous(), "First reply here.");
  assert.equal(playback.next(), "Second reply here.");
  assert.equal(playback.next(), "Third reply here.");
  assert.equal(playback.next(), "Third reply here.");
  assert.deepEqual(spoken, [
    "Second reply here.",
    "First reply here.",
    "First reply here.",
    "Second reply here.",
    "Third reply here.",
    "Third reply here."
  ]);
});

test("pause holds the reply and resume restarts it only when the browser cannot", () => {
  const spoken = [];
  let resumeWorks = false;
  const playback = GV.createPlayback({
    onSpeak: function (text) { spoken.push(text); },
    onPause: function () { return true; },
    onResume: function () { return resumeWorks; }
  });
  playback.setItems([{ key: "a", speech: "Read this paragraph again." }]);
  assert.equal(playback.next(), "Read this paragraph again.");
  const paused = playback.toggle();
  assert.equal(paused.mode, "paused");
  assert.equal(paused.restarted, false);
  assert.equal(playback.state().icon, "play");
  resumeWorks = true;
  const resumed = playback.toggle();
  assert.equal(resumed.mode, "playing");
  assert.equal(resumed.restarted, false);
  assert.equal(spoken.length, 1);
  playback.toggle();
  resumeWorks = false;
  const restarted = playback.toggle();
  assert.equal(restarted.restarted, true);
  assert.equal(restarted.speech, "Read this paragraph again.");
  assert.deepEqual(spoken, ["Read this paragraph again.", "Read this paragraph again."]);
});

test("each bot keeps its own voice and mute, and new bots follow the default", () => {
  const bot = GV.botFromLocation("https://grok.com/bot/abc-123", GV.botLabel(window.document));
  assert.equal(bot.id, "abc-123");
  assert.equal(bot.name, "Moya");
  const stored = { voiceURI: "browser-default", newBotsAutoRead: true, bots: {} };
  assert.equal(GV.botVoiceURI(stored, bot), "browser-default");
  assert.equal(GV.botAutoRead(stored, bot), true);
  stored.bots = { "abc-123": { name: "Moya", voiceURI: "jenny", autoRead: false } };
  assert.equal(GV.botVoiceURI(stored, bot), "jenny");
  assert.equal(GV.botAutoRead(stored, bot), false);
  stored.newBotsAutoRead = false;
  const fresh = { id: "later-bot", name: "Later" };
  assert.equal(GV.botAutoRead(stored, fresh), false);
  assert.equal(GV.botVoiceURI(stored, fresh), "browser-default");
  stored.newBotsAutoRead = true;
  assert.equal(GV.botAutoRead(stored, fresh), true);
});

test("update check keeps ext-v tags and hides prereleases unless beta is on", () => {
  const releases = [
    { tag_name: "v1.4.0", prerelease: false, html_url: "https://example/desktop" },
    { tag_name: "ext-v0.1.6", prerelease: false, html_url: "https://example/016" },
    { tag_name: "ext-v0.2.0", draft: true, html_url: "https://example/draft" },
    {
      tag_name: "ext-v0.2.1",
      prerelease: false,
      html_url: "https://example/021",
      assets: [{ name: "Grok-Voice-Reader-Extension.zip", browser_download_url: "https://example/021.zip" }]
    },
    {
      tag_name: "ext-v0.9.0",
      prerelease: true,
      html_url: "https://example/beta",
      assets: [{ name: "Grok-Voice-Reader-Extension.zip", browser_download_url: "https://example/beta.zip" }]
    }
  ];
  const stable = GV.pickExtensionUpdate(releases, "0.2.0", { beta: false });
  assert.equal(stable.tag, "ext-v0.2.1");
  assert.equal(stable.url, "https://example/021.zip");
  assert.equal(GV.pickExtensionUpdate(releases, "0.2.1", { beta: false }), null);
  const beta = GV.pickExtensionUpdate(releases, "0.2.1", { beta: true });
  assert.equal(beta.tag, "ext-v0.9.0");
  assert.equal(beta.url, "https://example/beta.zip");
  assert.equal(GV.pickExtensionUpdate(releases, "9.0.0", { beta: true }), null);
  assert.equal(GV.updateCheckDue(0, 5000), true);
  assert.equal(GV.updateCheckDue(1000, 2000), false);
  assert.equal(GV.updateCheckDue(1000, 1000 + GV.UPDATE_INTERVAL_MS), true);
});

test("the control bar sits on the reply being read and moves with it", () => {
  const doc = window.document;
  const first = doc.getElementById("a");
  const second = doc.getElementById("b");
  GV.placeReadingControls(doc, first, { mode: "playing" });
  const bar = doc.querySelector("[data-grok-voice-controls]");
  assert.ok(bar);
  assert.equal(bar.getAttribute("data-reading-id"), "a");
  assert.equal(first.classList.contains("grok-voice-reading"), true);
  assert.equal(second.classList.contains("grok-voice-reading"), false);
  const pause = bar.shadowRoot.querySelector('[data-action="play-pause"]');
  const previous = bar.shadowRoot.querySelector('[data-action="previous"]');
  const next = bar.shadowRoot.querySelector('[data-action="next"]');
  assert.equal(pause.getAttribute("aria-label"), "Pause (Alt+Shift+P)");
  assert.equal(previous.getAttribute("title"), "Previous reply (Alt+Left)");
  assert.equal(next.getAttribute("title"), "Next reply (Alt+Right)");
  assert.equal(bar.style.position, "fixed");
  GV.placeReadingControls(doc, second, { mode: "paused" });
  assert.equal(first.classList.contains("grok-voice-reading"), false);
  assert.equal(second.classList.contains("grok-voice-reading"), true);
  assert.equal(doc.querySelector("[data-grok-voice-controls]").getAttribute("data-reading-id"), "b");
  assert.equal(bar.shadowRoot.querySelector('[data-action="play-pause"]').getAttribute("aria-label"), "Play (Alt+Shift+P)");
  assert.equal(doc.querySelectorAll("[data-grok-voice-controls]").length, 1);
});

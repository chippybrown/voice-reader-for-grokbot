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

test("the green outline follows the reply being read", () => {
  const doc = window.document;
  const first = doc.getElementById("a");
  const second = doc.getElementById("b");
  GV.placeReadingControls(doc, first, { mode: "playing" });
  assert.equal(first.classList.contains("grok-voice-reading"), true);
  assert.equal(second.classList.contains("grok-voice-reading"), false);
  GV.placeReadingControls(doc, second, { mode: "paused" });
  assert.equal(first.classList.contains("grok-voice-reading"), false);
  assert.equal(second.classList.contains("grok-voice-reading"), true);
  GV.placeReadingControls(doc, null, { mode: "stopped" });
  assert.equal(first.classList.contains("grok-voice-reading"), false);
  assert.equal(second.classList.contains("grok-voice-reading"), false);
});

function composerMarkup() {
  return '<button id="add" type="button">+</button>' +
    '<textarea id="message" placeholder="Message Moya"></textarea>' +
    '<button id="mic" type="button" aria-label="Microphone"></button>' +
    '<button id="voice" type="button" aria-label="Voice mode"></button>';
}

test("controls are injected between the mic and the voice button and survive a re-render", async () => {
  const doc = window.document;
  const box = doc.createElement("div");
  box.id = "composer";
  box.innerHTML = composerMarkup();
  doc.body.appendChild(box);
  const host = GV.mountTransport(doc, { mode: "playing" });
  const voice = doc.getElementById("voice");
  const mic = doc.getElementById("mic");
  const field = doc.getElementById("message");
  assert.equal(host.getAttribute("data-grok-voice-placement"), "composer");
  assert.equal(host.nextElementSibling, voice);
  assert.equal(host.previousElementSibling, mic);
  assert.equal(host.parentNode, box);
  field.value = "still typing";
  assert.equal(field.value, "still typing");
  const pause = host.shadowRoot.querySelector('[data-action="play-pause"]');
  assert.equal(pause.getAttribute("aria-label").indexOf("Pause (Alt+Shift+P)") === 0, true);
  assert.equal(pause.getAttribute("aria-label").indexOf("Click the reply") !== -1, true);
  GV.watchComposer(doc, function () { return { mode: "paused" }; });
  box.innerHTML = composerMarkup();
  await delay(30);
  const again = doc.querySelector("[data-grok-voice-controls]");
  assert.ok(again);
  assert.equal(again.getAttribute("data-grok-voice-placement"), "composer");
  assert.equal(again.previousElementSibling.id, "mic");
  assert.equal(again.nextElementSibling.id, "voice");
  assert.equal(doc.getElementById("message").placeholder, "Message Moya");
});

test("controls sit above the composer when the mic and voice buttons are missing", () => {
  const doc = window.document;
  const rich = doc.getElementById("composer");
  if (rich) rich.remove();
  const stale = doc.querySelector("[data-grok-voice-controls]");
  if (stale) stale.remove();
  const plain = doc.createElement("div");
  plain.id = "plain-composer";
  plain.innerHTML = '<textarea placeholder="Message Moya"></textarea>';
  plain.getBoundingClientRect = function () {
    return { top: 500, left: 80, right: 700, bottom: 560, width: 620, height: 60, x: 80, y: 500 };
  };
  doc.body.appendChild(plain);
  Object.defineProperty(window, "innerWidth", { configurable: true, value: 800 });
  Object.defineProperty(window, "innerHeight", { configurable: true, value: 600 });
  const host = GV.mountTransport(doc, { mode: "stopped" });
  assert.equal(host.getAttribute("data-grok-voice-placement"), "above");
  assert.equal(host.style.position, "fixed");
  assert.equal(parseFloat(host.style.top), 464);
  assert.equal(parseFloat(host.style.left), 604);
});

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function mouse(target, type, x, y, detail) {
  target.dispatchEvent(new window.MouseEvent(type, {
    bubbles: true,
    cancelable: true,
    button: 0,
    detail: detail || 1,
    clientX: x,
    clientY: y
  }));
}

let replyClicks = 0;
let clickRoot = null;
GV.bindReplyClick(window.document, function (node) {
  const el = node && node.nodeType === 1 ? node : node && node.parentElement;
  return Boolean(clickRoot && el && clickRoot.contains(el));
}, function () { replyClicks += 1; });

test("a quick click on the outlined reply toggles play", async () => {
  clickRoot = window.document.getElementById("a");
  replyClicks = 0;
  mouse(clickRoot, "mousedown", 12, 12, 1);
  mouse(clickRoot, "mouseup", 13, 12, 1);
  await delay(320);
  assert.equal(replyClicks, 1);
});

test("dragging across the reply does not toggle play", async () => {
  clickRoot = window.document.getElementById("a");
  clickRoot.textContent = "Select this reply text instead of toggling.";
  replyClicks = 0;
  mouse(clickRoot, "mousedown", 8, 8, 1);
  mouse(clickRoot, "mouseup", 40, 18, 1);
  await delay(320);
  assert.equal(replyClicks, 0);
});

test("a double-click does not toggle play", async () => {
  clickRoot = window.document.getElementById("a");
  replyClicks = 0;
  mouse(clickRoot, "mousedown", 12, 12, 1);
  mouse(clickRoot, "mouseup", 12, 12, 1);
  mouse(clickRoot, "mousedown", 12, 12, 2);
  mouse(clickRoot, "mouseup", 12, 12, 2);
  clickRoot.dispatchEvent(new window.MouseEvent("dblclick", { bubbles: true, detail: 2, clientX: 12, clientY: 12 }));
  await delay(320);
  assert.equal(replyClicks, 0);
});

test("a click on a link inside the reply does not toggle play", async () => {
  clickRoot = window.document.getElementById("a");
  const link = window.document.createElement("a");
  link.href = "https://example.com/notes";
  link.textContent = "notes";
  clickRoot.appendChild(link);
  replyClicks = 0;
  mouse(link, "mousedown", 12, 12, 1);
  mouse(link, "mouseup", 12, 12, 1);
  await delay(320);
  assert.equal(replyClicks, 0);
});

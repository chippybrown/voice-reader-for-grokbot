const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const root = path.join(__dirname, "..");

function loadExtension() {
  const context = { console, setTimeout, clearTimeout, URL };
  context.globalThis = context;
  vm.createContext(context);
  for (const file of ["src/config.js", "src/text.js", "src/reader.js"]) {
    const filename = path.join(root, file);
    vm.runInContext(fs.readFileSync(filename, "utf8"), context, { filename });
  }
  return context.GrokVoice;
}

const GV = loadExtension();

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

test("match list is valid and copied into the manifest", () => {
  const manifest = JSON.parse(fs.readFileSync(path.join(root, "manifest.json"), "utf8"));
  assert.deepEqual(manifest.permissions, ["storage", "activeTab"]);
  assert.equal(manifest.manifest_version, 3);
  assert.ok(GV.MATCHES.length > 0);
  for (const pattern of GV.MATCHES) assert.equal(GV.patternValid(pattern), true);
  assert.deepEqual(manifest.host_permissions, Array.from(GV.MATCHES).concat(GV.EXTRA_HOSTS));
  assert.deepEqual(manifest.content_scripts[0].matches, Array.from(GV.MATCHES));
  assert.equal(manifest.content_scripts[0].all_frames, true);
  assert.equal(manifest.content_scripts[0].match_about_blank, true);
  assert.equal(manifest.content_scripts[0].match_origin_as_fallback, true);
  assert.equal(manifest.version, "0.2.3");
  assert.equal(manifest.commands.previous.suggested_key.default, GV.SHORTCUTS.previous);
  assert.equal(manifest.commands["play-pause"].suggested_key.default, GV.SHORTCUTS.playPause);
  assert.equal(manifest.commands.next.suggested_key.default, GV.SHORTCUTS.next);
  assert.deepEqual(manifest.content_scripts[0].js, [
    "src/config.js",
    "src/text.js",
    "src/detect.js",
    "src/reader.js",
    "src/playback.js",
    "src/bots.js",
    "src/controls.js",
    "src/content.js"
  ]);
});

test("url match list covers Grok hosts and not other sites", () => {
  assert.equal(GV.urlMatches("https://grok.com/"), true);
  assert.equal(GV.urlMatches("https://grok.com/chat/abc"), true);
  assert.equal(GV.urlMatches("https://grok.com/bot/3f1c0c2e-7a1b-4c89-9d2e-111111111111"), true);
  assert.equal(GV.urlMatches("https://grok.x.ai/"), true);
  assert.equal(GV.urlMatches("https://preview.grok.com/c/1"), true);
  assert.equal(GV.urlMatches("https://cursor.com/agents"), true);
  assert.equal(GV.urlMatches("https://api.x.ai/v1"), true);
  assert.equal(GV.urlMatches("https://example.com/"), false);
  assert.equal(GV.urlMatches("https://notgrok.com/"), false);
  assert.equal(GV.urlMatches("https://grok.com.evil.com/"), false);
  assert.equal(GV.urlMatches("https://x.com/home"), false);
  assert.equal(GV.urlMatches("https://evil.example/grok.com/"), false);
});

test("speech text drops markdown, urls, and symbols but keeps labels", () => {
  const raw = "The newest answer is ready. See the docs for more. **not stars** and a bare https://example.com/raw-url to skip. Also [notes](https://example.com/notes-url) please.";
  const speech = GV.stripForSpeech(raw);
  assert.equal(speech, "The newest answer is ready. See the docs for more. not stars and a bare to skip. Also notes please.");
  assert.equal(speech.includes("example.com"), false);
  assert.equal(speech.includes("*"), false);
  assert.equal(GV.stripForSpeech("# Title\n- item\n`code`"), "Title item code");
  assert.equal(GV.stripForSpeech("```js\nconst n = 1\n```"), "const n = 1");
});

test("old history and a growing old reply stay quiet", async () => {
  const spoken = [];
  const session = GV.createSession({ settleMs: 40, onSpeak: (text) => spoken.push(text) });
  const old = "This old answer should stay quiet.";
  session.arm([{ key: "old", raw: old, speech: old }]);
  session.watch([{ key: "old", raw: old, speech: old }]);
  session.watch([{ key: "old", raw: old + " Still old.", speech: old + " Still old." }]);
  await delay(80);
  assert.deepEqual(spoken, []);
});

test("a new reply is spoken once after it stops changing", async () => {
  const spoken = [];
  const session = GV.createSession({ settleMs: 50, onSpeak: (text) => spoken.push(text) });
  const old = "This old answer should stay quiet.";
  session.arm([{ key: "old", raw: old, speech: old }]);
  session.watch([
    { key: "old", raw: old, speech: old },
    { key: "new", raw: "The newest", speech: "The newest" }
  ]);
  await delay(20);
  assert.deepEqual(spoken, []);
  session.watch([
    { key: "old", raw: old + " Still old.", speech: old + " Still old." },
    { key: "new", raw: "The newest answer is ready.", speech: "The newest answer is ready." }
  ]);
  await delay(30);
  assert.deepEqual(spoken, []);
  await delay(80);
  assert.deepEqual(spoken, ["The newest answer is ready."]);
  session.watch([
    { key: "old", raw: old, speech: old },
    { key: "new", raw: "The newest answer is ready.", speech: "The newest answer is ready." }
  ]);
  await delay(80);
  assert.deepEqual(spoken, ["The newest answer is ready."]);
});

test("a changed reply is spoken once after it settles again", async () => {
  const spoken = [];
  const session = GV.createSession({ settleMs: 30, onSpeak: (text) => spoken.push(text) });
  session.arm([]);
  const first = "The newest answer is ready today.";
  session.watch([{ key: "new", raw: first, speech: first }]);
  await delay(60);
  assert.deepEqual(spoken, [first]);
  const grown = first + " More words arrived.";
  session.watch([{ key: "new", raw: grown, speech: grown }]);
  await delay(20);
  assert.deepEqual(spoken, [first]);
  await delay(50);
  assert.deepEqual(spoken, [first, grown]);
});

test("stop drops a reply that has not been spoken yet", async () => {
  const spoken = [];
  const session = GV.createSession({ settleMs: 80, onSpeak: (text) => spoken.push(text) });
  session.arm([]);
  session.watch([{ key: "new", raw: "Wait for the quiet gap please.", speech: "Wait for the quiet gap please." }]);
  session.stop();
  await delay(120);
  assert.deepEqual(spoken, []);
});

test("replay speaks the last reply again", async () => {
  const spoken = [];
  const session = GV.createSession({ settleMs: 20, onSpeak: (text) => spoken.push(text) });
  session.arm([]);
  session.watch([{ key: "new", raw: "Say this reply once.", speech: "Say this reply once." }]);
  await delay(50);
  assert.equal(session.replay(), "Say this reply once.");
  assert.deepEqual(spoken, ["Say this reply once.", "Say this reply once."]);
});

test("turning on arms the current reply instead of speaking it", async () => {
  const spoken = [];
  const session = GV.createSession({ settleMs: 20, onSpeak: (text) => spoken.push(text) });
  session.setEnabled(false);
  const existing = "Already on the page when the switch was turned on.";
  session.setEnabled(true);
  session.arm([{ key: "old", raw: existing, speech: existing }]);
  session.watch([{ key: "old", raw: existing, speech: existing }]);
  await delay(50);
  assert.deepEqual(spoken, []);
});

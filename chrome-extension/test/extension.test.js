const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const puppeteer = require("puppeteer-core");

const root = path.join(__dirname, "..");
const fixture = fs.readFileSync(path.join(__dirname, "fixture.html"), "utf8");
const expected = "The newest answer is ready. See the docs for more. not stars and a bare to skip. Also notes please.";

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// Branded Chrome ignores --load-extension. Puppeteer installs the unpacked
// folder through the DevTools Extensions domain instead.
async function launch() {
  const browser = await puppeteer.launch({
    executablePath: process.env.CHROME_PATH || "/usr/bin/google-chrome",
    headless: true,
    pipe: true,
    enableExtensions: true,
    args: ["--no-sandbox", "--disable-dev-shm-usage"]
  });
  const id = await browser.installExtension(root);
  return { browser, id };
}

// Context ids belong to one DevTools session. Keep that session and the
// content-script world (the isolated world that loaded GrokVoice).
async function contentWorld(page) {
  const client = await page.createCDPSession();
  const contexts = [];
  client.on("Runtime.executionContextCreated", (event) => {
    contexts.push(event.context);
  });
  await client.send("Runtime.enable");
  await delay(200);
  for (const context of contexts) {
    if (!context.auxData || context.auxData.type !== "isolated") continue;
    const probed = await client.send("Runtime.evaluate", {
      contextId: context.id,
      expression: "typeof globalThis.GrokVoice",
      returnByValue: true
    });
    if (probed.result && probed.result.value === "object") {
      return {
        evaluate: async (expression) => {
          const evaluated = await client.send("Runtime.evaluate", {
            contextId: context.id,
            expression,
            returnByValue: true,
            awaitPromise: true
          });
          if (evaluated.exceptionDetails) {
            throw new Error("Content script error: " + JSON.stringify(evaluated.exceptionDetails));
          }
          return evaluated.result.value;
        }
      };
    }
  }
  throw new Error("Content script world was not found");
}

async function stubSpeech(world) {
  const installed = await world.evaluate(`(() => {
    const spoken = [];
    globalThis.__grokVoiceSpoken = spoken;
    function record(utterance) {
      spoken.push(String(utterance && utterance.text || ""));
      try { if (utterance && utterance.onstart) utterance.onstart(); } catch (err) {}
      try { if (utterance && utterance.onend) utterance.onend(); } catch (err) {}
    }
    const proto = globalThis.SpeechSynthesis && globalThis.SpeechSynthesis.prototype;
    if (proto) {
      proto.speak = function (utterance) { record(utterance); };
      proto.cancel = function () {};
    }
    const synth = globalThis.speechSynthesis;
    if (synth) {
      try { synth.speak = function (utterance) { record(utterance); }; } catch (err) {}
      try { synth.cancel = function () {}; } catch (err) {}
    }
    return { hasProto: Boolean(proto), hasSynth: Boolean(synth) };
  })()`);
  if (!installed || (!installed.hasProto && !installed.hasSynth)) {
    throw new Error("Could not stub speechSynthesis: " + JSON.stringify(installed));
  }
  return installed;
}

async function spokenTexts(world) {
  return (await world.evaluate("globalThis.__grokVoiceSpoken || []")) || [];
}

test("extension speaks only the newest reply, once", { timeout: 60000 }, async () => {
  const { browser, id } = await launch();
  try {
    const workerTarget = await browser.waitForTarget(
      (target) => target.type() === "service_worker" && target.url().includes(id),
      { timeout: 15000 }
    );
    const worker = await workerTarget.worker();
    const matches = await worker.evaluate(() => globalThis.GrokVoice.MATCHES.slice());
    assert.ok(matches.some((pattern) => pattern.includes("grok.com")));

    const page = await browser.newPage();
    const logs = [];
    page.on("console", (msg) => logs.push(msg.text()));
    await page.setRequestInterception(true);
    page.on("request", (request) => {
      if (request.url().startsWith("https://grok.com/")) {
        request.respond({
          status: 200,
          contentType: "text/html; charset=utf-8",
          body: fixture
        }).catch(() => {});
        return;
      }
      request.continue().catch(() => {});
    });

    await page.goto("https://grok.com/voice-reader-fixture", { waitUntil: "domcontentloaded" });
    await page.waitForSelector("html[data-grok-voice-armed='1']", { timeout: 10000 });

    const badge = await waitForBadge(worker);
    assert.equal(badge, "ON");

    const world = await contentWorld(page);
    await stubSpeech(world);
    assert.deepEqual(await spokenTexts(world), []);

    await page.evaluate(() => window.streamNewReply());
    await delay(400);
    assert.deepEqual(await spokenTexts(world), [], "spoke before the reply settled");

    const spoken = await waitForSpoken(world);
    assert.equal(spoken.join(" "), expected);
    for (const banned of ["stay quiet", "Still old", "Hidden secret", "CSSHIDDEN", "Aria hidden", "Do not read", "What was already asked", "File menu", "Tooltip hint", "Moya", "2:14", "2:15", "Copy", "example.com", "secret-path", "*", "`"]) {
      assert.equal(spoken.join(" ").includes(banned), false, banned);
    }

    await page.evaluate(() => {
      document.getElementById("stream-body").classList.add("touched");
    });
    await delay(1800);
    assert.equal((await spokenTexts(world)).join(" "), expected);

    await world.evaluate("new Promise((resolve) => chrome.storage.local.set({ debug: true }, resolve))");
    await page.waitForSelector(".grok-voice-debug-target", { timeout: 3000 });
    const outlined = await page.$eval(".grok-voice-debug-target", (el) => el.innerText);
    assert.equal(outlined.includes("The newest answer is ready"), true);
    assert.equal(outlined.includes("Do not read"), false);
    assert.equal(outlined.includes("Moya"), false);
    assert.equal(logs.some((line) => line.indexOf("[GrokVoice]") !== -1 && line.indexOf("blocks=") !== -1), true);
  } finally {
    await browser.close().catch(() => {});
  }
});

const latePage = `<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Late chat</title></head>
<body>
  <p id="waiting">Chat is not mounted yet.</p>
  <script>
    window.mountLateChat = function () {
      var thread = document.createElement("div");
      thread.id = "late-thread";
      thread.style.cssText = "overflow-y:auto;height:420px;display:flex;flex-direction:column;gap:12px";
      document.body.appendChild(thread);
      function add(text, user) {
        var turn = document.createElement("div");
        turn.style.display = "flex";
        turn.style.justifyContent = user ? "flex-end" : "flex-start";
        var pad = document.createElement("div");
        pad.style.background = user ? "#6d28d9" : "#2b2e36";
        pad.style.color = "#fff";
        pad.style.borderRadius = "16px";
        pad.style.padding = "10px 14px";
        pad.style.maxWidth = "75%";
        var paragraph = document.createElement("p");
        paragraph.dir = "auto";
        paragraph.className = "break-words last:mb-0 streamdown-first-block:mt-0";
        paragraph.style.whiteSpace = "pre-wrap";
        paragraph.textContent = text;
        pad.appendChild(paragraph);
        turn.appendChild(pad);
        thread.appendChild(turn);
      }
      add("First late reply should stay quiet.", false);
      add("A question from the person.", true);
      add("The newest late reply should be spoken.", false);
    };
  </script>
</body></html>`;

test("a chat container inserted after startup is read", { timeout: 30000 }, async () => {
  const { browser } = await launch();
  try {
    const page = await browser.newPage();
    await page.setRequestInterception(true);
    page.on("request", (request) => {
      if (request.url().startsWith("https://grok.com/")) {
        request.respond({
          status: 200,
          contentType: "text/html; charset=utf-8",
          body: latePage
        }).catch(() => {});
        return;
      }
      request.continue().catch(() => {});
    });
    await page.goto("https://grok.com/late-chat", { waitUntil: "domcontentloaded" });
    await page.waitForSelector("html[data-grok-voice-armed='1']", { timeout: 10000 });
    const world = await contentWorld(page);
    await stubSpeech(world);
    await page.evaluate(() => window.mountLateChat());
    const spoken = await waitForSpoken(world);
    assert.deepEqual(spoken, ["The newest late reply should be spoken."]);
    const detected = await page.$eval("html", (el) => ({
      count: el.getAttribute("data-grok-voice-detected"),
      snippet: el.getAttribute("data-grok-voice-snippet")
    }));
    assert.equal(detected.count, "2");
    assert.equal(detected.snippet.includes("The newest late reply"), true);
    assert.equal(detected.snippet.includes("First late reply"), false);
  } finally {
    await browser.close().catch(() => {});
  }
});

const nestedPage = `<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Nested chat</title></head>
<body>
  <div id="shadow-host"></div>
  <iframe id="chat-frame" title="chat"></iframe>
  <script>
    window.mountNested = function () {
      document.getElementById("shadow-host").attachShadow({ mode: "open" });
      document.getElementById("chat-frame").srcdoc = '<!DOCTYPE html><html><body><div id="slot"></div></body></html>';
    };
    window.addShadowReply = function () {
      document.getElementById("shadow-host").shadowRoot.innerHTML = '<div style="display:flex;justify-content:flex-start"><div style="background:#2b2e36;color:#fff;padding:10px;border-radius:16px"><p dir="auto" class="break-words streamdown-first-block:mt-0" style="white-space:pre-wrap">Shadow assistant reply should be spoken.</p></div></div>';
    };
    window.iframeReplyHtml = '<div style="display:flex;justify-content:flex-end"><div style="background:#6d28d9;color:#fff;padding:10px"><p dir="auto" class="break-words streamdown-first-block:mt-0">User text in the frame.</p></div></div><div style="display:flex;justify-content:flex-start"><div style="background:#2b2e36;color:#fff;padding:10px;border-radius:16px"><p dir="auto" class="break-words streamdown-first-block:mt-0" style="white-space:pre-wrap">Iframe assistant reply should be spoken.</p></div></div>';
  </script>
</body></html>`;

test("shadow root and iframe chats are both detected", { timeout: 45000 }, async () => {
  const { browser } = await launch();
  try {
    const page = await browser.newPage();
    const client = await page.createCDPSession();
    const pendingIds = new Set();
    const worldIds = [];
    client.on("Runtime.executionContextCreated", (event) => {
      const context = event.context;
      if (context.auxData && context.auxData.type === "isolated") pendingIds.add(context.id);
    });
    await client.send("Runtime.enable");
    async function stubNewWorlds() {
      for (const id of Array.from(pendingIds)) {
        if (worldIds.indexOf(id) !== -1) {
          pendingIds.delete(id);
          continue;
        }
        try {
          const probed = await client.send("Runtime.evaluate", {
            contextId: id,
            expression: "typeof globalThis.GrokVoice",
            returnByValue: true
          });
          if (!probed.result || probed.result.value !== "object") continue;
          await client.send("Runtime.evaluate", {
            contextId: id,
            expression: `(() => {
              const spoken = [];
              globalThis.__grokVoiceSpoken = spoken;
              function record(utterance) { spoken.push(String(utterance && utterance.text || "")); }
              const proto = globalThis.SpeechSynthesis && globalThis.SpeechSynthesis.prototype;
              if (proto) { proto.speak = record; proto.cancel = function () {}; }
              const synth = globalThis.speechSynthesis;
              if (synth) {
                try { synth.speak = record; } catch (err) {}
                try { synth.cancel = function () {}; } catch (err) {}
              }
            })()`
          });
          worldIds.push(id);
          pendingIds.delete(id);
        } catch (err) {
          pendingIds.delete(id);
        }
      }
    }
    await page.setRequestInterception(true);
    page.on("request", (request) => {
      if (request.url().startsWith("https://grok.com/")) {
        request.respond({
          status: 200,
          contentType: "text/html; charset=utf-8",
          body: nestedPage
        }).catch(() => {});
        return;
      }
      request.continue().catch(() => {});
    });
    await page.goto("https://grok.com/nested-chat", { waitUntil: "domcontentloaded" });
    await page.waitForSelector("html[data-grok-voice-armed='1']", { timeout: 10000 });
    await delay(300);
    await stubNewWorlds();
    await page.evaluate(() => window.mountNested());
    let child = null;
    for (let i = 0; i < 30; i++) {
      child = page.frames().find((frame) => frame.url() === "about:srcdoc");
      if (child) {
        const armed = await child.evaluate(() => document.documentElement.getAttribute("data-grok-voice-armed")).catch(() => null);
        if (armed === "1") break;
      }
      await delay(100);
    }
    assert.ok(child, "srcdoc frame was not created");
    await stubNewWorlds();
    await child.evaluate((html) => {
      document.getElementById("slot").innerHTML = html;
    }, await page.evaluate(() => window.iframeReplyHtml));
    await page.evaluate(() => window.addShadowReply());
    let spoken = [];
    for (let i = 0; i < 40; i++) {
      await stubNewWorlds();
      spoken = [];
      const liveIds = worldIds.slice();
      for (const id of liveIds) {
        try {
          const result = await client.send("Runtime.evaluate", {
            contextId: id,
            expression: "globalThis.__grokVoiceSpoken || []",
            returnByValue: true
          });
          const list = result.result && result.result.value;
          if (Array.isArray(list)) spoken.push(...list);
        } catch (err) {
          const index = worldIds.indexOf(id);
          if (index !== -1) worldIds.splice(index, 1);
        }
      }
      if (spoken.includes("Shadow assistant reply should be spoken.") && spoken.includes("Iframe assistant reply should be spoken.")) break;
      await delay(150);
    }
    assert.equal(spoken.includes("Shadow assistant reply should be spoken."), true);
    child = page.frames().find((frame) => frame.url() === "about:srcdoc");
    const frameState = child ? await child.evaluate(() => ({
      detected: document.documentElement.getAttribute("data-grok-voice-detected"),
      snippet: document.documentElement.getAttribute("data-grok-voice-snippet"),
      armed: document.documentElement.getAttribute("data-grok-voice-armed"),
      html: document.body ? document.body.innerHTML.slice(0, 400) : ""
    })) : null;
    assert.equal(
      spoken.includes("Iframe assistant reply should be spoken."),
      true,
      JSON.stringify({ spoken, worlds: worldIds.length, frameState })
    );
    assert.equal(spoken.includes("User text in the frame."), false);
    const snippet = frameState && frameState.snippet;
    assert.equal(String(snippet).includes("Iframe assistant reply"), true);
    const topSnippet = await page.$eval("html", (el) => el.getAttribute("data-grok-voice-snippet"));
    assert.equal(String(topSnippet).includes("Shadow assistant reply"), true);
  } finally {
    await browser.close().catch(() => {});
  }
});

const typingPage = `<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Typing</title>
<style>
  #thread { overflow-y: auto; height: 420px; display: flex; flex-direction: column; gap: 12px; }
  .turn { display: flex; }
  .pad { color: #fff; border-radius: 16px; padding: 10px 14px; max-width: 75%; }
  .composer { padding: 12px; }
  textarea, [contenteditable] { width: 100%; box-sizing: border-box; }
</style></head>
<body>
  <div id="thread">
    <div class="turn" style="justify-content:flex-start">
      <div class="pad" style="background:#2b2e36">
        <p dir="auto" class="break-words streamdown-first-block:mt-0" style="white-space:pre-wrap">Old reply stays quiet.</p>
      </div>
    </div>
    <div class="turn" style="justify-content:flex-end">
      <div class="pad" style="background:rgb(110, 64, 200)">
        <p id="user-body" dir="auto" class="break-words streamdown-first-block:mt-0" style="white-space:pre-wrap">Already asked.</p>
      </div>
    </div>
  </div>
  <form class="composer">
    <textarea id="composer" placeholder="Message"></textarea>
    <div id="draft" contenteditable="true" role="textbox"><p dir="auto" class="break-words streamdown-first-block:mt-0">draft</p></div>
  </form>
  <script>
    window.addAssistant = function (text) {
      var turn = document.createElement("div");
      turn.className = "turn";
      turn.style.justifyContent = "flex-start";
      var pad = document.createElement("div");
      pad.className = "pad";
      pad.style.background = "#2b2e36";
      var paragraph = document.createElement("p");
      paragraph.dir = "auto";
      paragraph.className = "break-words streamdown-first-block:mt-0";
      paragraph.style.whiteSpace = "pre-wrap";
      paragraph.textContent = text;
      pad.appendChild(paragraph);
      turn.appendChild(pad);
      document.getElementById("thread").appendChild(turn);
    };
  </script>
</body></html>`;

async function typeInComposer(page) {
  await page.evaluate(() => {
    var box = document.getElementById("composer");
    var draft = document.getElementById("draft");
    var user = document.getElementById("user-body");
    box.focus();
    for (var i = 0; i < 20; i++) {
      box.value = "hello " + i;
      box.dispatchEvent(new KeyboardEvent("keydown", { key: "a", bubbles: true, cancelable: true }));
      box.dispatchEvent(new InputEvent("input", { bubbles: true, data: "a" }));
      draft.textContent = "draft " + i;
      draft.dispatchEvent(new InputEvent("input", { bubbles: true }));
    }
    user.textContent = "A typed user bubble must stay quiet.";
  });
}

test("keydowns and composer edits do not speak", { timeout: 60000 }, async () => {
  const { browser } = await launch();
  try {
    const page = await browser.newPage();
    await page.setRequestInterception(true);
    page.on("request", (request) => {
      if (request.url().startsWith("https://grok.com/")) {
        request.respond({
          status: 200,
          contentType: "text/html; charset=utf-8",
          body: typingPage
        }).catch(() => {});
        return;
      }
      request.continue().catch(() => {});
    });
    await page.goto("https://grok.com/typing", { waitUntil: "domcontentloaded" });
    await page.waitForSelector("html[data-grok-voice-armed='1']", { timeout: 10000 });
    const world = await contentWorld(page);
    await world.evaluate(`(() => {
      const spoken = [];
      let cancels = 0;
      let speaking = false;
      globalThis.__grokVoiceSpoken = spoken;
      globalThis.__grokVoiceCancels = () => cancels;
      function record(utterance) {
        spoken.push(String(utterance && utterance.text || ""));
        speaking = true;
      }
      function cancel() {
        cancels += 1;
        speaking = false;
      }
      const proto = globalThis.SpeechSynthesis && globalThis.SpeechSynthesis.prototype;
      if (proto) {
        proto.speak = function (utterance) { record(utterance); };
        proto.cancel = function () { cancel(); };
      }
      const synth = globalThis.speechSynthesis;
      if (synth) {
        try { synth.speak = function (utterance) { record(utterance); }; } catch (err) {}
        try { synth.cancel = function () { cancel(); }; } catch (err) {}
        try {
          Object.defineProperty(synth, "speaking", { configurable: true, get: function () { return speaking; } });
          Object.defineProperty(synth, "pending", { configurable: true, get: function () { return false; } });
        } catch (err) {}
      }
      return true;
    })()`);

    await typeInComposer(page);
    await delay(2200);
    assert.deepEqual(await spokenTexts(world), []);
    assert.equal(await world.evaluate("globalThis.__grokVoiceCancels()"), 0);

    await page.evaluate(() => window.addAssistant("Alpha reply should be spoken once."));
    const spoken = await waitForSpoken(world);
    assert.deepEqual(spoken, ["Alpha reply should be spoken once."]);
    const cancelsAfterSpeak = await world.evaluate("globalThis.__grokVoiceCancels()");

    await typeInComposer(page);
    await delay(2200);
    assert.deepEqual(await spokenTexts(world), ["Alpha reply should be spoken once."]);
    assert.equal(await world.evaluate("globalThis.__grokVoiceCancels()"), cancelsAfterSpeak);
  } finally {
    await browser.close().catch(() => {});
  }
});

test("a blocked utterance is spoken once on the next key", { timeout: 60000 }, async () => {
  const { browser } = await launch();
  try {
    const page = await browser.newPage();
    await page.setRequestInterception(true);
    page.on("request", (request) => {
      if (request.url().startsWith("https://grok.com/")) {
        request.respond({
          status: 200,
          contentType: "text/html; charset=utf-8",
          body: typingPage
        }).catch(() => {});
        return;
      }
      request.continue().catch(() => {});
    });
    await page.goto("https://grok.com/typing-unlock", { waitUntil: "domcontentloaded" });
    await page.waitForSelector("html[data-grok-voice-armed='1']", { timeout: 10000 });
    const world = await contentWorld(page);
    await world.evaluate(`(() => {
      const spoken = [];
      let calls = 0;
      globalThis.__grokVoiceSpoken = spoken;
      globalThis.__grokVoiceSpeakCalls = () => calls;
      function speak(utterance) {
        calls += 1;
        if (calls === 1) {
          if (utterance && typeof utterance.onerror === "function") utterance.onerror({ error: "not-allowed" });
          return;
        }
        spoken.push(String(utterance && utterance.text || ""));
      }
      const proto = globalThis.SpeechSynthesis && globalThis.SpeechSynthesis.prototype;
      if (proto) proto.speak = speak;
      const synth = globalThis.speechSynthesis;
      if (synth) {
        try { synth.speak = speak; } catch (err) {}
      }
      return true;
    })()`);

    await page.evaluate(() => window.addAssistant("Unlock this reply one time."));
    let calls = 0;
    for (let i = 0; i < 30 && calls < 1; i++) {
      calls = await world.evaluate("globalThis.__grokVoiceSpeakCalls()");
      if (calls < 1) await delay(150);
    }
    assert.equal(calls, 1);
    assert.deepEqual(await spokenTexts(world), []);

    await typeInComposer(page);
    await delay(400);
    assert.deepEqual(await spokenTexts(world), ["Unlock this reply one time."]);
    assert.equal(await world.evaluate("globalThis.__grokVoiceSpeakCalls()"), 2);

    await typeInComposer(page);
    await delay(500);
    assert.deepEqual(await spokenTexts(world), ["Unlock this reply one time."]);
    assert.equal(await world.evaluate("globalThis.__grokVoiceSpeakCalls()"), 2);
  } finally {
    await browser.close().catch(() => {});
  }
});

test("the chosen voice stays the same across replies", { timeout: 60000 }, async () => {
  const { browser } = await launch();
  try {
    const page = await browser.newPage();
    await page.setRequestInterception(true);
    page.on("request", (request) => {
      if (request.url().startsWith("https://grok.com/")) {
        request.respond({
          status: 200,
          contentType: "text/html; charset=utf-8",
          body: typingPage
        }).catch(() => {});
        return;
      }
      request.continue().catch(() => {});
    });
    await page.goto("https://grok.com/typing-voice", { waitUntil: "domcontentloaded" });
    await page.waitForSelector("html[data-grok-voice-armed='1']", { timeout: 10000 });
    const world = await contentWorld(page);
    await world.evaluate(`(() => {
      const used = [];
      globalThis.__grokVoiceUsed = used;
      globalThis.__flipVoices = false;
      globalThis.__voiceLists = 0;
      const OriginalUtterance = globalThis.SpeechSynthesisUtterance;
      function Utterance(text) {
        const utterance = new OriginalUtterance(text);
        let voice = null;
        Object.defineProperty(utterance, "voice", {
          configurable: true,
          enumerable: true,
          get: function () { return voice; },
          set: function (value) { voice = value; }
        });
        return utterance;
      }
      Utterance.prototype = OriginalUtterance.prototype;
      globalThis.SpeechSynthesisUtterance = Utterance;
      function list() {
        globalThis.__voiceLists += 1;
        if (globalThis.__flipVoices) {
          return [
            { voiceURI: "voice-b", lang: "en-GB", name: "B" },
            { voiceURI: "voice-c", lang: "en-US", name: "C" }
          ];
        }
        return [
          { voiceURI: "voice-b", lang: "en-GB", name: "B" },
          { voiceURI: "voice-a", lang: "en-US", name: "A" }
        ];
      }
      function record(utterance) {
        used.push({
          text: String(utterance && utterance.text || ""),
          voice: utterance && utterance.voice ? utterance.voice.voiceURI : ""
        });
      }
      const proto = globalThis.SpeechSynthesis && globalThis.SpeechSynthesis.prototype;
      if (proto) {
        proto.getVoices = list;
        proto.speak = function (utterance) { record(utterance); };
        proto.cancel = function () {};
      }
      const synth = globalThis.speechSynthesis;
      if (synth) {
        try { synth.getVoices = list; } catch (err) {}
        try { synth.speak = function (utterance) { record(utterance); }; } catch (err) {}
        try { synth.cancel = function () {}; } catch (err) {}
        try { synth.dispatchEvent(new Event("voiceschanged")); } catch (err) {}
      }
      return true;
    })()`);
    await world.evaluate("new Promise((resolve) => chrome.storage.local.set({ voiceURI: 'voice-a' }, resolve))");
    let lists = 0;
    for (let i = 0; i < 20 && lists < 1; i++) {
      lists = await world.evaluate("globalThis.__voiceLists");
      if (lists < 1) await delay(50);
    }
    assert.ok(lists >= 1, "voice list was not read after the saved voice was set");
    await world.evaluate(`(() => {
      globalThis.__flipVoices = true;
      const synth = globalThis.speechSynthesis;
      if (synth && synth.dispatchEvent) synth.dispatchEvent(new Event("voiceschanged"));
      if (synth && synth.getVoices) synth.getVoices();
      return true;
    })()`);

    await page.evaluate(() => window.addAssistant("First voiced reply stays on voice a."));
    let used = [];
    for (let i = 0; i < 30 && used.length < 1; i++) {
      used = (await world.evaluate("globalThis.__grokVoiceUsed")) || [];
      if (used.length < 1) await delay(150);
    }
    await page.evaluate(() => window.addAssistant("Second voiced reply stays on voice a."));
    for (let i = 0; i < 30 && used.length < 2; i++) {
      used = (await world.evaluate("globalThis.__grokVoiceUsed")) || [];
      if (used.length < 2) await delay(150);
    }
    assert.equal(used.length, 2);
    assert.equal(used[0].voice, "voice-a");
    assert.equal(used[1].voice, "voice-a");
    assert.equal(used[0].text.includes("First voiced reply"), true);
    assert.equal(used[1].text.includes("Second voiced reply"), true);
  } finally {
    await browser.close().catch(() => {});
  }
});

async function waitForBadge(worker) {
  let latest = "";
  for (let i = 0; i < 20; i++) {
    latest = await worker.evaluate(async () => {
      const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
      const tabId = tabs[0] && tabs[0].id;
      if (tabId == null) return "";
      return chrome.action.getBadgeText({ tabId });
    });
    if (latest === "ON") return latest;
    await delay(100);
  }
  return latest;
}

async function waitForSpoken(world) {
  let texts = [];
  for (let i = 0; i < 30; i++) {
    texts = await spokenTexts(world);
    if (texts.length) return texts;
    await delay(150);
  }
  return texts;
}

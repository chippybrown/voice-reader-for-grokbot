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
    assert.deepEqual(spoken, [expected]);
    for (const banned of ["stay quiet", "Still old", "Hidden secret", "CSSHIDDEN", "Aria hidden", "Do not read", "What was already asked", "File menu", "Tooltip hint", "Moya", "2:14", "2:15", "Copy", "example.com", "secret-path", "*", "`"]) {
      assert.equal(spoken[0].includes(banned), false, banned);
    }

    await page.evaluate(() => {
      document.getElementById("stream-body").classList.add("touched");
    });
    await delay(1800);
    assert.deepEqual(await spokenTexts(world), [expected]);

    await world.evaluate("new Promise((resolve) => chrome.storage.local.set({ debug: true }, resolve))");
    await page.waitForSelector(".grok-voice-debug-target", { timeout: 3000 });
    const outlined = await page.$eval(".grok-voice-debug-target", (el) => el.innerText);
    assert.equal(outlined.includes("The newest answer is ready"), true);
    assert.equal(outlined.includes("Do not read"), false);
    assert.equal(outlined.includes("Moya"), false);
    assert.equal(logs.some((line) => line.indexOf("[GrokVoice] blocks=") !== -1), true);
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

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
    for (const banned of ["stay quiet", "Still old", "Hidden secret", "CSSHIDDEN", "Aria hidden", "Do not read", "example.com", "secret-path", "*", "`"]) {
      assert.equal(spoken[0].includes(banned), false, banned);
    }

    await page.evaluate(() => {
      document.querySelector("[data-message-id='new-1']").classList.add("touched");
    });
    await delay(1800);
    assert.deepEqual(await spokenTexts(world), [expected]);
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

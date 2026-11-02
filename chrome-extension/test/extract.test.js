const assert = require("node:assert/strict");
const path = require("node:path");
const test = require("node:test");
const puppeteer = require("puppeteer-core");

const root = path.join(__dirname, "..");

const BLOCK = "break-words last:mb-0 max-md:leading-[155%] max-md:mb-4 max-md:last:mb-0 streamdown-first-block:mt-0";

const fixture = `<!DOCTYPE html>
<html>
<head>
  <style>
    #thread { overflow-y: auto; height: 480px; display: flex; flex-direction: column; gap: 16px; background: #16181d; }
    .turn { display: flex; width: 100%; }
    .start { justify-content: flex-start; }
    .end { justify-content: flex-end; }
    .card { display: flex; flex-direction: column; align-items: flex-start; gap: 4px; max-width: 75%; }
    .pad { border-radius: 16px; padding: 10px 14px; }
    .gray { background: #2b2e36; color: #f3f3f3; }
    .purple { background: #6d28d9; color: #fff; }
    .who { font-weight: 650; }
    .when { font-size: 12px; color: #9aa4ad; }
  </style>
</head>
<body>
  <div id="thread">
    <div class="turn end">
      <div class="pad purple">
        <p dir="auto" class="${BLOCK}" style="white-space: pre-wrap;">What was already asked?</p>
      </div>
    </div>
    <div class="turn start">
      <div class="card">
        <div class="who">Moya</div>
        <div class="when">2:14 PM</div>
        <div class="pad gray">
          <p dir="auto" class="${BLOCK}" style="white-space: pre-wrap;">The console tab lists running scripts.</p>
          <p dir="auto" class="${BLOCK}" style="white-space: pre-wrap;">Open Elements from there.</p>
          <ul><li>Inspect the bubble.</li></ul>
          <h2>Where to look</h2>
        </div>
        <button type="button">Copy</button>
      </div>
    </div>
  </div>
</body>
</html>`;

test("streamdown body is returned and the bot name is not", { timeout: 30000 }, async () => {
  const browser = await puppeteer.launch({
    executablePath: process.env.CHROME_PATH || "/usr/bin/google-chrome",
    headless: true,
    args: ["--no-sandbox", "--disable-dev-shm-usage"]
  });
  try {
    const page = await browser.newPage();
    await page.setContent(fixture, { waitUntil: "domcontentloaded" });
    await page.addScriptTag({ path: path.join(root, "src/config.js") });
    await page.addScriptTag({ path: path.join(root, "src/text.js") });
    await page.addScriptTag({ path: path.join(root, "src/detect.js") });
    const result = await page.evaluate(() => {
      const replies = globalThis.GrokVoice.detectAssistantReplies(document);
      const last = replies[replies.length - 1] || null;
      return {
        count: replies.length,
        speech: last ? last.speech : "",
        bodyText: last && last.body ? last.body.innerText : ""
      };
    });
    assert.equal(result.count, 1);
    assert.equal(
      result.speech,
      "The console tab lists running scripts. Open Elements from there. Inspect the bubble. Where to look"
    );
    assert.equal(result.speech.includes("Moya"), false);
    assert.equal(result.speech.includes("2:14"), false);
    assert.equal(result.speech.includes("Copy"), false);
    assert.equal(result.speech.includes("What was already asked"), false);
    assert.equal(result.bodyText.includes("Moya"), false);
    assert.equal(result.bodyText.includes("The console tab lists running scripts."), true);
  } finally {
    await browser.close().catch(() => {});
  }
});

test("the last assistant message is chosen, and a newer one is spoken", { timeout: 30000 }, async () => {
  const browser = await puppeteer.launch({
    executablePath: process.env.CHROME_PATH || "/usr/bin/google-chrome",
    headless: true,
    args: ["--no-sandbox", "--disable-dev-shm-usage"]
  });
  const block = "break-words last:mb-0 streamdown-first-block:mt-0";
  function bubble(id, text) {
    return `<div class="turn start" id="${id}"><div class="card"><div class="who">Moya</div><div class="pad gray"><p dir="auto" class="${block}" style="white-space: pre-wrap;">${text}</p></div></div></div>`;
  }
  const pageHtml = `<!DOCTYPE html>
<html><head><style>
  #thread { overflow-y: auto; height: 520px; display: flex; flex-direction: column; gap: 12px; background: #16181d; }
  .turn { display: flex; width: 100%; }
  .start { justify-content: flex-start; }
  .end { justify-content: flex-end; }
  .pad { border-radius: 16px; padding: 10px 14px; max-width: 75%; }
  .gray { background: #2b2e36; color: #f3f3f3; }
  .purple { background: #6d28d9; color: #fff; }
  .from { color: #bbb; font-size: 13px; align-self: center; }
</style></head><body>
  <div id="thread">
    ${bubble("a1", "First assistant reply stays quiet.")}
    <div class="from">Message from Grokbot Voice Chrome extension prototype Project</div>
    ${bubble("a2", "Second assistant reply stays quiet.")}
    <div class="turn end"><div class="pad purple"><p dir="auto" class="${block}" style="white-space: pre-wrap;">Okay, I heard the voice.</p></div></div>
    ${bubble("a3", "Third assistant reply is the one to read.")}
  </div>
</body></html>`;
  try {
    const page = await browser.newPage();
    await page.setContent(pageHtml, { waitUntil: "domcontentloaded" });
    for (const file of ["src/config.js", "src/text.js", "src/detect.js", "src/reader.js"]) {
      await page.addScriptTag({ path: path.join(root, file) });
    }
    const result = await page.evaluate(() => {
      const GV = globalThis.GrokVoice;
      const spoken = [];
      const keys = new WeakMap();
      let seq = 1;
      function keyFor(el) {
        let key = keys.get(el);
        if (!key) {
          key = "el:" + (seq++);
          keys.set(el, key);
        }
        return key;
      }
      function records() {
        return GV.detectAssistantReplies(document).map((reply) => ({
          key: keyFor(reply.element),
          raw: reply.raw,
          speech: reply.speech
        }));
      }
      const before = GV.latestAssistantReply(document);
      const session = GV.createSession({
        settleMs: 40,
        onSpeak: (text) => spoken.push(text)
      });
      session.arm(records());
      document.getElementById("thread").insertAdjacentHTML("beforeend",
        `<div class="turn start" id="a4"><div class="card"><div class="who">Moya</div><div class="pad gray"><p dir="auto" class="break-words last:mb-0 streamdown-first-block:mt-0" style="white-space: pre-wrap;">Fourth assistant reply should be spoken.</p></div></div></div>`);
      const after = GV.latestAssistantReply(document);
      session.watch(records());
      return new Promise((resolve) => {
        setTimeout(() => resolve({
          before: before ? before.speech : "",
          after: after ? after.speech : "",
          spoken
        }), 120);
      });
    });
    assert.equal(result.before, "Third assistant reply is the one to read.");
    assert.equal(result.before.includes("Moya"), false);
    assert.equal(result.before.includes("First assistant"), false);
    assert.equal(result.before.includes("Second assistant"), false);
    assert.equal(result.before.includes("Message from"), false);
    assert.equal(result.before.includes("Okay, I heard the voice"), false);
    assert.equal(result.after, "Fourth assistant reply should be spoken.");
    assert.deepEqual(result.spoken, ["Fourth assistant reply should be spoken."]);
  } finally {
    await browser.close().catch(() => {});
  }
});

test("open shadow root streamdown reply is found", { timeout: 30000 }, async () => {
  const browser = await puppeteer.launch({
    executablePath: process.env.CHROME_PATH || "/usr/bin/google-chrome",
    headless: true,
    args: ["--no-sandbox", "--disable-dev-shm-usage"]
  });
  try {
    const page = await browser.newPage();
    await page.setContent(`<!DOCTYPE html><body>
      <div id="host"></div>
      <div style="display:flex;justify-content:flex-end"><div style="background:#6d28d9;color:#fff;padding:8px"><p dir="auto">User fallback text.</p></div></div>
      <div style="display:flex;justify-content:flex-start"><div style="background:#2b2e36;color:#fff;padding:8px"><p dir="auto">Assistant fallback text.</p></div></div>
    </body>`, { waitUntil: "domcontentloaded" });
    await page.evaluate(() => {
      const root = document.getElementById("host").attachShadow({ mode: "open" });
      root.innerHTML = '<div style="display:flex;justify-content:flex-start"><div style="background:#2b2e36;color:#fff;padding:8px"><p dir="auto" class="break-words streamdown-first-block:mt-0" style="white-space:pre-wrap">Shadow assistant reply.</p></div></div>';
    });
    for (const file of ["src/config.js", "src/text.js", "src/detect.js"]) {
      await page.addScriptTag({ path: path.join(root, file) });
    }
    const result = await page.evaluate(() => {
      const report = globalThis.GrokVoice.inspectAssistant(document);
      return {
        mode: report.mode,
        speeches: report.replies.map((reply) => reply.speech)
      };
    });
    assert.equal(result.mode, "streamdown");
    assert.deepEqual(result.speeches, ["Shadow assistant reply."]);
  } finally {
    await browser.close().catch(() => {});
  }
});

test("fallback reads dir=auto bubbles when no streamdown class exists", { timeout: 30000 }, async () => {
  const browser = await puppeteer.launch({
    executablePath: process.env.CHROME_PATH || "/usr/bin/google-chrome",
    headless: true,
    args: ["--no-sandbox", "--disable-dev-shm-usage"]
  });
  try {
    const page = await browser.newPage();
    await page.setContent(`<!DOCTYPE html><body>
      <div style="display:flex;justify-content:flex-end"><div style="background:#6d28d9;color:#fff;padding:8px"><p dir="auto">User fallback text.</p></div></div>
      <div style="display:flex;justify-content:flex-start"><div style="background:#2b2e36;color:#fff;padding:8px"><p dir="auto">Assistant fallback text.</p></div></div>
    </body>`, { waitUntil: "domcontentloaded" });
    for (const file of ["src/config.js", "src/text.js", "src/detect.js"]) {
      await page.addScriptTag({ path: path.join(root, file) });
    }
    const result = await page.evaluate(() => {
      const report = globalThis.GrokVoice.inspectAssistant(document);
      return { mode: report.mode, speeches: report.replies.map((reply) => reply.speech) };
    });
    assert.equal(result.mode, "fallback");
    assert.deepEqual(result.speeches, ["Assistant fallback text."]);
  } finally {
    await browser.close().catch(() => {});
  }
});

test("a flex-end chat column does not hide assistant replies", { timeout: 30000 }, async () => {
  const browser = await puppeteer.launch({
    executablePath: process.env.CHROME_PATH || "/usr/bin/google-chrome",
    headless: true,
    args: ["--no-sandbox", "--disable-dev-shm-usage"]
  });
  const block = "break-words last:mb-0 streamdown-first-block:mt-0";
  try {
    const page = await browser.newPage();
    await page.setContent(`<!DOCTYPE html><body>
      <div id="column" class="justify-end items-end" style="display:flex;flex-direction:column;justify-content:flex-end;align-items:flex-end;height:480px;overflow-y:auto;background:#111;">
        <div style="display:flex;width:100%;justify-content:flex-start;">
          <div style="background:#2b2e36;color:#fff;padding:8px;border-radius:16px;"><p dir="auto" class="${block}">First assistant in a flex-end column.</p></div>
        </div>
        <div style="display:flex;width:100%;justify-content:flex-end;">
          <div style="background:rgb(110, 64, 200);color:#fff;padding:8px;border-radius:16px;margin-left:auto;"><p dir="auto" class="${block}">User purple text.</p></div>
        </div>
        <div style="display:flex;width:100%;justify-content:flex-start;">
          <div style="background:#2b2e36;color:#fff;padding:8px;border-radius:16px;"><p dir="auto" class="${block}">Last assistant should be chosen.</p></div>
        </div>
      </div>
    </body>`, { waitUntil: "domcontentloaded" });
    for (const file of ["src/config.js", "src/text.js", "src/detect.js"]) {
      await page.addScriptTag({ path: path.join(root, file) });
    }
    const result = await page.evaluate(() => {
      const report = globalThis.GrokVoice.inspectAssistant(document);
      return {
        mode: report.mode,
        blocks: report.blockCount,
        groups: report.groups.map((group) => group.role + ":" + group.reason),
        speeches: report.replies.map((reply) => reply.speech),
        latest: report.replies.length ? report.replies[report.replies.length - 1].speech : ""
      };
    });
    assert.equal(result.mode, "streamdown");
    assert.equal(result.blocks, 3);
    assert.equal(result.latest, "Last assistant should be chosen.");
    assert.deepEqual(result.speeches, [
      "First assistant in a flex-end column.",
      "Last assistant should be chosen."
    ]);
    assert.equal(result.groups.some((line) => line.indexOf("user:") === 0), true);
  } finally {
    await browser.close().catch(() => {});
  }
});

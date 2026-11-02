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

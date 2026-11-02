const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const { JSDOM } = require("jsdom");

const root = path.join(__dirname, "..");

function loadPage(html) {
  const dom = new JSDOM("<!DOCTYPE html><html><body>" + html + "</body></html>", {
    runScripts: "dangerously"
  });
  const window = dom.window;
  for (const file of ["src/config.js", "src/text.js", "src/detect.js"]) {
    window.eval(fs.readFileSync(path.join(root, file), "utf8"));
  }
  return window;
}

const wordSpans = [
  "I've", "also", "started", "building", "the", "shared", "workflow", "piece.",
  "It", "goes", "in", "switch"
].map((word) => "<span>" + word + "</span>").join(" ");

test("per-word streamdown spans keep the spaces shown on screen", () => {
  const window = loadPage(
    '<div id="reply">' +
      '<div class="who">Moya</div>' +
      '<p dir="auto" class="break-words streamdown-first-block:mt-0" style="white-space:pre-wrap">' +
        wordSpans +
      "</p>" +
      '<p dir="auto" class="break-words streamdown-first-block:mt-0">' +
        "<span>Second</span><span> </span><span>paragraph</span><span> </span><span>here</span>" +
      "</p>" +
      "<ul>" +
        '<li><p dir="auto" class="streamdown-first-block:mt-0"><span>First</span> <span>item</span></p></li>' +
        '<li><p dir="auto" class="streamdown-first-block:mt-0"><span>Second</span> <span>item</span></p></li>' +
      "</ul>" +
      '<p dir="auto" class="streamdown-first-block:mt-0">' +
        '<span>See</span> <a href="https://example.com/secret-path"><span>the</span> <span>notes</span></a> ' +
        "<span>**please**</span>" +
      "</p>" +
    "</div>"
  );
  const reply = window.document.getElementById("reply");
  const speech = window.GrokVoice.replySpeech(reply);
  assert.equal(
    speech,
    "I've also started building the shared workflow piece. It goes in switch. Second paragraph here. First item. Second item. See the notes please"
  );
  assert.equal(speech.includes("I'vealso"), false);
  assert.equal(speech.includes("piece.It"), false);
  assert.equal(speech.includes("Moya"), false);
  assert.equal(speech.includes("example.com"), false);
  assert.equal(speech.includes("*"), false);
  window.close();
});

test("flex word chips with no space characters are still spaced", () => {
  const window = loadPage(
    '<p id="line" dir="auto" class="streamdown-first-block:mt-0" style="display:flex;flex-wrap:wrap;white-space:pre-wrap">' +
      "<span>I've</span><span>also</span><span>started</span>" +
    "</p>"
  );
  const speech = window.GrokVoice.visibleSpeech(window.document.getElementById("line"));
  assert.equal(speech, "I've also started");
  window.close();
});

// Pages the extension may read. Copy this same array into manifest.json
// under host_permissions and content_scripts[0].matches. npm test fails
// if the three copies drift.
//
// https://grok.com/* covers grok.com/bot/<id>. Paths narrower than /* cannot
// be used together with match_origin_as_fallback, which is what lets the
// script run in about:blank and srcdoc frames.
// Chrome ignores the path on a host permission and grants the whole host.
// Do not add https://x.com/* unless the extension should read all of X.
//
// Reply detection does not depend on a data-testid. Streamdown blocks
// (class names containing STREAMDOWN_MARK) are the primary signal.
// Alignment and color decide user vs assistant when both use Streamdown.
// If a page has no Streamdown markup, the layout fallback is used:
// left / dark-gray bubbles are assistant, right / purple bubbles are yours.
(function (root) {
  "use strict";

  var GV = root.GrokVoice || (root.GrokVoice = {});

  GV.MATCHES = [
    "https://grok.com/*",
    "https://*.grok.com/*",
    "https://x.ai/*",
    "https://*.x.ai/*",
    "https://grok.x.ai/*",
    "https://*.grok.x.ai/*",
    "https://cursor.com/*",
    "https://*.cursor.com/*"
  ];

  // Substring on the renderer class, as in streamdown-first-block:mt-0.
  GV.STREAMDOWN_MARK = "streamdown";

  // Quiet period after the newest reply stops changing, before it is spoken.
  GV.SETTLE_MS = 1500;

  GV.REPO = "chippybrown/voice-reader-for-grokbot";
  GV.UPDATE_INTERVAL_MS = 24 * 60 * 60 * 1000;
  GV.EXTRA_HOSTS = ["https://api.github.com/*"];

  // Shown in hover tooltips. The same chords are suggested in the manifest.
  GV.SHORTCUTS = {
    previous: "Alt+Left",
    playPause: "Alt+Shift+P",
    next: "Alt+Right"
  };

  GV.DEFAULTS = {
    enabled: true,
    voiceURI: "",
    rate: 1,
    debug: false,
    newBotsAutoRead: true,
    betaUpdates: false,
    bots: {}
  };

  GV.clampRate = function clampRate(value) {
    var n = Number(value);
    if (!isFinite(n)) return 1;
    n = Math.round(n * 10) / 10;
    if (n < 0.5) return 0.5;
    if (n > 2) return 2;
    return n;
  };
})(globalThis);

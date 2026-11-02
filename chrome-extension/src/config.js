// Edit this file to match the page Chip actually has open.
//
// MATCHES is the list of pages the extension is allowed to read.
// Copy the same strings into manifest.json in both of these places:
//   host_permissions
//   content_scripts[0].matches
// npm test fails if the three copies drift.
//
// Chrome ignores the path on a host permission and grants the whole site.
// Prefer a Grok host (grok.com, grok.x.ai, or a subdomain). grok.com/* already
// covers every Grok path on that site, including a Grok Bot chat if it is
// served there. Add another host only when that site is a Grok chat.
// Do not add https://x.com/* — that would ask to read all of X. X Chat can
// show the same bots, but there is no separate public host for it yet.
//
// selectors.assistant is tried in order. The first selector that finds any
// element is the one used for the whole page. Put the best bot-reply
// selector first. If none of them match, the content script falls back to
// a heuristic (see selectors.fallbackHints and the note in the README).
//
// How to adjust after looking at the live page:
//   1. Open a Grok chat and inspect one bot reply (right-click, Inspect).
//   2. Find an attribute that is on bot replies and not on your messages.
//   3. Put that CSS selector first in selectors.assistant.
//   4. If the spoken words include buttons or "thinking" text, add a
//      selector for that extra chrome to selectors.skip, or set
//      selectors.content to the inner node that holds only the reply.
//   5. Reload the extension on chrome://extensions, then reload the tab.
(function (root) {
  "use strict";

  var GV = root.GrokVoice || (root.GrokVoice = {});

  GV.MATCHES = [
    "https://grok.com/*",
    "https://*.grok.com/*",
    "https://grok.x.ai/*",
    "https://*.grok.x.ai/*"
  ];

  // Quiet period after the newest reply stops changing, before it is spoken.
  GV.SETTLE_MS = 1500;

  GV.DEFAULTS = {
    enabled: true,
    voiceURI: "",
    rate: 1
  };

  GV.SELECTORS = {
    // Tried in order. First selector that matches at least one node wins.
    assistant: [
      '[data-testid="assistant-message"]',
      '[data-message-author-role="assistant"]',
      '[data-role="assistant"]',
      '[data-author="assistant"]',
      ".response-content-markdown"
    ],
    // Used by the fallback heuristic so a person-side bubble is not read.
    user: [
      '[data-testid="user-message"]',
      '[data-message-author-role="user"]',
      '[data-role="user"]',
      '[data-author="user"]'
    ],
    // First match limits the search. If none match, the whole body is used.
    chatRoot: [
      "main",
      '[data-testid="conversation"]',
      '[data-testid="chat-messages"]'
    ],
    // Inside a bot bubble, prefer the node that holds the reply text.
    content: [
      ".response-content-markdown",
      ".markdown",
      '[data-testid="message-content"]',
      ".prose"
    ],
    // Never read these, even when they sit inside a bot bubble.
    skip: [
      "script",
      "style",
      "noscript",
      "svg",
      "button",
      "textarea",
      "input",
      "select",
      "nav",
      "footer",
      ".thinking-container",
      '[data-testid="thinking"]',
      '[data-testid="canvas-trigger"]',
      ".sr-only",
      ".visually-hidden"
    ],
    // Last-resort hints used only when every assistant selector misses.
    fallbackHints: [
      '[class*="assistant" i]',
      '[class*="bot-message" i]',
      '[class*="model-message" i]',
      '[data-author="assistant"]'
    ]
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

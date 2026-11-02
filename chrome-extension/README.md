# Grok Voice Reader (browser prototype)

A Chrome extension that reads a new Grok reply aloud in the tab you have open. One tab shows one chat, so it does not have to guess which saved chat is on screen.

This is a prototype. It is not part of the desktop app and it is not a release.

It speaks only the visible words of a bot reply that arrives after the page loads, or after you turn the switch on. A reply that is already on the page stays quiet, including one that is still streaming when you turn it on. Your messages stay quiet. Hidden text, link addresses, and markdown marks stay quiet. The same reply is not spoken twice. A streaming reply is spoken after it stops changing for about 1.5 seconds.

Speech uses the browser's built-in `speechSynthesis`. The computer needs a voice installed (Chrome and Edge use the system voices).

## Install in Chrome

1. Open `chrome://extensions`.
2. Turn on **Developer mode**.
3. Click **Load unpacked**.
4. Choose this `chrome-extension` folder (the folder that contains `manifest.json`).

The toolbar icon shows **ON** when the switch is on and the active tab is a Grok page. Open the icon for the switch, voice, rate, **Stop**, and **Replay last**. Those choices are kept in `chrome.storage`.

After you reload the extension, reload the Grok tab too. Chrome does not reinject a content script into a tab that is already open.

## Install in Edge

1. Open `edge://extensions`.
2. Turn on **Developer mode**.
3. Click **Load unpacked**.
4. Choose this same `chrome-extension` folder.

Edge uses the same Manifest V3 package. The **ON** badge, popup, and voices work the same way.

## Which pages it runs on

The list is `GrokVoice.MATCHES` in `src/config.js`:

- `https://grok.com/*` and `https://*.grok.com/*`
- `https://grok.x.ai/*` and `https://*.grok.x.ai/*` (older Grok web host)

`grok.com/*` already includes every path on that site. A Grok Bot chat page on `grok.com` is covered. There is no separate public host for Grok Bot web chat yet (the desktop and phone apps are the main way in; X Chat on x.com can show the same bots). To add a host, put the match pattern in `src/config.js` and copy that same array into `manifest.json` under `host_permissions` and `content_scripts[0].matches`. Then reload the extension.

Chrome ignores the path on a host permission and grants the whole site. Prefer a Grok host. Do not add `https://x.com/*` unless you mean for the extension to read all of X.

`npm test` checks that the three copies of the list match, and that the only API permissions are `storage` and `activeTab`.

## If it reads the wrong part of the page

The live page was not available while this was written, so the selectors are defaults plus a fallback. They live in `GrokVoice.SELECTORS` in `src/config.js`. That file has the edit steps. Short version:

1. Open a Grok chat. Right-click a bot reply and choose **Inspect**.
2. Find an attribute that is on bot replies and not on your messages. `data-testid="assistant-message"` is the usual one on grok.com.
3. Put that CSS selector first in `selectors.assistant`. The first selector that finds anything is the one used for the whole page.
4. If the voice says button labels or "thinking" text, add a selector for that extra piece to `selectors.skip`, or point `selectors.content` at the inner node that holds only the reply (often `.response-content-markdown`).
5. Reload the extension, then reload the tab.

If none of the assistant selectors match, the script guesses: it looks for assistant-like class names, then for article-shaped blocks that are not your message and not the composer. Treat that as a hint that the selector list needs an update. It can pick the wrong block.

`SETTLE_MS` in the same file is the quiet gap (1500). Raise it if a slow stream is being read in pieces.

## What the buttons do

- **Read new replies aloud** turns watching on or off. Turning it on does not read what is already on the page.
- **Voice** and **Rate** are stored for next time. Rate runs from 0.5 to 2.
- **Stop** stops the current speech and drops a reply that was waiting out the quiet gap.
- **Replay last** speaks the last reply again, on purpose.

## Test page

`test/fixture.html` is a static chat. It has an old reply, hidden replies, and a button that streams one new bot reply (with a link and some markdown). The extension does not run on a `file://` page. The automated test loads the extension and serves this file at `https://grok.com/voice-reader-fixture`.

From this folder, with Chrome or Chromium installed (`CHROME_PATH` if it is not `/usr/bin/google-chrome`):

```bash
npm install
npm test
```

The browser test stubs `speechSynthesis` and checks that the newest reply is handed to `speak` exactly once, and that the old reply, the new question, the hidden text, the link address, and the markdown marks are not.

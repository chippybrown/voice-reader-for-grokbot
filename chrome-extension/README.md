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

The toolbar icon shows **ON** when the switch is on and the active tab is a Grok page, including `https://grok.com/bot/<id>`. Open the icon for the switch, **Show what it detects**, voice, rate, **Stop**, and **Replay last**. Those choices are kept in `chrome.storage`.

**Show what it detects** outlines the bottom-most assistant body in green. With that on, the page console logs `[GrokVoice]` after each look: how many Streamdown blocks were found, how many groups, the first 60 characters chosen, and why speech was skipped or started. The popup status shows the same count and snippet.

After you reload the extension, reload the Grok tab too. Chrome does not reinject a content script into a tab that is already open. The badge can show **ON** from the address alone before that reload. If the popup says to reload the tab, do that. A missing content script is ignored instead of logging a connection error.

## Install in Edge

1. Open `edge://extensions`.
2. Turn on **Developer mode**.
3. Click **Load unpacked**.
4. Choose this same `chrome-extension` folder.
5. Reload the Grok tab.

Edge uses this same Manifest V3 package. The toolbar badge, popup, and voices work the same way. It stays on APIs Edge supports: `storage`, `activeTab`, `action`, `tabs`, `runtime`, plus the page `speechSynthesis` and `MutationObserver`. There are no Chrome-only APIs.

## Which pages it runs on

The list is `GrokVoice.MATCHES` in `src/config.js`:

- `https://grok.com/bot/*` for a Grok Bot web chat (`grok.com/bot/<id>`)
- `https://grok.com/*` and `https://*.grok.com/*`
- `https://grok.x.ai/*` and `https://*.grok.x.ai/*` (older Grok web host)

To add a host, put the match pattern in `src/config.js` and copy that same array into `manifest.json` under `host_permissions` and `content_scripts[0].matches`. Then reload the extension.

Chrome ignores the path on a host permission and grants the whole site. Prefer a Grok host. Do not add `https://x.com/*` unless you mean for the extension to read all of X.

`npm test` checks that the three copies of the list match, and that the only API permissions are `storage` and `activeTab`.

## How a reply is chosen

The content script runs in every frame of a Grok, xAI, or Cursor page, including `about:blank` and `srcdoc` frames opened by that page. It also looks inside open shadow roots. The popup lists each frame’s address and how many replies that frame found.

This build is **0.1.2**. The popup shows that version beside the title.

Assistant text on grok.com is rendered by Streamdown. The reader uses only those blocks: a `p` with `dir="auto"` whose class contains `streamdown` (for example `streamdown-first-block:mt-0`), plus any list, heading, or table in that same markdown box. The bot name above the reply, the time, and the buttons are not part of that box, so they are not spoken. Several blocks in one box are one reply. A new or changed message is spoken after its text stays still for about 1.5 seconds, and only once.

Your own bubbles are left out even when they use Streamdown. A bubble counts as yours when it is purple, right-aligned (`justify-content: flex-end`, or sitting on the right side of the thread), or marked with a user role or label. The input box, menus, and tooltips are ignored.

Chrome sometimes blocks `speechSynthesis` until the page has been clicked or typed in. When that happens the reply is kept and spoken on the next click or keypress in the tab.

`STREAMDOWN_MARK` and `SETTLE_MS` are in `src/config.js`. The quiet gap is 1.5 seconds. Raise it if a slow stream is read in pieces.

## What the buttons do

- **Read new replies aloud** turns watching on or off. Turning it on does not read what is already on the page.
- **Show what it detects** outlines the latest assistant bubble and logs its path. It does not change what is spoken.
- **Voice** and **Rate** are stored for next time. Rate runs from 0.5 to 2.
- **Stop** stops the current speech and drops a reply that was waiting out the quiet gap.
- **Replay last** speaks the last reply again, on purpose.

## Test page

`test/fixture.html` is a static chat in the grok.com/bot shape: Streamdown paragraphs, left gray assistant bubbles, and right purple user bubbles that also use Streamdown. It has an old reply, hidden replies, a menu, a tooltip, and a button that streams one new bot reply (two paragraphs, a link, and some markdown). The extension does not run on a `file://` page. The automated test loads the extension and serves this file at `https://grok.com/voice-reader-fixture`.

From this folder, with Chrome or Chromium installed (`CHROME_PATH` if it is not `/usr/bin/google-chrome`):

```bash
npm install
npm test
```

The browser test stubs `speechSynthesis` and checks that the newest reply is handed to `speak` exactly once, and that the old reply, the new question, the hidden text, the link address, and the markdown marks are not.

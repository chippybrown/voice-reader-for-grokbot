# Grok Voice Reader

A browser add-on that reads a new Grok reply out loud. It works in the tab you have open, including a Grok Bot chat at grok.com/bot. This build is **0.2.3**. The popup shows that number next to the title.

You need Chrome, Edge, or Brave, and a speech voice already installed on the computer. Those browsers use the voices that come with Windows or macOS. In Edge, Jenny Online (Natural) is one of those voices.

## Download

1. Download [Grok-Voice-Reader-Extension.zip](https://github.com/chippybrown/voice-reader-for-grokbot/releases/download/ext-v0.2.3/Grok-Voice-Reader-Extension.zip) from the [0.2.3 release](https://github.com/chippybrown/voice-reader-for-grokbot/releases/tag/ext-v0.2.3). On Windows you can instead run [Grok-Voice-Reader-Setup.exe](https://github.com/chippybrown/voice-reader-for-grokbot/releases/download/ext-v0.2.3/Grok-Voice-Reader-Setup.exe), which copies the files to `%LOCALAPPDATA%\Grok Voice Reader\extension`. On Linux, run [Grok-Voice-Reader-x86_64.AppImage](https://github.com/chippybrown/voice-reader-for-grokbot/releases/download/ext-v0.2.3/Grok-Voice-Reader-x86_64.AppImage), which copies them to `~/.local/share/grok-voice-reader/extension`.
2. Unzip it. On Windows, right-click the zip and choose **Extract All**. On a Mac, double-click the zip.
3. Put the unzipped folder somewhere you will not delete, such as **Documents**. The folder must contain a file named `manifest.json`.

Leave that folder where it is. The browser loads the extension from that place. If you move or delete the folder, the extension stops working.

## Install in Chrome

1. Open Chrome and go to `chrome://extensions`.
2. Turn on **Developer mode**. The switch is in the top right.
3. Click **Load unpacked**.
4. Choose the unzipped folder (the one that contains `manifest.json`).
5. Pin it so you can find it later. Click the puzzle-piece icon on the toolbar, find **Grok Voice Reader**, and click the pin.

## Install in Edge

1. Open Edge and go to `edge://extensions`.
2. Turn on **Developer mode**. The switch is at the bottom of the left side.
3. Click **Load unpacked**.
4. Choose the same unzipped folder.
5. Pin it. Click the puzzle-piece icon (or the eye icon) on the toolbar, find **Grok Voice Reader**, and turn the pin on.

## Install in Brave

1. Download [Grok-Voice-Reader-Extension.zip](https://github.com/chippybrown/voice-reader-for-grokbot/releases/download/ext-v0.2.3/Grok-Voice-Reader-Extension.zip) and unzip it. The unzipped folder must contain `manifest.json`. On Windows or Linux, the installer already put that folder in `%LOCALAPPDATA%\Grok Voice Reader\extension` or `~/.local/share/grok-voice-reader/extension`.
2. Open Brave and go to `brave://extensions`.
3. Turn on **Developer mode**.
4. Click **Load unpacked**.
5. Choose the unzipped folder.
6. Refresh the Grok tab. The extension does not attach to a tab that was already open.

## First time you use it

1. Open your Grok chat, such as `https://grok.com/bot/…`.
2. Refresh that tab. The extension does not attach to a tab that was already open.
3. Click once anywhere on the page. Chrome, Edge, and Brave sometimes stay quiet until the page has been clicked.
4. The toolbar icon shows **ON** when the tab is a Grok page and reading is turned on.
5. Send a new message. When the reply stops changing for about a second and a half, it is read aloud. Replies that were already on the page stay quiet. Your own messages stay quiet. The bot’s name is not read.

## Voice and speed

1. Click the **Grok Voice Reader** icon.
2. Open **Voice** and pick a voice. If the list only says **Browser default**, your computer may still be loading voices. Close the popup and open it again.
3. Move **Rate**. 1.0 is normal. Lower is slower. The highest is 2.
4. **Stop** stops the voice that is playing.
5. **Replay last** reads the last reply again.

Those choices are remembered.

**Show what it detects** is off. Leave it off unless a reply is not being read. When it is on, the latest reply is outlined in green, and the page console (press F12, then **Console**) prints lines that start with `[GrokVoice]`.

## Update

1. Download the new zip and unzip it.
2. Replace the contents of the folder the browser is already using. Do not load a second copy.
3. Open `chrome://extensions`, `edge://extensions`, or `brave://extensions`.
4. Click **Reload** on Grok Voice Reader. The circular arrow is on the extension card.
5. Refresh the Grok tab, and click the page once.

## If nothing is read

- Refresh the Grok tab after you load or reload the extension.
- Click the page once.
- Open the extension popup. It lists each frame and how many replies it found. A count of zero means that frame cannot see the chat.
- Turn on **Read new replies aloud** if it is off.

## For developers

From this folder, with Chrome or Chromium installed (`CHROME_PATH` if it is not `/usr/bin/google-chrome`):

```bash
npm install
npm test
```

URL patterns live in `src/config.js` and must match `manifest.json`. A release tag named `ext-v<version>` (for example `ext-v0.2.3`) builds `Grok-Voice-Reader-Extension.zip` and publishes it. That tag does not publish the desktop app, and it is not marked Latest. The desktop updater uses `/releases/latest`. Point the download button at the top of the main README at the new zip when you publish.

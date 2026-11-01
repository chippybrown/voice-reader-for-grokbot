# Grokbot Voice

Download [Grokbot Voice.exe](https://github.com/chippybrown/voice-reader-for-grokbot/releases) from the Releases page, put it on your desktop, and double-click to run.

A small Windows app for people who'd rather listen than read.

Grokbot Voice sits on your screen as a little always-on-top toolbar. It watches the Grok Bot desktop app, and when a bot writes a new reply, it reads that reply aloud. Bot names and timestamps are skipped, so you hear the reply itself. You can use that bot's own Grok voice, a natural offline Piper voice, or a built-in Windows voice.

![The Grokbot Voice toolbar: Back, Stop, Pause, Resume, Next, a green Watching light, and the gear and power buttons](docs/toolbar.png)

## What you need

Grokbot Voice works with the Grok Bot desktop app on Windows.

## Install

1. On the [Releases](https://github.com/chippybrown/voice-reader-for-grokbot/releases) page, download `Grokbot Voice.exe` and put it on your desktop.
2. Double-click it. Windows SmartScreen may warn you, because the app is not code-signed yet. Click **More info**, then **Run anyway**.
3. The toolbar starts in the lower right of the screen. Drag it anywhere you like. It stays above your other windows.

## Voices

**Windows voices** (such as David and Zira) can speak as soon as you start. In Settings, open the voice list and choose **Get More Voices** to add more in Windows speech settings.

**Piper voices** sound more natural and run on your computer. After a voice is downloaded, no internet is needed to use it.

1. Open the voice list at <https://huggingface.co/rhasspy/piper-voices>.
2. Download both files for the voice you want: the `.onnx` file and the matching `.onnx.json` file.
3. Put those two files here (create the folders if they are not there yet):

   `%APPDATA%\Grok Voice\piper`

   Paste that path into the File Explorer address bar. It usually opens something like `C:\Users\YourName\AppData\Roaming\Grok Voice\piper`.
4. Restart Grokbot Voice. The new voice shows up in Settings.

Jenny is an easy first voice: `en_GB-jenny_dioco-medium.onnx` and `en_GB-jenny_dioco-medium.onnx.json`. The same pair of files works for other voices, such as Amy, Lessac, and LJ Speech.

**Grok voice (optional).** This uses the chief-of-staff bot's voice from the Grok Bot app. That bot is Moya unless you name a different one. The words are spoken by xAI's text-to-speech service. The steps are in the next section.

## Getting your xAI API key (for the Grok voice)

You only need this if you want the Grok voice. Windows and Piper voices work with no key at all.

1. Sign in at [console.x.ai](https://console.x.ai) with an X account or an xAI account.
2. Open **Billing** and add credits. This is separate from any Grok or X subscription. Speech costs roughly $15 per 1 million characters, about a penny per reply.
3. Open **API Keys**, create an API key, and copy it.
4. In Grokbot Voice, open the gear, click the voice name, and choose **Set xAI API key...**. Paste the key and click **Save**.

The key is saved encrypted for your Windows account only (Windows DPAPI). You do not have to paste it again.

If the key has no credits, or it hits its spending limit, Grokbot Voice quietly reads that reply with a free local voice instead. The same thing happens if you are offline or xAI reports any other error. It tries Jenny when that Piper voice is installed, then any other Piper voice you added. The next reply tries the Grok voice again. A Windows voice is there whenever you pick one in Settings.

## The buttons

The buttons stay quiet. Only **Test** in Settings speaks. Everything else just does its job.

- **Back** reads the previous reply. Press it again to go further back.
- **Stop** stops the reading that is playing now.
- **Pause** pauses in the middle of the reply and remembers the spot.
- **Resume** continues from that spot.
- **Next** steps forward through earlier replies. On the newest reply, Next stops and waits for the next new one.
- **Gear** opens Settings. Choose a voice, then set its speed and pitch. Each voice remembers its own settings. The Grok voice uses the speed (xAI keeps it in a comfortable range). Pitch applies to Windows and Piper voices. **Test** plays a short sample, **Reset** puts that voice back to normal, and **Done** closes the panel. Open the voice list there and choose **Set xAI API key...** when you want the Grok voice.
- **Status light** is green for Watching, blue for Reading, and yellow for Paused.
- **Turn off** is the red button in the top right. It closes Grokbot Voice.

When you switch to another chat or another bot, reading stops and only the bottom reply of that chat is read. **Back** steps up from there.

## Keyboard shortcuts

These work from any window:

- `Ctrl+Alt+S` stops reading
- `Ctrl+Alt+P` pauses or resumes
- `Ctrl+Alt+Q` quits

## Where settings are saved

Your choices are stored under `%APPDATA%` (usually `C:\Users\YourName\AppData\Roaming`):

- `%APPDATA%\Grok Reader voice.txt` remembers the voice you picked
- `%APPDATA%\Grok Voice\voice settings.json` remembers speed and pitch for each voice
- `%APPDATA%\Grok Voice\piper` is where Piper voice files go
- `%APPDATA%\Grok Voice\xai key.bin` is your xAI API key, encrypted for your Windows account
- `%APPDATA%\Grok Voice\chief of staff.txt` is optional. Put a bot's name on the first line if the chief of staff should be someone other than Moya

## Build from source

On Windows, with Python 3.12:

```bat
pip install -r requirements.txt
pyinstaller --noconfirm --onefile --noconsole --name "Grokbot Voice" --icon grokbot_voice.ico --add-data "grokbot_voice.ico;." --collect-all uiautomation --collect-all piper --collect-all onnxruntime --hidden-import comtypes.stream grok_voice.py
```

The program is written to `dist\Grokbot Voice.exe`.

Pushing a version tag such as `v1.0.0` runs that same build on GitHub and attaches `Grokbot Voice.exe` to the release. You can also start the workflow by hand from the Actions tab.

## License

Grokbot Voice is free software under the [GNU General Public License v3.0](LICENSE). Piper TTS, which this app uses for the natural voices, is GPL software too, which is why this project uses GPL-3.0.

## Disclaimer

This is an independent hobby project. It is not made by or affiliated with xAI. Grok is a trademark of xAI.

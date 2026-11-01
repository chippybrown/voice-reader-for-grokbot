# Grok Voice

A small Windows app for people who'd rather listen than read.

Grok Voice sits on your screen as a little always-on-top toolbar. It watches the Grok Bot desktop app, and when the bot writes a new reply, it reads that reply aloud. You can use natural-sounding offline Piper voices, or the built-in Windows voices David and Zira.

![The Grok Voice toolbar: Back, Stop, Pause, Resume, Next, the Jenny voice, a green Watching light, and the gear and power buttons](docs/toolbar.png)

## What you need

Grok Voice currently works with the Grok Bot desktop app on Windows only. Browser support may come later.

## Install

1. Open [Releases](https://github.com/chippybrown/voice-reader-for-grokbot/releases) and download `Grok Voice.exe`.
2. Windows SmartScreen may warn you, because the app is not code-signed yet. Click **More info**, then **Run anyway**.
3. The toolbar starts in the lower right of the screen. Drag it anywhere you like. It stays above your other windows.

## Add natural voices

David and Zira (the usual Windows voices) can speak as soon as you start the app. Piper voices sound more natural, and they run on your computer. After you download a voice, no internet is needed to use it.

1. Open the voice list at <https://huggingface.co/rhasspy/piper-voices>.
2. Download both files for the voice you want: the `.onnx` file and the matching `.onnx.json` file.
3. Put those two files in this folder (create the folders if they are not there yet):

   `%APPDATA%\Grok Voice\piper`

   Paste that path into the File Explorer address bar. It usually opens something like `C:\Users\YourName\AppData\Roaming\Grok Voice\piper`.
4. Restart Grok Voice. The new voice appears in the voice picker.

These are the voices it was set up with. Download the `.onnx` and `.onnx.json` pair for each one you want:

**English, United States**

| Voice | Files start with |
| --- | --- |
| Amy, medium | `en_US-amy-medium` |
| Amy, low | `en_US-amy-low` |
| Lessac, medium | `en_US-lessac-medium` |
| HFC Female, medium | `en_US-hfc_female-medium` |
| Kristin, medium | `en_US-kristin-medium` |
| Kathleen, low | `en_US-kathleen-low` |
| LJ Speech, high | `en_US-ljspeech-high` |

**English, Great Britain**

| Voice | Files start with |
| --- | --- |
| Alba, medium | `en_GB-alba-medium` |
| Cori, high | `en_GB-cori-high` |
| Jenny, medium | `en_GB-jenny_dioco-medium` |
| Southern English Female, low | `en_GB-southern_english_female-low` |

For Amy medium, the two files are `en_US-amy-medium.onnx` and `en_US-amy-medium.onnx.json`. The other voices follow the same pattern.

## The buttons

- **Back** reads the previous reply. Press it again to go further back.
- **Stop** stops the reading that is playing now.
- **Pause** pauses.
- **Resume** starts again.
- **Next** steps forward through earlier replies. If you are already on the newest reply, Next stops the current reading and waits for the next new one.
- **Gear** (top right, next to the red button) opens Speed and Pitch sliders. Each voice remembers its own speed and pitch. **Test** plays a short sample, **Reset** puts that voice back to normal speed and pitch, and **Done** closes the panel.
- **Voice picker** is the rounded button with the current voice name (for example, Jenny). Click it to switch voices. **Get More Voices** in that menu opens Windows speech settings, where you can add more built-in Windows voices.
- **Status light** is green for Watching, blue for Reading, and yellow for Paused.
- **Turn Off** is the red button in the top right. It closes Grok Voice.

## Keyboard shortcuts

These work from any window:

- `Ctrl+Alt+S` stops reading
- `Ctrl+Alt+P` pauses or resumes
- `Ctrl+Alt+Q` quits

## Where settings are saved

Your choices are stored under `%APPDATA%` (usually `C:\Users\YourName\AppData\Roaming`):

- `%APPDATA%\Grok Reader voice.txt` remembers the voice you picked
- `%APPDATA%\Grok Voice\voice settings.json` remembers speed and pitch for each voice
- `%APPDATA%\Grok Voice\piper` is where you put Piper voice files

## Build from source

On Windows, with Python 3.12:

```bat
pip install -r requirements.txt
pyinstaller --noconfirm --onefile --noconsole --name "Grok Voice" --collect-all uiautomation --collect-all piper --collect-all onnxruntime --hidden-import comtypes.stream grok_voice.py
```

The program is written to `dist\Grok Voice.exe`.

Pushing a version tag such as `v1.0.0` runs that same build on GitHub and attaches `Grok Voice.exe` to the release. You can also start the workflow by hand from the Actions tab.

## License

Grok Voice is free software under the [GNU General Public License v3.0](LICENSE). Piper TTS, which this app uses for the natural voices, is GPL software too, which is why this project uses GPL-3.0.

## Disclaimer

This is an independent hobby project. It is not made by or affiliated with xAI. Grok is a trademark of xAI.

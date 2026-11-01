# Grokbot Voice

Download [Grokbot Voice.exe](https://github.com/chippybrown/voice-reader-for-grokbot/releases) from the Releases page, put it on your desktop, and double-click to run.

A small app for people who'd rather listen than read. It runs on Windows and on Linux Mint.

Grokbot Voice sits on your screen as a little always-on-top toolbar. It watches the Grok Bot desktop app, and when a bot writes a new reply, it reads that reply aloud. Bot names and timestamps are skipped, so you hear the reply itself. You can use that bot's own Grok voice, a natural offline Piper voice, or a built-in voice (Windows voices, or espeak-ng on Linux).

![The Grokbot Voice toolbar: Back, Stop, Pause, Play, Next, a green Watching light, and the gear and power buttons](docs/toolbar.png)

## What you need

On Windows, Grokbot Voice works with the Grok Bot desktop app.

On Linux Mint, install the Grok Bot desktop app as well. Grokbot Voice reads that app's saved chats. The Linux steps are in [Linux Mint](#linux-mint) below.

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

On Windows the key is saved encrypted for your Windows account only (Windows DPAPI). On Linux it is saved in your login keyring. You do not have to paste it again.

If the key has no credits, or it hits its spending limit, Grokbot Voice quietly reads that reply with a free local voice instead. The same thing happens if you are offline or xAI reports any other error. It tries Jenny when that Piper voice is installed, then any other Piper voice you added. The next reply tries the Grok voice again. A Windows voice is there whenever you pick one in Settings.

## The buttons

The buttons stay quiet. Only **Test** in Settings speaks. Everything else just does its job.

- **Back** reads the previous reply. Press it again to go further back.
- **Stop** stops the reply that is playing and stops monitoring. The Stop button turns red, and the status says **Not monitoring**.
- **Pause** holds in the middle of the reply and remembers the spot. The Pause button turns amber, and the status says **Reading paused**.
- **Play** is the green button. After Stop, it starts monitoring again. Replies that arrived while monitoring was off are skipped. After Pause, Play continues from the spot where reading held.
- **Next** steps forward through earlier replies. On the newest reply, Next stops and waits for the next new one.
- **Gear** opens Settings. The default voice has its own speed and pitch. Each voice remembers those. Below that, every bot that has been seen has a checkbox, a voice, and its own speed and pitch. A bot with no voice picked uses the default voice. Uncheck a bot and its new replies stay quiet, even in the open chat. **Back**, **Next**, and **Play** still speak that bot. **New bots on by default** is on, so a bot you have not set yet is read aloud. The Grok voice uses the speed (xAI keeps it in a comfortable range). Pitch applies to Windows and Piper voices. **Test** plays a short sample of the default voice, **Reset** puts that voice back to normal, and **Done** closes the panel. Open the voice list there and choose **Set xAI API key...** when you want the Grok voice. Hover any toolbar button for a short description. Stop, Pause, and Turn off include their keyboard shortcut.
- **Status light** is green for Watching, blue for Reading, amber for Reading paused, and red for Not monitoring.
- **Turn off** is the red button in the top right. It closes Grokbot Voice.

When Grokbot Voice starts, or starts again, replies already in the chat stay quiet. Only a reply that arrives after launch is read. **Back** and **Next** still move through the earlier ones. Notes a bot sends to another agent are never read.

On Linux, opening a different saved chat stays quiet the same way, until a new reply arrives in that chat. On Windows, switching to another chat reads only the bottom reply, and **Back** steps up from there.

## Keyboard shortcuts

These work from any window:

- `Ctrl+Alt+S` stops reading and stops monitoring
- `Ctrl+Alt+P` pauses, or continues from the paused spot
- `Ctrl+Alt+Q` quits

On Linux these shortcuts use the normal keyboard and do not need an administrator password. Linux Mint Cinnamon uses X11, where they work. On a Wayland session they usually do not, and the on-screen buttons still do.

## Where settings are saved

Your choices are stored under `%APPDATA%` (usually `C:\Users\YourName\AppData\Roaming`):

- `%APPDATA%\Grok Reader voice.txt` remembers the voice you picked
- `%APPDATA%\Grok Voice\voice settings.json` remembers speed and pitch for each voice
- `%APPDATA%\Grok Voice\bot settings.json` remembers each bot's voice, speed, pitch, and whether it is read aloud
- `%APPDATA%\Grok Voice\piper` is where Piper voice files go
- `%APPDATA%\Grok Voice\xai key.bin` is your xAI API key, encrypted for your Windows account
- `%APPDATA%\Grok Voice\chief of staff.txt` is optional. Put a bot's name on the first line if the chief of staff should be someone other than Moya

On Linux the same settings live in `~/.config/grokbot-voice/` (voice choice, speed and pitch, per-bot voices, Piper models, and the optional chief-of-staff name). The xAI key is in the login keyring, not in that folder. See [Linux Mint](#linux-mint).

The bar and Settings show the version from `version.py`. This build is **Grokbot Voice v1.3.0**.

## Build from source

On Windows, with Python 3.12:

```bat
pip install -r requirements.txt
pyinstaller --noconfirm --onefile --noconsole --name "Grokbot Voice" --icon grokbot_voice.ico --add-data "grokbot_voice.ico;." --collect-all uiautomation --collect-all piper --collect-all onnxruntime --hidden-import comtypes.stream --hidden-import platform_win --hidden-import grok_store --hidden-import audio_util --hidden-import version --hidden-import bot_prefs grok_voice.py
```

The program is written to `dist\Grokbot Voice.exe`.

On Linux the matching build is in [Linux Mint](#linux-mint). A version tag also builds `Grokbot-Voice-x86_64.AppImage` and `grokbot-voice-linux-x86_64` on Ubuntu 22.04.

Pushing a version tag such as `v1.3.0` runs that same build on GitHub and attaches `Grokbot Voice.exe` to the release, plus the Linux files. The release name is taken from `version.py`. You can also start the workflow by hand from the Actions tab.

## Linux Mint

The short way is one command. Paste it in a terminal. An administrator gets everything: the system packages, the app, a menu entry, a desktop icon, and Piper with the Jenny, Amy, and Lessac voices. Run it again any time to update. It asks before turning on start-at-login, and the answer is No if there is no terminal.

```bash
curl -fsSL https://raw.githubusercontent.com/chippybrown/voice-reader-for-grokbot/cursor/linux-mint-port-ecad/install-mint.sh | bash
```

If you are not an administrator and those packages are already installed, the same command skips apt and continues. You can also force that with:

```bash
curl -fsSL https://raw.githubusercontent.com/chippybrown/voice-reader-for-grokbot/cursor/linux-mint-port-ecad/install-mint.sh | bash -s -- --no-apt
```

If something is still missing, it prints the exact `sudo apt-get install` line for an administrator and stops.

To remove the app later:

```bash
bash ~/.local/share/grokbot-voice/install-mint.sh --uninstall
```

That removes the program, the menu entry, and the desktop icon. Your settings, Piper voices, and xAI key stay.

Open the gear to switch voices. On a new install the voice is **Jenny (natural)**. Amy and Lessac are in the same list. espeak-ng is still there if you want it.

Grok Bot itself has a Linux desktop app. Download the **Linux .deb (x64)** from [cursor.com/download/bot](https://cursor.com/download/bot), then install it:

```bash
sudo apt install ./Grok_Bot_*.deb
```

Open Grok Bot once and sign in, so it can save chats on this computer. Grokbot Voice reads those saved chats. It does not read pixels off the screen.

### 1. Install the packages Grokbot Voice needs

Open a terminal and paste:

```bash
sudo apt update
sudo apt install python3 python3-tk python3-pip espeak-ng pulseaudio-utils gnome-keyring libsecret-1-0
```

- `python3-tk` draws the little toolbar.
- `espeak-ng` is the built-in voice, the stand-in for the Windows voices.
- `pulseaudio-utils` provides `paplay`, which plays the sound. If you are on PipeWire and `paplay` is missing, install the package that provides `pw-play` (often `pipewire-bin` or `pipewire`).
- `gnome-keyring` and `libsecret` store the xAI key. Linux Mint Cinnamon starts the keyring when you log in.

### 2. Run Grokbot Voice

On the [Releases](https://github.com/chippybrown/voice-reader-for-grokbot/releases) page, download **Grokbot-Voice-x86_64.AppImage**. It is attached when a version tag is built, the same way the Windows exe is. Then:

```bash
chmod +x Grokbot-Voice-x86_64.AppImage
./Grokbot-Voice-x86_64.AppImage
```

The same toolbar appears. Drag it where you like. There is also a plain binary named `grokbot-voice-linux-x86_64` if you would rather not use an AppImage.

To run from this source folder instead:

```bash
python3 -m pip install -r requirements-linux.txt
python3 grok_voice.py
```

### 3. Piper voices

The installer downloads Piper and three voices into `~/.config/grokbot-voice/piper`: Jenny, Amy, and Lessac. Jenny is selected the first time you start. Open the gear and click the voice name to pick another one. Files that are already there are left alone, so running the installer again does not download them twice.

The Ubuntu package named `piper` is a game-controller tool, not this speech program. The installer does not use that package. You can point at a different Piper program with the `GROKBOT_PIPER` environment variable.

### 4. The xAI key

Use the same gear menu as on Windows: **Set xAI API key...**, paste the key from [console.x.ai](https://console.x.ai), and click **Save**. The key goes into your login keyring (Secret Service), not into a file. Speech is still billed on that xAI account. If the key is missing, out of credits, or xAI returns an error, Grokbot Voice uses Piper when you have it, and otherwise espeak-ng.

### Where the chats are

Grokbot Voice looks for Grok Bot's `sand-client-persistence` folder and follows only the conversation open in the app. It uses a saved selected agent when the files have one, otherwise the bot named in the Grok Bot window title, otherwise the conversation where you wrote most recently. Other bots are ignored, including ones still writing in the background. It checks, in order:

- `GROKBOT_CHAT_DIR`, if you set that variable
- the folder named in `~/.config/grokbot-voice/chat-folder.txt`, if that file exists
- `~/.config/Grok Bot/sand-client-persistence`
- `~/.config/grok-bot/sand-client-persistence`
- `~/.config/Grokbot/sand-client-persistence`
- Flatpak folders under `~/.var/app`
- Snap folders under `~/snap`

A line in `chat-folder.txt` can be the `sand-client-persistence` folder itself, or the `Grok Bot` folder that contains it.

### Keyboard shortcuts on Mint

`Ctrl+Alt+S`, `Ctrl+Alt+P`, and `Ctrl+Alt+Q` work from any window on X11, which is what Linux Mint Cinnamon uses, and they do not ask for a password. On Wayland those global keys usually do nothing. The buttons on the toolbar still work.

### Build a Linux binary yourself

On Ubuntu 22.04 or Linux Mint 21 or newer, with the packages from step 1:

```bash
python3 -m pip install -r requirements-linux.txt
python3 -m PyInstaller --noconfirm --onefile --noconsole --name grokbot-voice \
  --add-data "assets/icon.png:." \
  --hidden-import platform_linux --hidden-import grok_store --hidden-import audio_util \
  --hidden-import version --hidden-import bot_prefs \
  --collect-all keyring --collect-all secretstorage --collect-all pynput \
  grok_voice.py
chmod +x packaging/linux/build-appimage.sh
packaging/linux/build-appimage.sh
```

That writes `dist/grokbot-voice` and, when `appimagetool` is installed, `dist/Grokbot-Voice-x86_64.AppImage`. GitHub builds the same files on Ubuntu 22.04 so they run on Mint.

## License

Grokbot Voice is free software under the [GNU General Public License v3.0](LICENSE). Piper TTS, which this app uses for the natural voices, is GPL software too, which is why this project uses GPL-3.0.

## Disclaimer

This is an independent hobby project. It is not made by or affiliated with xAI. Grok is a trademark of xAI.

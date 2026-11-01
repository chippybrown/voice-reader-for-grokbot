#!/usr/bin/env bash
# One-step install for Grokbot Voice on Linux Mint.
#   curl -fsSL https://raw.githubusercontent.com/chippybrown/voice-reader-for-grokbot/cursor/linux-mint-port-ecad/install-mint.sh | bash
# Run it again to update. Remove it with: bash install-mint.sh --uninstall
set -euo pipefail

REPO_URL="https://github.com/chippybrown/voice-reader-for-grokbot.git"
BRANCH="${GROKBOT_VOICE_BRANCH:-cursor/linux-mint-port-ecad}"
DEST="${HOME}/.local/share/grokbot-voice"
LAUNCHER="${HOME}/.local/bin/grokbot-voice"
MENU_ENTRY="${HOME}/.local/share/applications/grokbot-voice.desktop"
DESKTOP_ENTRY="${HOME}/Desktop/grokbot-voice.desktop"
AUTOSTART_ENTRY="${HOME}/.config/autostart/grokbot-voice.desktop"
DRY=0
UNINSTALL=0

APT_PACKAGES=(
  git
  ca-certificates
  python3
  python3-tk
  python3-pip
  python3-venv
  python3-dev
  build-essential
  pkg-config
  libffi-dev
  portaudio19-dev
  libportaudio2
  espeak-ng
  pulseaudio-utils
  gnome-keyring
  libsecret-1-0
  libglib2.0-bin
)

usage() {
  cat << 'EOF'
Usage: install-mint.sh [--dry-run] [--uninstall]

  Installs Grokbot Voice for the current user. sudo is used only for apt.
  Running it again updates the checkout and the Python packages.

  --dry-run    Print the actions and do not change the system.
  --uninstall  Remove the app, menu entry, and autostart. Settings stay.

  GROKBOT_VOICE_BRANCH   Git branch to install (default: cursor/linux-mint-port-ecad)
EOF
}

say() {
  printf '%s\n' "$*"
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --dry-run) DRY=1 ;;
    --uninstall) UNINSTALL=1 ;;
    -h|--help) usage; exit 0 ;;
    *)
      printf 'Unknown option: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

stop_app() {
  if ! command -v pkill >/dev/null 2>&1; then
    return 0
  fi
  # The pattern is the installed program, not this installer.
  pkill -f "${DEST}/grok_voice.py" >/dev/null 2>&1 || true
}

uninstall_app() {
  say "Removing Grokbot Voice from this account."
  if [ "$DRY" -eq 1 ]; then
    say "dry-run: would stop the app and remove the launcher, menu entry, desktop shortcut, autostart entry, and ${DEST}"
    say "dry-run: would leave ~/.config/grokbot-voice and the keyring entry in place"
    return 0
  fi
  stop_app
  rm -f "$LAUNCHER" "$MENU_ENTRY" "$DESKTOP_ENTRY" "$AUTOSTART_ENTRY"
  if [ -d "$DEST" ]; then
    rm -rf "$DEST"
  fi
  say "Grokbot Voice was removed."
  say "Settings in ~/.config/grokbot-voice and the saved xAI key were left in place."
}

install_apt() {
  say "Installing system packages (sudo is used only for apt)."
  if [ "$DRY" -eq 1 ]; then
    say "dry-run: sudo apt-get update"
    printf 'dry-run: sudo apt-get install -y'
    printf ' %s' "${APT_PACKAGES[@]}"
    printf '\n'
    return 0
  fi
  sudo apt-get update
  sudo apt-get install -y "${APT_PACKAGES[@]}"
}

sync_repo() {
  say "Using branch ${BRANCH}."
  if [ "$DRY" -eq 1 ]; then
    if [ -d "${DEST}/.git" ]; then
      say "dry-run: would update ${DEST} to origin/${BRANCH}"
    else
      say "dry-run: would clone ${REPO_URL} into ${DEST}"
    fi
    return 0
  fi
  mkdir -p "$(dirname "$DEST")"
  if [ -d "${DEST}/.git" ]; then
    git -C "$DEST" fetch origin "$BRANCH"
    git -C "$DEST" checkout -B "$BRANCH" "origin/${BRANCH}"
  elif [ -e "$DEST" ]; then
    printf 'Refusing to replace %s because it is not a Grokbot Voice checkout.\n' "$DEST" >&2
    exit 1
  else
    git clone --branch "$BRANCH" --single-branch "$REPO_URL" "$DEST"
  fi
}

install_python() {
  local venv="${DEST}/.venv"
  say "Installing Python packages into ${venv}."
  if [ "$DRY" -eq 1 ]; then
    say "dry-run: python3 -m venv ${venv}"
    say "dry-run: ${venv}/bin/pip install -r ${DEST}/requirements-linux.txt"
    return 0
  fi
  python3 -m venv "$venv"
  "${venv}/bin/pip" install --upgrade pip
  "${venv}/bin/pip" install -r "${DEST}/requirements-linux.txt"
}

write_desktop_file() {
  local path="$1"
  local autostart="$2"
  cat > "$path" << EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=Grokbot Voice
Comment=Read Grok Bot replies aloud
Exec=${LAUNCHER}
Icon=${DEST}/assets/icon.png
Terminal=false
Categories=Audio;Utility;
StartupNotify=false
EOF
  if [ "$autostart" -eq 1 ]; then
    printf 'X-GNOME-Autostart-enabled=true\n' >> "$path"
  fi
}

install_launchers() {
  say "Adding the menu entry and the grokbot-voice command."
  if [ "$DRY" -eq 1 ]; then
    say "dry-run: would write ${LAUNCHER}"
    say "dry-run: would write ${MENU_ENTRY}"
    if [ -d "${HOME}/Desktop" ]; then
      say "dry-run: would write ${DESKTOP_ENTRY} and mark it trusted"
    else
      say "dry-run: no ~/Desktop folder, so no desktop shortcut"
    fi
    return 0
  fi
  mkdir -p "${HOME}/.local/bin" "${HOME}/.local/share/applications"
  cat > "$LAUNCHER" << EOF
#!/bin/sh
exec "${DEST}/.venv/bin/python" "${DEST}/grok_voice.py"
EOF
  chmod +x "$LAUNCHER"
  write_desktop_file "$MENU_ENTRY" 0
  if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "${HOME}/.local/share/applications" || true
  fi
  if [ -d "${HOME}/Desktop" ]; then
    cp "$MENU_ENTRY" "$DESKTOP_ENTRY"
    chmod +x "$DESKTOP_ENTRY"
    if command -v gio >/dev/null 2>&1; then
      gio set "$DESKTOP_ENTRY" metadata::trusted true || true
    else
      say "Note: gio is not available, so Mint may ask you to trust the desktop icon."
    fi
  fi
  case ":${PATH}:" in
    *":${HOME}/.local/bin:"*) ;;
    *)
      say "Note: ${HOME}/.local/bin is not on PATH yet. The menu entry still works."
      say "Log out and back in, or open a new terminal, before typing grokbot-voice."
      ;;
  esac
}

# yes, no, or skip. skip means there was no terminal, so an existing choice stays.
AUTOSTART_CHOICE="skip"

prompt_autostart() {
  local answer
  AUTOSTART_CHOICE="skip"
  if [ "$DRY" -eq 1 ]; then
    say "dry-run: would ask to start at login (default No when there is no terminal)"
    return 0
  fi
  if [ ! -r /dev/tty ] || [ ! -w /dev/tty ]; then
    if [ -f "$AUTOSTART_ENTRY" ]; then
      say "No terminal to ask about autostart. Leaving the current login setting as it is."
    else
      say "No terminal to ask about autostart. Leaving it off."
    fi
    return 0
  fi
  printf 'Start Grokbot Voice when you log in? [y/N] ' > /dev/tty
  if ! IFS= read -r answer < /dev/tty; then
    printf '\n' > /dev/tty
    say "No answer. Autostart left off."
    AUTOSTART_CHOICE="no"
    return 0
  fi
  case "$answer" in
    y|Y|yes|YES) AUTOSTART_CHOICE="yes" ;;
    *) AUTOSTART_CHOICE="no" ;;
  esac
}

install_autostart() {
  prompt_autostart
  case "$AUTOSTART_CHOICE" in
    yes)
      say "Grokbot Voice will start when you log in."
      if [ "$DRY" -eq 0 ]; then
        mkdir -p "${HOME}/.config/autostart"
        write_desktop_file "$AUTOSTART_ENTRY" 1
      fi
      ;;
    no)
      if [ "$DRY" -eq 0 ] && [ -f "$AUTOSTART_ENTRY" ]; then
        rm -f "$AUTOSTART_ENTRY"
        say "Autostart turned off."
      fi
      ;;
    *) ;;
  esac
}

warn_environment() {
  if [ ! -d "${HOME}/.config/Grok Bot" ]; then
    say "Warning: Grok Bot's folder was not found at ~/.config/Grok Bot."
    say "Install the Linux desktop app and sign in once: https://cursor.com/download/bot"
  fi
  if [ "${XDG_SESSION_TYPE:-}" = "wayland" ]; then
    say "Warning: this is a Wayland session. Keyboard shortcuts may not work. Use the on-screen buttons."
  fi
}

launch_app() {
  say "Set your xAI key from the gear menu"
  if [ "$DRY" -eq 1 ]; then
    say "dry-run: would launch ${LAUNCHER}"
    return 0
  fi
  if command -v setsid >/dev/null 2>&1; then
    setsid "$LAUNCHER" >/dev/null 2>&1 < /dev/null &
  else
    nohup "$LAUNCHER" >/dev/null 2>&1 < /dev/null &
  fi
}

if [ "$UNINSTALL" -eq 1 ]; then
  uninstall_app
  exit 0
fi

install_apt
sync_repo
install_python
install_launchers
install_autostart
warn_environment
launch_app

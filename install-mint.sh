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
NO_APT=0

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
  xdg-utils
  desktop-file-utils
  curl
)

usage() {
  cat << 'EOF'
Usage: install-mint.sh [--dry-run] [--uninstall]

  Installs Grokbot Voice for the current user. sudo is used only for apt.
  Running it again updates the checkout and the Python packages.

  --dry-run    Print the actions and do not change the system.
  --no-apt     Do not install system packages. Use this when they are already installed.
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
    --no-apt) NO_APT=1 ;;
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
  rm -f "$LAUNCHER" "$MENU_ENTRY" "$AUTOSTART_ENTRY" "$DESKTOP_ENTRY"
  rm -f "$(desktop_directory)/grokbot-voice.desktop"
  if [ -d "$DEST" ]; then
    rm -rf "$DEST"
  fi
  say "Grokbot Voice was removed."
  say "Settings in ~/.config/grokbot-voice and the saved xAI key were left in place."
}

# /dev/tty can exist and look readable when this process has no controlling
# terminal. Opening it then fails with "No such device or address".
tty_openable() {
  # A failed redirect prints to the shell's stderr unless the group catches it.
  [ -c /dev/tty ] || return 1
  { : >/dev/tty; } 2>/dev/null || return 1
  { : </dev/tty; } 2>/dev/null || return 1
}

print_admin_packages() {
  say "An administrator needs to install these packages:"
  printf 'sudo apt-get update && sudo apt-get install -y'
  printf ' %s' "${APT_PACKAGES[@]}"
  printf '\n'
}

lib_present() {
  local pattern="$1"
  local cache
  if command -v ldconfig >/dev/null 2>&1; then
    cache="$(ldconfig -p 2>/dev/null || true)"
  elif [ -x /sbin/ldconfig ]; then
    cache="$(/sbin/ldconfig -p 2>/dev/null || true)"
  else
    cache=""
  fi
  if printf '%s\n' "$cache" | grep -F -q "$pattern"; then
    return 0
  fi
  if [ -e "/usr/lib/x86_64-linux-gnu/${pattern}" ] || [ -e "/usr/lib/aarch64-linux-gnu/${pattern}" ]; then
    return 0
  fi
  return 1
}

deps_ready() {
  local missing=0
  if ! command -v git >/dev/null 2>&1; then
    say "  - git"
    missing=1
  fi
  if ! command -v python3 >/dev/null 2>&1; then
    say "  - python3"
    missing=1
  fi
  if ! python3 -c "import tkinter" >/dev/null 2>&1; then
    say "  - python3-tk"
    missing=1
  fi
  if ! python3 -m venv --help >/dev/null 2>&1; then
    say "  - python3-venv"
    missing=1
  fi
  if ! command -v espeak-ng >/dev/null 2>&1 && ! command -v espeak >/dev/null 2>&1; then
    say "  - espeak-ng"
    missing=1
  fi
  if ! command -v paplay >/dev/null 2>&1 && ! command -v pw-play >/dev/null 2>&1 && ! command -v aplay >/dev/null 2>&1; then
    say "  - pulseaudio-utils (paplay, pw-play, or aplay)"
    missing=1
  fi
  if ! command -v gio >/dev/null 2>&1; then
    say "  - libglib2.0-bin (gio)"
    missing=1
  fi
  if ! lib_present "libportaudio.so.2"; then
    say "  - libportaudio2 and portaudio19-dev"
    missing=1
  fi
  if ! lib_present "libsecret-1.so.0"; then
    say "  - libsecret-1-0"
    missing=1
  fi
  return "$missing"
}

can_sudo() {
  command -v sudo >/dev/null 2>&1 || return 1
  if sudo -n true >/dev/null 2>&1; then
    return 0
  fi
  # An admin with a terminal can type a password. A non-admin cannot.
  if ! tty_openable; then
    return 1
  fi
  sudo -v >/dev/null 2>&1
}

install_apt() {
  say "Installing system packages (sudo is used only for apt)."
  if [ "$DRY" -eq 1 ]; then
    if [ "$NO_APT" -eq 1 ]; then
      say "dry-run: would skip apt (--no-apt)"
    else
      say "dry-run: sudo apt-get update"
      printf 'dry-run: sudo apt-get install -y'
      printf ' %s' "${APT_PACKAGES[@]}"
      printf '\n'
    fi
    return 0
  fi
  if [ "$NO_APT" -eq 1 ]; then
    say "Skipping apt (--no-apt)."
    if ! deps_ready; then
      say "Some required programs are still missing."
      print_admin_packages
    fi
    return 0
  fi
  if can_sudo; then
    sudo apt-get update
    sudo apt-get install -y "${APT_PACKAGES[@]}"
    return 0
  fi
  say "No administrator rights for apt."
  if deps_ready; then
    say "The required programs are already installed, so apt was skipped."
    return 0
  fi
  say "These are missing, so the install cannot continue."
  print_admin_packages
  exit 1
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

fetch_file() {
  local url="$1"
  local dest="$2"
  if [ -s "$dest" ]; then
    return 0
  fi
  mkdir -p "$(dirname "$dest")"
  local tmp="${dest}.partial"
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL -o "$tmp" "$url"
  else
    python3 -c 'import sys, urllib.request; urllib.request.urlretrieve(sys.argv[1], sys.argv[2])' "$url" "$tmp"
  fi
  mv "$tmp" "$dest"
}

install_piper() {
  local config="${XDG_CONFIG_HOME:-${HOME}/.config}/grokbot-voice"
  local piper_dir="${config}/piper"
  local arch=""
  case "$(uname -m)" in
    aarch64|arm64) arch="aarch64" ;;
    x86_64|amd64) arch="x86_64" ;;
    *)
      say "No Piper build for $(uname -m). espeak-ng will be used until a voice is added."
      return 0
      ;;
  esac
  say "Installing Piper and the Jenny, Amy, and Lessac voices into ${piper_dir}."
  if [ "$DRY" -eq 1 ]; then
    say "dry-run: would download Piper for ${arch} and the three voices, skipping files already there"
    return 0
  fi
  mkdir -p "$piper_dir"
  if [ ! -x "${piper_dir}/piper" ]; then
    local tar="${config}/piper_linux_${arch}.tar.gz"
    fetch_file "https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_linux_${arch}.tar.gz" "$tar"
    tar -C "$config" -xzf "$tar"
    rm -f "$tar"
    chmod +x "${piper_dir}/piper" || true
  else
    say "Piper is already installed."
  fi
  local base="https://huggingface.co/rhasspy/piper-voices/resolve/main/en"
  local voice name
  for voice in \
    "en_GB/jenny_dioco/medium/en_GB-jenny_dioco-medium" \
    "en_US/amy/medium/en_US-amy-medium" \
    "en_US/lessac/medium/en_US-lessac-medium"
  do
    name="${voice##*/}"
    if [ -s "${piper_dir}/${name}.onnx" ] && [ -s "${piper_dir}/${name}.onnx.json" ]; then
      say "Voice ${name} is already present."
      continue
    fi
    say "Downloading ${name}."
    fetch_file "${base}/${voice}.onnx" "${piper_dir}/${name}.onnx"
    fetch_file "${base}/${voice}.onnx.json" "${piper_dir}/${name}.onnx.json"
  done
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

desktop_directory() {
  local dir=""
  if command -v xdg-user-dir >/dev/null 2>&1; then
    dir="$(xdg-user-dir DESKTOP 2>/dev/null || true)"
  fi
  if [ -z "$dir" ] || [ "$dir" = "$HOME" ]; then
    dir="${HOME}/Desktop"
  fi
  printf '%s\n' "$dir"
}

install_launchers() {
  local desk
  desk="$(desktop_directory)"
  say "Adding the menu entry, the desktop icon, and the grokbot-voice launcher."
  if [ "$DRY" -eq 1 ]; then
    say "dry-run: would write ${LAUNCHER}"
    say "dry-run: would write ${MENU_ENTRY} and update the desktop database"
    say "dry-run: would write ${desk}/grokbot-voice.desktop and mark it trusted"
    return 0
  fi
  mkdir -p "${HOME}/.local/bin" "${HOME}/.local/share/applications" "$desk"
  cat > "$LAUNCHER" << EOF
#!/bin/sh
exec "${DEST}/.venv/bin/python" "${DEST}/grok_voice.py"
EOF
  chmod +x "$LAUNCHER"
  write_desktop_file "$MENU_ENTRY" 0
  if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "${HOME}/.local/share/applications" || true
  else
    say "Note: update-desktop-database is not installed. The menu file is still in place."
  fi
  cp "$MENU_ENTRY" "${desk}/grokbot-voice.desktop"
  chmod +x "${desk}/grokbot-voice.desktop"
  if command -v gio >/dev/null 2>&1; then
    gio set "${desk}/grokbot-voice.desktop" metadata::trusted true || true
  else
    say "Note: gio is not available, so Mint may ask you to trust the desktop icon."
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
  if [ "${CI:-}" = "true" ] || [ "${GROKBOT_VOICE_AUTOSTART:-}" = "0" ]; then
    say "Autostart left off."
    AUTOSTART_CHOICE="no"
    return 0
  fi
  if ! tty_openable; then
    if [ -f "$AUTOSTART_ENTRY" ]; then
      say "No terminal to ask about autostart. Leaving the current login setting as it is."
    else
      say "No terminal to ask about autostart. Leaving it off."
    fi
    return 0
  fi
  if [ "$DRY" -eq 1 ]; then
    say "dry-run: would ask to start at login (default No)"
    return 0
  fi
  if ! printf 'Start Grokbot Voice when you log in? [y/N] ' > /dev/tty; then
    say "No terminal to ask about autostart. Leaving it off."
    return 0
  fi
  if ! IFS= read -r answer < /dev/tty; then
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
install_piper
install_launchers
install_autostart
warn_environment
launch_app

// Copies the extension into a fixed folder and opens a short help page.
// Re-running replaces the files in that same folder.
package main

import (
	"embed"
	"fmt"
	"io/fs"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
)

//go:embed extension/*
var packed embed.FS

func main() {
	dest := destination()
	if err := os.MkdirAll(dest, 0o755); err != nil {
		fmt.Println("Could not create", dest)
		fmt.Println(err)
		os.Exit(1)
	}
	if err := copyExtension(dest); err != nil {
		fmt.Println("Could not copy the extension.")
		fmt.Println(err)
		os.Exit(1)
	}
	help := filepath.Join(dest, "installed.html")
	if err := os.WriteFile(help, []byte(helpPage(dest)), 0o644); err != nil {
		fmt.Println("Could not write the help page.")
		fmt.Println(err)
		os.Exit(1)
	}
	fmt.Println("Grok Voice Reader is in:")
	fmt.Println(dest)
	fmt.Println()
	fmt.Println("1. Open brave://extensions, chrome://extensions, or edge://extensions.")
	fmt.Println("2. Turn on Developer mode, click Load unpacked, and choose the folder above.")
	fmt.Println("3. Refresh the Grok tab. To update later, run this installer again and click Reload.")
	openHelp(help)
	openExtensions()
}

func destination() string {
	if runtime.GOOS == "windows" {
		base := os.Getenv("LOCALAPPDATA")
		if base == "" {
			base = filepath.Join(os.Getenv("USERPROFILE"), "AppData", "Local")
		}
		return filepath.Join(base, "Grok Voice Reader", "extension")
	}
	home, err := os.UserHomeDir()
	if err != nil || home == "" {
		home = "."
	}
	return filepath.Join(home, ".local", "share", "grok-voice-reader", "extension")
}

func copyExtension(dest string) error {
	return fs.WalkDir(packed, "extension", func(path string, entry fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		rel := strings.TrimPrefix(path, "extension")
		rel = strings.TrimPrefix(rel, "/")
		rel = strings.TrimPrefix(rel, "\\")
		target := dest
		if rel != "" {
			target = filepath.Join(dest, filepath.FromSlash(rel))
		}
		if entry.IsDir() {
			return os.MkdirAll(target, 0o755)
		}
		data, err := packed.ReadFile(path)
		if err != nil {
			return err
		}
		return os.WriteFile(target, data, 0o644)
	})
}

func helpPage(dest string) string {
	return "<!DOCTYPE html><html><head><meta charset=\"utf-8\"><title>Grok Voice Reader</title></head><body>" +
		"<h1>Grok Voice Reader is installed</h1><p>The extension folder is:</p><p><code>" + dest + "</code></p>" +
		"<ol><li>Open <code>brave://extensions</code>, <code>chrome://extensions</code>, or <code>edge://extensions</code>.</li>" +
		"<li>Turn on <strong>Developer mode</strong>, click <strong>Load unpacked</strong>, and choose that folder.</li>" +
		"<li>Refresh the Grok tab and click the page once.</li></ol>" +
		"<p>To update, run the installer again, then click <strong>Reload</strong> on the extension.</p></body></html>"
}

func openHelp(path string) {
	if runtime.GOOS == "windows" {
		_ = exec.Command("cmd", "/c", "start", "", path).Start()
		return
	}
	_ = exec.Command("xdg-open", path).Start()
}

func openExtensions() {
	type candidate struct {
		exe  string
		page string
	}
	var list []candidate
	if runtime.GOOS == "windows" {
		local := os.Getenv("LOCALAPPDATA")
		list = []candidate{
			{filepath.Join(local, `BraveSoftware\Brave-Browser\Application\brave.exe`), "brave://extensions"},
			{`C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe`, "brave://extensions"},
			{filepath.Join(local, `Google\Chrome\Application\chrome.exe`), "chrome://extensions"},
			{`C:\Program Files\Google\Chrome\Application\chrome.exe`, "chrome://extensions"},
			{`C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe`, "edge://extensions"},
			{`C:\Program Files\Microsoft\Edge\Application\msedge.exe`, "edge://extensions"},
		}
	} else {
		list = []candidate{
			{"brave-browser", "brave://extensions"},
			{"brave", "brave://extensions"},
			{"google-chrome", "chrome://extensions"},
			{"google-chrome-stable", "chrome://extensions"},
			{"chromium", "chrome://extensions"},
			{"microsoft-edge", "edge://extensions"},
		}
	}
	for _, item := range list {
		exe := item.exe
		if runtime.GOOS != "windows" {
			found, err := exec.LookPath(item.exe)
			if err != nil {
				continue
			}
			exe = found
		} else if _, err := os.Stat(item.exe); err != nil {
			continue
		}
		_ = exec.Command(exe, item.page).Start()
		return
	}
}

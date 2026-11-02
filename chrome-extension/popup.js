/* global GrokVoice */
(function () {
  "use strict";

  var GV = globalThis.GrokVoice;
  var enabledInput = document.getElementById("enabled");
  var debugInput = document.getElementById("debug");
  var voiceSelect = document.getElementById("voice");
  var rateInput = document.getElementById("rate");
  var rateValue = document.getElementById("rate-value");
  var statusNode = document.getElementById("status");
  var saving = false;

  function setStatus(text) {
    statusNode.textContent = text;
  }

  function showRate(value) {
    rateValue.textContent = GV.clampRate(value).toFixed(1);
  }

  function fillVoices(selected) {
    var voices = window.speechSynthesis ? window.speechSynthesis.getVoices() : [];
    var previous = selected || voiceSelect.value;
    voiceSelect.textContent = "";
    var fallback = document.createElement("option");
    fallback.value = "";
    fallback.textContent = "Browser default";
    voiceSelect.appendChild(fallback);
    voices.forEach(function (voice) {
      var option = document.createElement("option");
      option.value = voice.voiceURI;
      option.textContent = voice.name + (voice.lang ? " (" + voice.lang + ")" : "");
      voiceSelect.appendChild(option);
    });
    voiceSelect.value = previous;
    if (voiceSelect.value !== previous) voiceSelect.value = "";
  }

  function askBackground(message) {
    return new Promise(function (resolve) {
      try {
        chrome.runtime.sendMessage(message, function (response) {
          void chrome.runtime.lastError;
          resolve(response || null);
        });
      } catch (err) {
        resolve(null);
      }
    });
  }

  function frameLine(frame) {
    var count = Number(frame.groups) || 0;
    var line = (frame.url || "frame") + " — " + count + (count === 1 ? " reply" : " replies");
    if (frame.snippet) line += ". Last: " + frame.snippet;
    if (frame.mode === "fallback") line += " (no streamdown class)";
    return line;
  }

  function refreshStatus() {
    askBackground({ type: "popup-status" }).then(function (response) {
      if (!response || !response.ok) {
        setStatus("This tab is not a Grok chat.");
        return;
      }
      var lines = [response.enabled ? "On." : "Off."];
      var frames = response.frames || [];
      if (!frames.length) lines.push("0 replies detected. No frame has reported yet.");
      else frames.forEach(function (frame) { lines.push(frameLine(frame)); });
      setStatus(lines.join("\n"));
    });
  }

  function save(partial) {
    saving = true;
    chrome.storage.local.set(partial, function () {
      saving = false;
      refreshStatus();
    });
  }

  enabledInput.addEventListener("change", function () {
    save({ enabled: enabledInput.checked });
  });

  debugInput.addEventListener("change", function () {
    save({ debug: debugInput.checked });
  });

  voiceSelect.addEventListener("change", function () {
    save({ voiceURI: voiceSelect.value });
  });

  rateInput.addEventListener("input", function () {
    showRate(rateInput.value);
    save({ rate: GV.clampRate(rateInput.value) });
  });

  document.getElementById("stop").addEventListener("click", function () {
    askBackground({ type: "broadcast", command: "stop" }).then(function () {
      setStatus("Stopped.");
    });
  });

  document.getElementById("replay").addEventListener("click", function () {
    askBackground({ type: "broadcast", command: "replay" }).then(function (response) {
      if (response && response.text) setStatus("Replaying the last reply.");
      else setStatus("Nothing to replay yet.");
    });
  });

  try {
    document.getElementById("version").textContent = chrome.runtime.getManifest().version;
  } catch (err) {
    document.getElementById("version").textContent = "";
  }

  chrome.storage.local.get(GV.DEFAULTS, function (stored) {
    enabledInput.checked = stored.enabled !== false;
    debugInput.checked = stored.debug === true;
    rateInput.value = String(GV.clampRate(stored.rate));
    showRate(rateInput.value);
    fillVoices(stored.voiceURI || "");
    refreshStatus();
  });

  if (window.speechSynthesis) {
    window.speechSynthesis.addEventListener("voiceschanged", function () {
      if (!saving) fillVoices(voiceSelect.value);
    });
  }
})();

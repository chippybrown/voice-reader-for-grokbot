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

  function activeTab() {
    return chrome.tabs.query({ active: true, currentWindow: true }).then(function (tabs) {
      return tabs[0] || null;
    });
  }

  function send(type) {
    return activeTab().then(function (tab) {
      if (!tab || tab.id == null) return { tab: null, response: null, missing: false };
      return new Promise(function (resolve) {
        try {
          chrome.tabs.sendMessage(tab.id, { type: type }, function (response) {
            var missing = Boolean(chrome.runtime.lastError);
            resolve({
              tab: tab,
              response: missing ? null : (response || null),
              missing: missing
            });
          });
        } catch (err) {
          resolve({ tab: tab, response: null, missing: true });
        }
      });
    }, function () {
      return { tab: null, response: null, missing: true };
    });
  }

  function detectedLine(response) {
    var count = Number(response.detected);
    if (!isFinite(count)) count = 0;
    var line = count === 1 ? "1 reply detected." : count + " replies detected.";
    if (response.snippet) line += " Last: " + response.snippet;
    if (response.reason === "no-streamdown-blocks") line += " No Streamdown text found.";
    else if (response.reason === "historical") line += " Already on the page.";
    else if (response.reason === "waiting") line += " Waiting until it settles.";
    else if (response.reason === "spoke" || response.reason === "already-spoken") line += " Spoken.";
    return line;
  }

  function refreshStatus() {
    send("status").then(function (result) {
      var tab = result.tab;
      var response = result.response;
      var url = tab && tab.url ? tab.url : "";
      if (result.missing && url && GV.urlMatches(url)) {
        setStatus("Reload this Grok tab so reading can start.");
        return;
      }
      if (!response || !response.ok) {
        setStatus("This tab is not a Grok chat.");
        return;
      }
      var prefix = response.enabled ? "On. " : "Off. ";
      setStatus(prefix + detectedLine(response));
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
    send("stop").then(function (result) {
      if (result.missing) setStatus("Nothing is speaking in this tab.");
      else setStatus("Stopped.");
    });
  });

  document.getElementById("replay").addEventListener("click", function () {
    send("replay").then(function (result) {
      if (result.response && result.response.ok) setStatus("Replaying the last reply.");
      else setStatus("Nothing to replay yet.");
    });
  });

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

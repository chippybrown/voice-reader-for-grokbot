/* global GrokVoice */
(function () {
  "use strict";

  var GV = globalThis.GrokVoice;
  var enabledInput = document.getElementById("enabled");
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
      if (!tab || tab.id == null) return null;
      return chrome.tabs.sendMessage(tab.id, { type: type });
    });
  }

  function refreshStatus() {
    send("status").then(function (response) {
      if (!response || !response.ok) {
        setStatus("This tab is not a Grok chat.");
        return;
      }
      if (response.enabled) setStatus("On. A reply already on the page stays quiet.");
      else setStatus("Off. New replies stay quiet.");
    }).catch(function () {
      setStatus("This tab is not a Grok chat.");
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

  voiceSelect.addEventListener("change", function () {
    save({ voiceURI: voiceSelect.value });
  });

  rateInput.addEventListener("input", function () {
    showRate(rateInput.value);
    save({ rate: GV.clampRate(rateInput.value) });
  });

  document.getElementById("stop").addEventListener("click", function () {
    send("stop").then(function () {
      setStatus("Stopped.");
    }).catch(function () {
      setStatus("Nothing is speaking in this tab.");
    });
  });

  document.getElementById("replay").addEventListener("click", function () {
    send("replay").then(function (response) {
      if (response && response.ok) setStatus("Replaying the last reply.");
      else setStatus("Nothing to replay yet.");
    }).catch(function () {
      setStatus("Nothing to replay yet.");
    });
  });

  chrome.storage.local.get(GV.DEFAULTS, function (stored) {
    enabledInput.checked = stored.enabled !== false;
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

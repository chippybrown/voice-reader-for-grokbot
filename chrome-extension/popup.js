/* global GrokVoice */
(function () {
  "use strict";

  var GV = globalThis.GrokVoice;
  var enabledInput = document.getElementById("enabled");
  var debugInput = document.getElementById("debug");
  var voiceSelect = document.getElementById("voice");
  var botVoiceSelect = document.getElementById("bot-voice");
  var botReadInput = document.getElementById("bot-read");
  var newBotsInput = document.getElementById("new-bots");
  var betaInput = document.getElementById("beta");
  var rateInput = document.getElementById("rate");
  var rateValue = document.getElementById("rate-value");
  var statusNode = document.getElementById("status");
  var updateNode = document.getElementById("update");
  var playButton = document.getElementById("play-pause");
  var saving = false;
  var currentBot = { id: "", name: "" };
  var storedBots = {};

  function setStatus(text) {
    statusNode.textContent = text;
  }

  function showRate(value) {
    rateValue.textContent = GV.clampRate(value).toFixed(1);
  }

  function voiceOptions(select, selected, includeDefault) {
    var voices = window.speechSynthesis ? window.speechSynthesis.getVoices() : [];
    var previous = selected != null ? selected : select.value;
    select.textContent = "";
    if (includeDefault) {
      var fallback = document.createElement("option");
      fallback.value = "";
      fallback.textContent = "Browser default";
      select.appendChild(fallback);
    } else {
      var inherit = document.createElement("option");
      inherit.value = "";
      inherit.textContent = "Default voice";
      select.appendChild(inherit);
    }
    voices.forEach(function (voice) {
      var option = document.createElement("option");
      option.value = voice.voiceURI;
      option.textContent = voice.name + (voice.lang ? " (" + voice.lang + ")" : "");
      select.appendChild(option);
    });
    select.value = previous;
    if (select.value !== previous) select.value = "";
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

  function bestFrame(frames) {
    var best = null;
    (frames || []).forEach(function (frame) {
      if (!frame || !frame.botId) return;
      if (!best || Number(frame.groups) > Number(best.groups)) best = frame;
    });
    return best;
  }

  function paintPlay(mode) {
    var playing = mode === "playing";
    playButton.innerHTML = GV.controlIcon(playing ? "pause" : "play");
    var tips = GV.controlTooltips();
    var tip = playing ? tips.pause : tips.play;
    playButton.title = tip;
    playButton.setAttribute("aria-label", tip);
  }

  function showBot(stored) {
    var name = currentBot.name || "this bot";
    document.getElementById("bot-voice-label").textContent = "Voice for " + name;
    document.getElementById("bot-read-label").textContent = "Read " + name + " aloud";
    var record = currentBot.id && storedBots[currentBot.id] ? storedBots[currentBot.id] : null;
    var auto = record ? record.autoRead !== false : stored.newBotsAutoRead !== false;
    botReadInput.checked = auto;
    botReadInput.disabled = !currentBot.id;
    botVoiceSelect.disabled = !currentBot.id;
    voiceOptions(botVoiceSelect, record && record.voiceURI ? record.voiceURI : "", false);
  }

  function showUpdate(notice) {
    updateNode.hidden = !notice || !notice.url;
    updateNode.textContent = "";
    if (!notice || !notice.url) return;
    updateNode.appendChild(document.createTextNode("Update available: " + (notice.version || notice.tag) + ". "));
    var link = document.createElement("a");
    link.href = notice.url;
    link.target = "_blank";
    link.rel = "noopener";
    link.textContent = "Download";
    updateNode.appendChild(link);
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
      var frame = bestFrame(frames);
      currentBot = frame ? { id: frame.botId, name: frame.botName || frame.botId } : { id: "", name: "" };
      var playing = "";
      frames.forEach(function (item) {
        if (item && item.playback) playing = item.playback;
      });
      paintPlay(playing);
      chrome.storage.local.get(GV.DEFAULTS, function (stored) {
        storedBots = stored.bots || {};
        showBot(stored);
        showUpdate(stored.updateNotice);
      });
    });
  }

  function save(partial) {
    saving = true;
    chrome.storage.local.set(partial, function () {
      saving = false;
      refreshStatus();
    });
  }

  function saveBot(partial) {
    if (!currentBot.id) return;
    chrome.storage.local.get(GV.DEFAULTS, function (stored) {
      var bots = GV.rememberBot(stored, { id: currentBot.id, name: currentBot.name || currentBot.id });
      bots[currentBot.id] = Object.assign({}, bots[currentBot.id], partial);
      save({ bots: bots });
    });
  }

  function labelButtons() {
    var tips = GV.controlTooltips();
    var previous = document.getElementById("previous");
    var next = document.getElementById("next");
    previous.innerHTML = GV.controlIcon("previous");
    next.innerHTML = GV.controlIcon("next");
    previous.title = tips.previous;
    next.title = tips.next;
    previous.setAttribute("aria-label", tips.previous);
    next.setAttribute("aria-label", tips.next);
    document.getElementById("stop").title = "Stop reading";
    document.getElementById("replay").title = "Replay the last reply";
    paintPlay("stopped");
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

  botVoiceSelect.addEventListener("change", function () {
    saveBot({ voiceURI: botVoiceSelect.value, name: currentBot.name });
  });

  botReadInput.addEventListener("change", function () {
    saveBot({ autoRead: botReadInput.checked, name: currentBot.name });
  });

  newBotsInput.addEventListener("change", function () {
    save({ newBotsAutoRead: newBotsInput.checked });
  });

  betaInput.addEventListener("change", function () {
    save({ betaUpdates: betaInput.checked, updateCheckedAt: 0 });
    askBackground({ type: "check-update", force: true });
  });

  rateInput.addEventListener("input", function () {
    showRate(rateInput.value);
    save({ rate: GV.clampRate(rateInput.value) });
  });

  document.getElementById("previous").addEventListener("click", function () {
    askBackground({ type: "broadcast", command: "previous" }).then(refreshStatus);
  });

  playButton.addEventListener("click", function () {
    askBackground({ type: "broadcast", command: "play-pause" }).then(function (response) {
      paintPlay(response && response.mode);
      refreshStatus();
    });
  });

  document.getElementById("next").addEventListener("click", function () {
    askBackground({ type: "broadcast", command: "next" }).then(refreshStatus);
  });

  document.getElementById("stop").addEventListener("click", function () {
    askBackground({ type: "broadcast", command: "stop" }).then(function () {
      paintPlay("stopped");
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

  labelButtons();

  chrome.storage.local.get(GV.DEFAULTS, function (stored) {
    enabledInput.checked = stored.enabled !== false;
    debugInput.checked = stored.debug === true;
    newBotsInput.checked = stored.newBotsAutoRead !== false;
    betaInput.checked = stored.betaUpdates === true;
    storedBots = stored.bots || {};
    rateInput.value = String(GV.clampRate(stored.rate));
    showRate(rateInput.value);
    voiceOptions(voiceSelect, stored.voiceURI || "", true);
    showUpdate(stored.updateNotice);
    refreshStatus();
  });

  askBackground({ type: "check-update", force: false }).then(function (response) {
    if (response && response.notice) showUpdate(response.notice);
  });

  if (window.speechSynthesis) {
    window.speechSynthesis.addEventListener("voiceschanged", function () {
      if (saving) return;
      voiceOptions(voiceSelect, voiceSelect.value, true);
      voiceOptions(botVoiceSelect, botVoiceSelect.value, false);
    });
  }
})();

// Watches one Grok chat tab. Speaks only a bot reply that shows up after
// this script arms (page load, or the moment the popup switch is turned on).
(function (root) {
  "use strict";

  var GV = root.GrokVoice;
  var voiceURI = GV.DEFAULTS.voiceURI;
  var rate = GV.DEFAULTS.rate;
  var debug = GV.DEFAULTS.debug === true;
  var keys = new WeakMap();
  var keySeq = 1;
  var scanTimer = null;
  var observer = null;
  var shadowObservers = new WeakSet();
  var debugEl = null;
  var DEBUG_CLASS = "grok-voice-debug-target";
  var queuedSpeech = "";
  var unlockArmed = false;
  var cachedVoice = null;
  var cachedVoiceURI = null;

  var session = GV.createSession({
    settleMs: GV.SETTLE_MS,
    onSpeak: speakAloud
  });

  function keyFor(el) {
    var attr = el.getAttribute("data-message-id") || el.getAttribute("data-id") || el.id || "";
    if (attr) return "id:" + attr;
    var key = keys.get(el);
    if (!key) {
      key = "el:" + (keySeq++);
      keys.set(el, key);
    }
    return key;
  }

  function recordsFrom(replies) {
    var out = [];
    for (var i = 0; i < replies.length; i++) {
      var reply = replies[i];
      if (!reply || !reply.speech) continue;
      out.push({
        key: keyFor(reply.element),
        raw: reply.raw || reply.speech,
        speech: reply.speech
      });
    }
    return out;
  }

  function getSynth() {
    var synth = root.speechSynthesis;
    if (synth && typeof synth.speak === "function") return synth;
    return null;
  }

  // Pick the saved voice once, after the browser has loaded its voice list.
  // Later voiceschanged events must not swap in a different voice.
  function rememberVoice() {
    if (cachedVoice && (!voiceURI || cachedVoice.voiceURI === voiceURI)) return;
    var synth = getSynth();
    if (!synth || typeof synth.getVoices !== "function") return;
    var voices = synth.getVoices() || [];
    if (!voices.length) return;
    if (!voiceURI) {
      cachedVoice = voices[0];
      cachedVoiceURI = cachedVoice.voiceURI || "";
      return;
    }
    for (var i = 0; i < voices.length; i++) {
      if (voices[i].voiceURI === voiceURI) {
        cachedVoice = voices[i];
        cachedVoiceURI = voiceURI;
        return;
      }
    }
  }

  function voiceForUtterance() {
    if (!cachedVoice || (voiceURI && cachedVoice.voiceURI !== voiceURI)) rememberVoice();
    if (voiceURI && (!cachedVoice || cachedVoice.voiceURI !== voiceURI)) return null;
    return cachedVoice;
  }

  function speakAloud(text) {
    if (!text) return;
    lastDetect.reason = "spoke";
    lastDetect.snippet = snippetOf(text);
    logResolve();
    attemptSpeak(text, true);
  }

  function attemptSpeak(text, allowCancel) {
    var synth = getSynth();
    var Utterance = root.SpeechSynthesisUtterance;
    if (!synth || !Utterance || !text) return;
    try {
      if (allowCancel && (synth.speaking || synth.pending)) synth.cancel();
      var utterance = new Utterance(text);
      utterance.rate = GV.clampRate(rate);
      var voice = voiceForUtterance();
      if (voice) {
        utterance.voice = voice;
        if (voice.lang) utterance.lang = voice.lang;
      }
      utterance.onerror = function (event) {
        if (event && event.error === "not-allowed") {
          queuedSpeech = text;
          armUnlock();
        }
      };
      synth.speak(utterance);
    } catch (err) {
      queuedSpeech = text;
      armUnlock();
    }
  }

  function unlockOnce() {
    var text = queuedSpeech;
    queuedSpeech = "";
    disarmUnlock();
    if (!text) return;
    attemptSpeak(text, false);
  }

  function armUnlock() {
    if (unlockArmed || !queuedSpeech) return;
    unlockArmed = true;
    document.addEventListener("pointerdown", unlockOnce, true);
    document.addEventListener("keydown", unlockOnce, true);
  }

  function disarmUnlock() {
    if (!unlockArmed) return;
    unlockArmed = false;
    document.removeEventListener("pointerdown", unlockOnce, true);
    document.removeEventListener("keydown", unlockOnce, true);
  }

  function stopSpeaking() {
    queuedSpeech = "";
    disarmUnlock();
    session.stop();
    var synth = getSynth();
    if (synth && synth.cancel) {
      try { synth.cancel(); } catch (err) { /* already stopped */ }
    }
  }

  function markArmed(on) {
    var node = document.documentElement;
    if (node) node.setAttribute("data-grok-voice-armed", on ? "1" : "0");
  }

  // Pass a callback so a missing worker does not reject an uncaught promise.
  // Reading lastError is what keeps that failure out of the page console.
  function safeSend(message) {
    if (!chrome.runtime || !chrome.runtime.id) return;
    try {
      chrome.runtime.sendMessage(message, function () {
        void chrome.runtime.lastError;
      });
    } catch (err) {
      // The worker may still be starting. The badge is set from the tab URL.
    }
  }

  function ensureDebugStyle() {
    if (document.getElementById("grok-voice-debug-style")) return;
    var style = document.createElement("style");
    style.id = "grok-voice-debug-style";
    style.textContent = "." + DEBUG_CLASS + "{outline:3px solid #3ddc84 !important;outline-offset:3px !important;}";
    (document.head || document.documentElement).appendChild(style);
  }

  function clearDebug() {
    var nodes = document.querySelectorAll("." + DEBUG_CLASS);
    for (var i = 0; i < nodes.length; i++) nodes[i].classList.remove(DEBUG_CLASS);
    debugEl = null;
  }

  var lastDetect = { blocks: 0, groups: 0, snippet: "", reason: "starting" };

  function snippetOf(text) {
    text = String(text || "").replace(/\s+/g, " ").trim();
    if (text.length <= 60) return text;
    return text.slice(0, 60);
  }

  var lastLogLine = "";

  function logResolve(report) {
    if (!debug) return;
    report = report || {};
    var detail = "";
    var groups = report.groups || [];
    for (var i = 0; i < groups.length; i++) {
      detail += " group" + (i + 1) + "=" + groups[i].role + ":" + groups[i].reason
        + ":\"" + snippetOf(groups[i].speech) + "\"";
    }
    var line = "[GrokVoice] frame=" + location.href
      + " blocks=" + lastDetect.blocks
      + " groups=" + groups.length
      + " assistant=" + lastDetect.groups
      + " mode=" + (lastDetect.mode || "")
      + detail
      + " chosen=\"" + lastDetect.snippet + "\""
      + " skip=" + lastDetect.reason;
    if (line === lastLogLine) return;
    lastLogLine = line;
    try {
      console.log(line);
    } catch (err) {
      // Logging is only a debugging aid.
    }
  }

  function publishDetect(report, reason) {
    var replies = report.replies || [];
    var latest = replies.length ? replies[replies.length - 1] : null;
    lastDetect.blocks = report.blockCount || 0;
    lastDetect.groups = replies.length;
    lastDetect.mode = report.mode || "";
    lastDetect.snippet = snippetOf(latest ? latest.speech : "");
    lastDetect.reason = reason;
    var rootNode = document.documentElement;
    if (rootNode) {
      rootNode.setAttribute("data-grok-voice-detected", String(replies.length));
      rootNode.setAttribute("data-grok-voice-snippet", lastDetect.snippet);
    }
    logResolve(report);
    safeSend({
      type: "frame-report",
      href: location.href,
      blocks: lastDetect.blocks,
      groups: lastDetect.groups,
      snippet: lastDetect.snippet,
      reason: lastDetect.reason,
      mode: lastDetect.mode
    });
  }

  function updateDebug(replies) {
    if (!debug) {
      if (debugEl) clearDebug();
      return;
    }
    ensureDebugStyle();
    var latest = replies.length ? replies[replies.length - 1] : null;
    var target = latest ? (latest.body || latest.element) : null;
    if (!target || target.isConnected === false) {
      clearDebug();
      return;
    }
    if (debugEl === target && target.classList.contains(DEBUG_CLASS)) return;
    clearDebug();
    debugEl = target;
    target.classList.add(DEBUG_CLASS);
  }

  function applyEnabled(on) {
    session.setEnabled(on);
    if (on) {
      session.arm(recordsFrom(GV.detectAssistantReplies(document)));
      markArmed(true);
    } else {
      stopSpeaking();
      markArmed(false);
    }
    safeSend({ type: "watch-state", enabled: Boolean(on) });
    scheduleScan();
  }

  function scan() {
    var report = GV.inspectAssistant(document);
    var replies = report.replies || [];
    updateDebug(replies);
    var reason = "disabled";
    if (!session.isEnabled()) reason = "disabled";
    else if (!report.blockCount) reason = "no-streamdown-blocks";
    else if (!replies.length) reason = "no-assistant-groups";
    else reason = session.watch(recordsFrom(replies)) || "waiting";
    publishDetect(report, reason);
  }

  function scheduleScan() {
    if (scanTimer) return;
    scanTimer = setTimeout(function () {
      scanTimer = null;
      try {
        watchShadows(document);
        scan();
      } catch (err) {
        // Keep watching after a bad read.
      }
    }, 50);
  }

  function watchShadows(rootNode) {
    if (!observer || !rootNode || !rootNode.querySelectorAll) return;
    var all = rootNode.querySelectorAll("*");
    for (var i = 0; i < all.length; i++) {
      var shadow = all[i].shadowRoot;
      if (!shadow || shadowObservers.has(shadow)) continue;
      shadowObservers.add(shadow);
      observer.observe(shadow, observeOptions());
      watchShadows(shadow);
    }
  }

  function observeOptions() {
    return {
      subtree: true,
      childList: true,
      characterData: true
    };
  }

  function mutationsAreNoise(records) {
    if (!records || !records.length || typeof GV.ignoreMutation !== "function") return false;
    for (var i = 0; i < records.length; i++) {
      if (!GV.ignoreMutation(records[i])) return false;
    }
    return true;
  }

  function startObserver() {
    if (observer) return;
    observer = new MutationObserver(function (records) {
      try {
        bindObserver();
        if (mutationsAreNoise(records)) return;
        scheduleScan();
      } catch (err) {
        scheduleScan();
      }
    });
    bindObserver();
  }

  var observedRoot = null;

  function bindObserver() {
    var target = document.body || document.documentElement;
    if (!target || observedRoot === target) {
      watchShadows(document.body || document);
      return;
    }
    observer.observe(target, observeOptions());
    if (document.documentElement && document.documentElement !== target) {
      observer.observe(document.documentElement, { childList: true, subtree: false });
    }
    observedRoot = target;
    watchShadows(target);
  }

  chrome.runtime.onMessage.addListener(function (message, _sender, sendResponse) {
    if (!message || typeof message.type !== "string") return;
    if (message.type === "stop") {
      stopSpeaking();
      sendResponse({ ok: true });
      return;
    }
    if (message.type === "replay") {
      var text = session.replay();
      sendResponse({ ok: Boolean(text), text: text || "" });
      return;
    }
    if (message.type === "status") {
      sendResponse({
        ok: true,
        enabled: session.isEnabled(),
        armed: document.documentElement.getAttribute("data-grok-voice-armed") === "1",
        last: session.getLastSpoken(),
        detected: lastDetect.groups,
        blocks: lastDetect.blocks,
        snippet: lastDetect.snippet,
        reason: lastDetect.reason
      });
    }
  });

  chrome.storage.onChanged.addListener(function (changes, area) {
    if (area !== "local") return;
    if (changes.voiceURI) {
      voiceURI = changes.voiceURI.newValue || "";
      cachedVoice = null;
      cachedVoiceURI = null;
      rememberVoice();
    }
    if (changes.rate) rate = GV.clampRate(changes.rate.newValue);
    if (changes.debug) {
      debug = changes.debug.newValue === true;
      if (!debug) clearDebug();
      scheduleScan();
    }
    if (changes.enabled) applyEnabled(changes.enabled.newValue !== false);
  });

  function boot() {
    startObserver();
    var synth = getSynth();
    if (synth && synth.addEventListener) {
      synth.addEventListener("voiceschanged", rememberVoice);
    }
    chrome.storage.local.get(GV.DEFAULTS, function (stored) {
      voiceURI = stored.voiceURI || "";
      rate = GV.clampRate(stored.rate);
      debug = stored.debug === true;
      cachedVoice = null;
      cachedVoiceURI = null;
      rememberVoice();
      applyEnabled(stored.enabled !== false);
      scheduleScan();
    });
    setInterval(scheduleScan, 1000);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  } else {
    boot();
  }
})(globalThis);

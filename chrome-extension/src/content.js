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

  function pickVoice(synth) {
    if (!voiceURI || !synth.getVoices) return null;
    var voices = synth.getVoices() || [];
    for (var i = 0; i < voices.length; i++) {
      if (voices[i].voiceURI === voiceURI) return voices[i];
    }
    return null;
  }

  // Chrome drops speechSynthesis.speak until the page has a click or keypress.
  // Keep the words and try again on the next gesture. The call has to happen
  // inside that event, so the listeners below invoke speak directly.
  function speakAloud(text) {
    if (!text) return;
    queuedSpeech = text;
    attemptSpeak(text);
  }

  function attemptSpeak(text) {
    var synth = getSynth();
    var Utterance = root.SpeechSynthesisUtterance;
    if (!synth || !Utterance || !text) return;
    try {
      if (synth.speaking || synth.pending) synth.cancel();
      var utterance = new Utterance(text);
      utterance.rate = GV.clampRate(rate);
      var voice = pickVoice(synth);
      if (voice) {
        utterance.voice = voice;
        if (voice.lang) utterance.lang = voice.lang;
      }
      utterance.onstart = function () {
        if (queuedSpeech === text) queuedSpeech = "";
      };
      utterance.onend = function () {
        if (queuedSpeech === text) queuedSpeech = "";
      };
      utterance.onerror = function (event) {
        var reason = event && event.error;
        if (reason === "not-allowed") queuedSpeech = text;
      };
      synth.speak(utterance);
    } catch (err) {
      queuedSpeech = text;
    }
  }

  function flushQueued() {
    if (!queuedSpeech) return;
    attemptSpeak(queuedSpeech);
  }

  function stopSpeaking() {
    queuedSpeech = "";
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

  function updateDebug(replies) {
    if (!debug) {
      if (debugEl) clearDebug();
      return;
    }
    ensureDebugStyle();
    // Always the bottom-most assistant body from this scan. Never reuse the
    // first bubble found on an earlier pass.
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
    try {
      console.info("[Grok Voice Reader] latest assistant reply:", GV.elementPath(target));
    } catch (err) {
      // Logging is only a debugging aid.
    }
  }

  function currentReplies() {
    return GV.detectAssistantReplies(document);
  }

  function applyEnabled(on) {
    session.setEnabled(on);
    if (on) {
      session.arm(recordsFrom(currentReplies()));
      markArmed(true);
    } else {
      stopSpeaking();
      markArmed(false);
    }
    safeSend({ type: "watch-state", enabled: Boolean(on) });
  }

  function scan() {
    var replies = currentReplies();
    updateDebug(replies);
    if (!session.isEnabled()) return;
    session.watch(recordsFrom(replies));
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
      characterData: true,
      attributes: true
    };
  }

  function startObserver() {
    if (observer || !document.documentElement) return;
    observer = new MutationObserver(scheduleScan);
    observer.observe(document.documentElement, observeOptions());
    watchShadows(document);
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
        last: session.getLastSpoken()
      });
    }
  });

  chrome.storage.onChanged.addListener(function (changes, area) {
    if (area !== "local") return;
    if (changes.voiceURI) voiceURI = changes.voiceURI.newValue || "";
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
    chrome.storage.local.get(GV.DEFAULTS, function (stored) {
      voiceURI = stored.voiceURI || "";
      rate = GV.clampRate(stored.rate);
      debug = stored.debug === true;
      applyEnabled(stored.enabled !== false);
      if (debug) scheduleScan();
    });
  }

  document.addEventListener("pointerdown", flushQueued, true);
  document.addEventListener("keydown", flushQueued, true);

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  } else {
    boot();
  }
})(globalThis);

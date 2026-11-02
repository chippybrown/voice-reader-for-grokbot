// Watches one Grok chat tab. Speaks only a bot reply that appears after
// this script arms (page load, or the moment the popup switch is turned on).
(function (root) {
  "use strict";

  var GV = root.GrokVoice;
  var voiceURI = GV.DEFAULTS.voiceURI;
  var rate = GV.DEFAULTS.rate;
  var keys = new WeakMap();
  var keySeq = 1;
  var scanTimer = null;
  var observer = null;

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

  function chatRoot(doc) {
    var selectors = GV.SELECTORS.chatRoot;
    for (var i = 0; i < selectors.length; i++) {
      try {
        var found = doc.querySelector(selectors[i]);
        if (found) return found;
      } catch (err) {
        // Ignore a selector Chip is mid-edit on.
      }
    }
    return doc.body || doc.documentElement;
  }

  function queryAll(rootNode, selector) {
    try {
      return Array.prototype.slice.call(rootNode.querySelectorAll(selector));
    } catch (err) {
      return [];
    }
  }

  function outermost(nodes) {
    return nodes.filter(function (el) {
      return !nodes.some(function (other) {
        return other !== el && other.contains(el);
      });
    });
  }

  function insideUser(el) {
    var selector = GV.SELECTORS.user.filter(Boolean).join(", ");
    if (!selector) return false;
    try {
      return el.matches(selector) || Boolean(el.closest(selector));
    } catch (err) {
      return false;
    }
  }

  function fallback(rootNode) {
    var hints = GV.SELECTORS.fallbackHints.filter(Boolean).join(", ");
    var hinted = hints ? queryAll(rootNode, hints).filter(function (el) {
      return !insideUser(el);
    }) : [];
    hinted = outermost(hinted);
    if (hinted.length) return hinted;

    // Approximate: message-shaped blocks that are not the composer and not
    // a person-side bubble. Chip should set selectors.assistant so this path
    // does not have to guess.
    var turns = queryAll(rootNode, "article, [role='article'], [role='listitem'], li");
    turns = turns.filter(function (el) {
      if (insideUser(el)) return false;
      if (el.closest("form, nav, footer, header")) return false;
      if (el.querySelector("textarea, input")) return false;
      return true;
    });
    return outermost(turns);
  }

  function findAssistantElements(doc) {
    var rootNode = chatRoot(doc);
    var selectors = GV.SELECTORS.assistant;
    for (var i = 0; i < selectors.length; i++) {
      var nodes = outermost(queryAll(rootNode, selectors[i]));
      if (nodes.length) return nodes;
    }
    return fallback(rootNode);
  }

  function readRoot(el) {
    var selectors = GV.SELECTORS.content;
    for (var i = 0; i < selectors.length; i++) {
      try {
        if (el.matches(selectors[i])) return el;
        var inner = el.querySelector(selectors[i]);
        if (inner) return inner;
      } catch (err) {
        // Skip a bad selector and try the next one.
      }
    }
    return el;
  }

  function snapshot() {
    return findAssistantElements(document).map(function (el) {
      var source = readRoot(el);
      var raw = GV.visibleRaw(source);
      return {
        key: keyFor(el),
        raw: raw,
        speech: raw ? GV.visibleSpeech(source) : ""
      };
    });
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

  function speakAloud(text) {
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
      synth.speak(utterance);
    } catch (err) {
      // A missing voice or a torn-down tab should not break the watcher.
    }
  }

  function stopSpeaking() {
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

  function publish(on) {
    try {
      chrome.runtime.sendMessage({ type: "watch-state", enabled: Boolean(on) });
    } catch (err) {
      // The service worker may be asleep. The tab listener sets the badge too.
    }
  }

  function applyEnabled(on) {
    session.setEnabled(on);
    if (on) {
      session.arm(snapshot());
      markArmed(true);
    } else {
      stopSpeaking();
      markArmed(false);
    }
    publish(on);
  }

  function scan() {
    if (!session.isEnabled()) return;
    session.watch(snapshot());
  }

  function scheduleScan() {
    if (scanTimer) return;
    scanTimer = setTimeout(function () {
      scanTimer = null;
      try { scan(); } catch (err) { /* keep watching after a bad selector */ }
    }, 50);
  }

  function startObserver() {
    if (observer || !document.documentElement) return;
    observer = new MutationObserver(scheduleScan);
    observer.observe(document.documentElement, {
      subtree: true,
      childList: true,
      characterData: true,
      attributes: true,
      attributeFilter: ["class", "style", "hidden", "aria-hidden", "data-testid", "data-message-id"]
    });
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
    if (changes.enabled) applyEnabled(changes.enabled.newValue !== false);
  });

  function boot() {
    startObserver();
    chrome.storage.local.get(GV.DEFAULTS, function (stored) {
      voiceURI = stored.voiceURI || "";
      rate = GV.clampRate(stored.rate);
      applyEnabled(stored.enabled !== false);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  } else {
    boot();
  }
})(globalThis);

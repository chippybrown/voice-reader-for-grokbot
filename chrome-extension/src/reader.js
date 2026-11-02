// Decide which reply is new, wait until it stops changing, speak it once.
// The DOM and speechSynthesis stay in content.js. This file only sees
// { key, raw, speech } records in document order.
(function (root) {
  "use strict";

  var GV = root.GrokVoice || (root.GrokVoice = {});

  function continues(previous, next) {
    if (!previous || !next) return false;
    if (previous === next) return true;
    // Short texts match too often ("Hi" / "Hi, the answer is...").
    if (previous.length < 24) return false;
    return next.indexOf(previous) === 0 || previous.indexOf(next) === 0;
  }

  function sameStream(pending, message) {
    if (pending.key === message.key) return true;
    var a = pending.raw || "";
    var b = message.raw || "";
    if (!a || !b) return false;
    return b.indexOf(a) === 0 || a.indexOf(b) === 0;
  }

  GV.createSession = function createSession(options) {
    var settleMs = options && options.settleMs > 0 ? options.settleMs : 1500;
    var onSpeak = options && options.onSpeak ? options.onSpeak : function () {};
    var enabled = true;
    var armed = false;
    var historical = new Set();
    var baselineText = new Map();
    var baselineSpeech = new Set();
    var spoken = new Set();
    var spokenStable = new Set();
    var spokenKey = "";
    var spokenRaw = "";
    var lastSpoken = "";
    var pending = null;
    var timer = null;
    var generation = 0;

    function clearTimer() {
      generation += 1;
      if (timer) {
        clearTimeout(timer);
        timer = null;
      }
    }

    function commit() {
      if (!enabled || !pending) return;
      var speech = String(pending.speech || "").trim();
      var raw = pending.raw || "";
      var key = pending.key;
      var id = stableKey(pending);
      pending = null;
      if (!speech || !id || spokenStable.has(id)) return;
      spoken.add(speech);
      spokenStable.add(id);
      spokenKey = key;
      spokenRaw = raw;
      lastSpoken = speech;
      onSpeak(speech);
    }

    // The same bubble with the same words is never spoken again. A later
    // change to that bubble is a different key. Replay does not use this.
    function alreadyCovered(message) {
      var id = stableKey(message);
      if (!id) return true;
      return spokenStable.has(id);
    }

    function stableKey(message) {
      var speech = String(message.speech || message.raw || "").replace(/\s+/g, " ").trim();
      if (!speech) return "";
      return String(message.key) + ":" + textHash(speech);
    }

    function textHash(text) {
      var hash = 5381;
      for (var i = 0; i < text.length; i++) {
        hash = ((hash * 33) ^ text.charCodeAt(i)) >>> 0;
      }
      return hash.toString(16);
    }

    function restartTimer() {
      var token = generation;
      if (timer) clearTimeout(timer);
      timer = setTimeout(function () {
        timer = null;
        if (token !== generation) return;
        commit();
      }, settleMs);
    }

    // Only the bubble that was already on screen, with the same body, stays quiet.
    // A different element, or a body that is not that saved text, is a new reply.
    function isHistorical(message) {
      var raw = message.raw || "";
      var speech = message.speech || "";
      if (!historical.has(message.key)) return false;
      var prev = baselineText.get(message.key) || "";
      if (!raw || raw === prev) return true;
      if (prev && continues(prev, raw)) return true;
      if (speech && baselineSpeech.has(speech)) return true;
      return false;
    }

    function newestSpoken(messages) {
      if (!messages) return null;
      for (var i = messages.length - 1; i >= 0; i--) {
        var message = messages[i];
        if (message && message.key && message.raw && String(message.raw).trim()) return message;
      }
      return null;
    }

    return {
      arm: function arm(messages) {
        armed = true;
        historical = new Set();
        baselineText = new Map();
        baselineSpeech = new Set();
        clearTimer();
        pending = null;
        var list = messages || [];
        for (var i = 0; i < list.length; i++) {
          var message = list[i];
          if (!message || !message.key) continue;
          historical.add(message.key);
          var raw = message.raw || "";
          baselineText.set(message.key, raw);
          if (message.speech) baselineSpeech.add(message.speech);
        }
      },

      setEnabled: function setEnabled(value) {
        enabled = Boolean(value);
        if (!enabled) {
          clearTimer();
          pending = null;
        }
      },

      isEnabled: function isEnabled() {
        return enabled;
      },

      // messages: assistant replies in document order, oldest first.
      watch: function watch(messages) {
        if (!enabled || !armed) return "not-armed";
        var message = newestSpoken(messages);
        if (!message) return "no-latest";
        if (isHistorical(message)) return "historical";
        if (alreadyCovered(message)) return "already-spoken";
        var speech = String(message.speech || "").trim();
        var raw = String(message.raw || "").replace(/\s+/g, " ").trim();
        if (!speech) return "empty";
        if (spokenStable.has(stableKey(message))) return "already-spoken";
        if (pending && !sameStream(pending, message)) commit();
        if (pending && sameStream(pending, message)) {
          if (pending.raw === raw) return "waiting";
          pending = { key: message.key, raw: raw, speech: speech };
          restartTimer();
          return "waiting";
        }
        pending = { key: message.key, raw: raw, speech: speech };
        restartTimer();
        return "waiting";
      },

      stop: function stop() {
        clearTimer();
        pending = null;
      },

      replay: function replay() {
        if (!lastSpoken) return "";
        onSpeak(lastSpoken);
        return lastSpoken;
      },

      getLastSpoken: function getLastSpoken() {
        return lastSpoken;
      }
    };
  };
})(globalThis);

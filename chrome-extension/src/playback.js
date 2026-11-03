// Which reply is selected, and whether Play is showing the pause icon.
// speechSynthesis stays in content.js. Pausing keeps the chunk and the
// character offset so Play can continue instead of starting over.
(function (root) {
  "use strict";

  var GV = root.GrokVoice || (root.GrokVoice = {});

  GV.createPlayback = function createPlayback(options) {
    var onSpeak = options && options.onSpeak ? options.onSpeak : function () {};
    var onPause = options && options.onPause ? options.onPause : function () { return false; };
    var onResume = options && options.onResume ? options.onResume : function () { return false; };
    var items = [];
    var index = -1;
    var mode = "stopped";

    function current() {
      if (index < 0 || index >= items.length) return null;
      return items[index];
    }

    function speakCurrent() {
      var item = current();
      if (!item || !item.speech) {
        mode = "stopped";
        return "";
      }
      mode = "playing";
      onSpeak(item.speech, item);
      return item.speech;
    }

    return {
      setItems: function setItems(list) {
        var key = current() ? current().key : "";
        items = list || [];
        if (key) {
          for (var i = 0; i < items.length; i++) {
            if (items[i] && items[i].key === key) {
              index = i;
              return;
            }
          }
        }
        if (index >= items.length) index = items.length - 1;
      },

      noteSpoken: function noteSpoken(key) {
        for (var i = 0; i < items.length; i++) {
          if (items[i] && items[i].key === key) {
            index = i;
            mode = "playing";
            return true;
          }
        }
        return false;
      },

      previous: function previous() {
        if (!items.length) return "";
        if (index < 0) index = Math.max(0, items.length - 2);
        else if (index > 0) index -= 1;
        return speakCurrent();
      },

      next: function next() {
        if (!items.length) return "";
        if (index < 0) index = items.length - 1;
        else if (index < items.length - 1) index += 1;
        return speakCurrent();
      },

      // One button. Pause keeps the place in the reply. Play continues
      // from there when onResume can. Otherwise the reply starts again.
      toggle: function toggle() {
        if (!items.length) return { mode: mode, speech: "", restarted: false };
        if (index < 0) index = items.length - 1;
        var item = current();
        var speech = item && item.speech ? item.speech : "";
        if (mode === "playing") {
          onPause();
          mode = "paused";
          return { mode: mode, speech: speech, restarted: false };
        }
        if (mode === "paused" && onResume()) {
          mode = "playing";
          return { mode: mode, speech: speech, restarted: false };
        }
        return { mode: "playing", speech: speakCurrent(), restarted: true };
      },

      stop: function stop() {
        mode = "stopped";
      },

      markEnded: function markEnded() {
        if (mode === "playing") mode = "stopped";
      },

      state: function state() {
        var item = current();
        return {
          mode: mode,
          index: index,
          icon: mode === "playing" ? "pause" : "play",
          speech: item ? item.speech : "",
          key: item ? item.key : "",
          element: item ? item.element : null,
          body: item ? (item.body || item.element) : null
        };
      }
    };
  };

  // Short local voices can use speechSynthesis.resume(). Long chunks and
  // online voices in Chrome and Edge often cannot, so those start again
  // from the last word boundary.
  GV.RESUME_CHUNK_LIMIT = 180;

  GV.splitSpeechChunks = function splitSpeechChunks(text) {
    var raw = String(text || "").replace(/\s+/g, " ").trim();
    if (!raw) return [];
    var parts = [];
    var start = 0;
    var i;
    for (i = 0; i < raw.length; i++) {
      var ch = raw.charAt(i);
      if (ch !== "." && ch !== "!" && ch !== "?" && ch !== "…") continue;
      var end = i + 1;
      while (end < raw.length && /["')\]]/.test(raw.charAt(end))) end += 1;
      if (end < raw.length && !/\s/.test(raw.charAt(end))) continue;
      pushChunk(parts, raw.slice(start, end));
      while (end < raw.length && /\s/.test(raw.charAt(end))) end += 1;
      start = end;
      i = end - 1;
    }
    pushChunk(parts, raw.slice(start));
    return parts;
  };

  function pushChunk(parts, piece) {
    var rest = String(piece || "").trim();
    var limit = GV.RESUME_CHUNK_LIMIT;
    while (rest.length > limit) {
      var cut = rest.lastIndexOf(" ", limit);
      if (cut < 40) cut = limit;
      parts.push(rest.slice(0, cut).trim());
      rest = rest.slice(cut).trim();
    }
    if (rest) parts.push(rest);
  }

  // charIndex from onboundary points at a word, or sometimes into one.
  GV.wordBoundaryIndex = function wordBoundaryIndex(text, charIndex) {
    var value = String(text || "");
    var index = Number(charIndex);
    if (index !== index || index <= 0) return 0;
    if (index > value.length) index = value.length;
    var at = index;
    if (at > 0 && at < value.length && !/\s/.test(value.charAt(at)) && !/\s/.test(value.charAt(at - 1))) {
      while (at > 0 && !/\s/.test(value.charAt(at - 1))) at -= 1;
    }
    while (at < value.length && /\s/.test(value.charAt(at))) at += 1;
    return at;
  };

  GV.resumeFromOffset = function resumeFromOffset(chunks, chunkIndex, charIndex) {
    var list = chunks || [];
    var index = chunkIndex | 0;
    if (index < 0 || index >= list.length) return [];
    var chunk = String(list[index] || "");
    var at = GV.wordBoundaryIndex(chunk, charIndex);
    var rest = chunk.slice(at).trim();
    var out = [];
    if (rest) out.push(rest);
    for (var i = index + 1; i < list.length; i++) {
      if (list[i]) out.push(String(list[i]));
    }
    return out;
  };

  GV.resumeIsReliable = function resumeIsReliable(chunk, voice) {
    var text = String(chunk || "");
    if (!text || text.length > GV.RESUME_CHUNK_LIMIT) return false;
    var label = voice ? String(voice.name || "") + " " + String(voice.voiceURI || "") : "";
    if (/online|natural|neural|network/i.test(label)) return false;
    return true;
  };

  // Speaks a reply as chunks. Pause keeps the chunk index and charIndex.
  // Resume uses the engine when that is reliable, otherwise the saved offset.
  // An audio element uses pause() and play() so its position stays.
  GV.createSpeechQueue = function createSpeechQueue(options) {
    options = options || {};
    var speak = options.speak || function () {};
    var cancel = options.cancel || function () {};
    var pauseEngine = options.pause || function () { return false; };
    var resumeEngine = options.resume || function () { return false; };
    var voiceFor = options.voice || function () { return null; };
    var chunks = [];
    var index = 0;
    var charIndex = 0;
    var paused = false;
    var generation = 0;
    var audio = null;
    var liveText = "";

    function locate(parts, absolute) {
      var cursor = 0;
      var i;
      for (i = 0; i < parts.length; i++) {
        var size = String(parts[i] || "").length;
        if (absolute < cursor + size || i === parts.length - 1) {
          var local = absolute - cursor;
          if (local < 0) local = 0;
          if (local > size) local = size;
          return { index: i, charIndex: local };
        }
        cursor += size + 1;
      }
      return { index: 0, charIndex: 0 };
    }

    function playFrom(list, start, gen) {
      chunks = list || [];
      index = start;
      charIndex = 0;
      paused = false;
      if (!chunks.length || start >= chunks.length) {
        if (options.onfinished && gen === generation) options.onfinished();
        return false;
      }
      var text = chunks[start];
      if (!text) return playFrom(chunks, start + 1, gen);
      liveText = text;
      speak(text, {
        onboundary: function (event) {
          if (gen !== generation || paused || !event) return;
          var name = event.name || "word";
          if (name !== "word" && name !== "sentence") return;
          var next = Number(event.charIndex);
          if (next !== next) return;
          charIndex = next;
        },
        onend: function () {
          if (gen !== generation || paused) return;
          playFrom(chunks, start + 1, gen);
        },
        onerror: function (event) {
          if (options.onerror) options.onerror(event, text);
        }
      });
      return true;
    }

    return {
      start: function (text) {
        audio = null;
        generation += 1;
        paused = false;
        cancel();
        var full = String(text || "").replace(/\s+/g, " ").trim();
        var parts = GV.splitSpeechChunks(full);
        chunks = parts;
        index = 0;
        charIndex = 0;
        liveText = full;
        if (!full) return false;
        var gen = generation;
        speak(full, {
          onboundary: function (event) {
            if (gen !== generation || paused || !event) return;
            var name = event.name || "word";
            if (name !== "word" && name !== "sentence") return;
            var next = Number(event.charIndex);
            if (next !== next) return;
            var where = locate(parts, next);
            index = where.index;
            charIndex = where.charIndex;
          },
          onend: function () {
            if (gen !== generation || paused) return;
            if (options.onfinished) options.onfinished();
          },
          onerror: function (event) {
            if (options.onerror) options.onerror(event, full);
          }
        });
        return true;
      },
      useAudio: function (element) {
        generation += 1;
        paused = false;
        chunks = [];
        index = 0;
        charIndex = 0;
        audio = element || null;
        return Boolean(audio);
      },
      pause: function () {
        if (audio && typeof audio.pause === "function") {
          audio.pause();
          paused = true;
          return true;
        }
        if (GV.resumeIsReliable(liveText, voiceFor()) && pauseEngine()) {
          paused = true;
          return true;
        }
        paused = true;
        generation += 1;
        cancel();
        return chunks.length > 0;
      },
      resume: function () {
        if (audio && typeof audio.play === "function" && audio.paused && !audio.ended) {
          paused = false;
          try { audio.play(); } catch (err) { return false; }
          return true;
        }
        if (paused && GV.resumeIsReliable(liveText, voiceFor()) && resumeEngine()) {
          paused = false;
          return true;
        }
        var plan = GV.resumeFromOffset(chunks, index, charIndex);
        if (!plan.length) return false;
        generation += 1;
        var gen = generation;
        cancel();
        liveText = plan[0] || "";
        return playFrom(plan, 0, gen);
      },
      stop: function () {
        generation += 1;
        paused = false;
        chunks = [];
        index = 0;
        charIndex = 0;
        if (audio && typeof audio.pause === "function") {
          try { audio.pause(); } catch (err) { /* already quiet */ }
        }
        audio = null;
        cancel();
      },
      state: function () {
        return { chunks: chunks.slice(), index: index, charIndex: charIndex, paused: paused };
      }
    };
  };
})(globalThis);

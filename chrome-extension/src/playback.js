// Which reply is selected, and whether Play is showing the pause icon.
// speechSynthesis stays in content.js. onPause/onResume report whether the
// browser actually held the utterance.
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

      // One button. Pause holds the utterance when the browser can.
      // Otherwise the next press starts the same reply again.
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
})(globalThis);

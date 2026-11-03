// YouTube-style previous, play/pause, and next. They live in the composer,
// between the microphone and the voice button. If that pair is not there,
// they sit in a fixed bar just above the composer's right edge.
// The green outline stays on the reply. The old per-bubble bar is off.
(function (root) {
  "use strict";

  var GV = root.GrokVoice || (root.GrokVoice = {});
  var READING_CLASS = "grok-voice-reading";
  var currentHost = null;
  var currentTarget = null;
  var handlers = { onPrevious: null, onToggle: null, onNext: null };

  var ICONS = {
    previous: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6h2v12H6zm3.5 6 8.5 6V6z"></path></svg>',
    play: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5v14l11-7z"></path></svg>',
    pause: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"></path></svg>',
    next: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 18l8.5-6L6 6v12zM16 6v12h2V6h-2z"></path></svg>'
  };

  GV.controlIcon = function controlIcon(name) {
    return ICONS[name] || "";
  };

  GV.controlTooltips = function controlTooltips() {
    var shortcuts = GV.SHORTCUTS || {};
    var click = " Click the reply to play or pause.";
    return {
      previous: "Previous reply (" + (shortcuts.previous || "Alt+Left") + ")",
      play: "Play (" + (shortcuts.playPause || "Alt+Shift+P") + ")." + click,
      pause: "Pause (" + (shortcuts.playPause || "Alt+Shift+P") + ")." + click,
      next: "Next reply (" + (shortcuts.next || "Alt+Right") + ")"
    };
  };

  function ensureStyle(doc) {
    if (!doc.getElementById) return;
    if (doc.getElementById("grok-voice-reading-style")) return;
    var style = doc.createElement("style");
    style.id = "grok-voice-reading-style";
    style.textContent = "." + READING_CLASS + "{outline:3px solid #3ddc84 !important;outline-offset:3px !important;}";
    (doc.head || doc.documentElement).appendChild(style);
  }

  function buttonHtml(action, icon, tip) {
    return '<button type="button" data-action="' + action + '" title="' + tip + '" aria-label="' + tip + '">' +
      ICONS[icon] + '<span class="tip">' + tip + "</span></button>";
  }

  function paint(host, mode) {
    var shadow = host.shadowRoot;
    if (!shadow) return;
    var tips = GV.controlTooltips();
    var toggle = shadow.querySelector('[data-action="play-pause"]');
    if (!toggle) return;
    var playing = mode === "playing";
    var tip = playing ? tips.pause : tips.play;
    toggle.innerHTML = ICONS[playing ? "pause" : "play"] + '<span class="tip">' + tip + "</span>";
    toggle.title = tip;
    toggle.setAttribute("aria-label", tip);
  }

  function fieldHint(field) {
    return (field.getAttribute("placeholder") || field.getAttribute("aria-placeholder") ||
      field.getAttribute("aria-label") || field.getAttribute("data-placeholder") || "");
  }

  function isMessageField(field) {
    return /message/i.test(fieldHint(field));
  }

  // The chat box, and where the controls should go.
  // mode "composer" means insert before the round voice button.
  // mode "above" means the mic and voice button were not both found.
  GV.findComposerSlot = function findComposerSlot(doc) {
    var none = { mode: "none", box: null, field: null, voice: null };
    if (!doc || !doc.querySelectorAll) return none;
    var fields = [];
    try {
      fields = doc.querySelectorAll("textarea, input, [contenteditable='true'], [contenteditable=''], [role='textbox']");
    } catch (err) {
      return none;
    }
    var field = null;
    var i;
    for (i = 0; i < fields.length; i++) {
      if (isMessageField(fields[i])) {
        field = fields[i];
        break;
      }
    }
    if (!field) return none;
    var box = field.parentElement || field;
    var node = field.parentElement;
    var guard = 0;
    while (node && node !== doc.body && node !== doc.documentElement && guard < 8) {
      guard += 1;
      var count = 0;
      try { count = node.querySelectorAll("button").length; } catch (err) { count = 0; }
      if (count >= 2) {
        box = node;
        break;
      }
      node = node.parentElement;
    }
    var buttons = [];
    try { buttons = box.querySelectorAll("button"); } catch (err) { buttons = []; }
    var after = [];
    for (i = 0; i < buttons.length; i++) {
      if (!buttons[i].closest || !buttons[i].closest("[data-grok-voice-controls]")) {
        if (field.compareDocumentPosition(buttons[i]) & 4) after.push(buttons[i]);
      }
    }
    if (after.length >= 2) {
      return { mode: "composer", box: box, field: field, voice: after[after.length - 1] };
    }
    return { mode: "above", box: box, field: field, voice: null };
  };

  function positionAbove(host, box) {
    if (!host || !box || !box.getBoundingClientRect) return;
    var rect = box.getBoundingClientRect();
    var view = box.ownerDocument && box.ownerDocument.defaultView;
    var width = host.offsetWidth || 96;
    var height = host.offsetHeight || 32;
    var margin = 8;
    var viewWidth = view && view.innerWidth ? view.innerWidth : 800;
    var viewHeight = view && view.innerHeight ? view.innerHeight : 600;
    var top = rect.top - height - 4;
    if (top < margin) top = margin;
    if (top + height > viewHeight - margin) top = Math.max(margin, viewHeight - height - margin);
    var left = rect.right - width;
    if (left < margin) left = margin;
    if (left + width > viewWidth - margin) left = Math.max(margin, viewWidth - width - margin);
    host.style.position = "fixed";
    host.style.top = Math.round(top) + "px";
    host.style.left = Math.round(left) + "px";
  }

  function interactiveTarget(node) {
    var el = node && node.nodeType === 1 ? node : (node && node.parentElement);
    if (!el || !el.closest) return false;
    try {
      return Boolean(el.closest("a, button, input, textarea, select, pre, code, [role='button'], [data-grok-voice-controls]"));
    } catch (err) {
      return false;
    }
  }

  // A plain click on the outlined reply toggles play. Drags, double-clicks,
  // links, and modifier keys do not.
  GV.bindReplyClick = function bindReplyClick(doc, isInside, onToggle) {
    if (!doc || doc.__grokVoiceClickBound) return;
    doc.__grokVoiceClickBound = true;
    var pending = null;
    var timer = null;
    function cancel() {
      pending = null;
      if (timer) {
        clearTimeout(timer);
        timer = null;
      }
    }
    function modified(event) {
      return event.ctrlKey || event.metaKey || event.altKey || event.shiftKey;
    }
    doc.addEventListener("mousedown", function (event) {
      if (event.button !== 0 || event.detail > 1) {
        cancel();
        return;
      }
      if (modified(event) || !isInside(event.target) || interactiveTarget(event.target)) {
        pending = null;
        return;
      }
      pending = { x: event.clientX, y: event.clientY };
    }, true);
    doc.addEventListener("mouseup", function (event) {
      var start = pending;
      pending = null;
      if (!start || event.button !== 0 || event.detail > 1 || modified(event)) return;
      if (Math.abs(event.clientX - start.x) > 5 || Math.abs(event.clientY - start.y) > 5) return;
      if (!isInside(event.target) || interactiveTarget(event.target)) return;
      if (timer) clearTimeout(timer);
      timer = setTimeout(function () {
        timer = null;
        var selection = null;
        try {
          var view = doc.defaultView;
          selection = view && view.getSelection ? view.getSelection() : null;
        } catch (err) {
          selection = null;
        }
        if (selection && selection.isCollapsed === false) return;
        if (onToggle) onToggle();
      }, 250);
    }, true);
    doc.addEventListener("dblclick", function () { cancel(); }, true);
  };

  function build(doc, options) {
    var tips = GV.controlTooltips();
    var host = doc.createElement("div");
    host.setAttribute("data-grok-voice-controls", "1");
    host.setAttribute("role", "toolbar");
    host.setAttribute("aria-label", "Reply playback");
    host.style.zIndex = "2147483646";
    host.style.margin = "0";
    host.style.pointerEvents = "auto";
    host.style.display = "inline-flex";
    host.style.alignItems = "center";
    var shadow = host.attachShadow({ mode: "open" });
    shadow.innerHTML =
      "<style>" +
      ":host{all:initial;}" +
      ".bar{display:flex;gap:2px;padding:2px;background:rgba(15,15,15,.9);border-radius:8px;box-shadow:0 1px 4px rgba(0,0,0,.45);}" +
      ":host([data-grok-voice-placement='composer']) .bar{background:transparent;box-shadow:none;padding:0;}" +
      "button{position:relative;width:28px;height:28px;padding:0;border:0;border-radius:4px;background:transparent;color:#fff;cursor:pointer;}" +
      "button:hover,button:focus{background:rgba(255,255,255,.16);}" +
      "svg{width:20px;height:20px;fill:#fff;display:block;margin:4px auto;}" +
      ".tip{display:none;position:absolute;bottom:calc(100% + 6px);left:50%;transform:translateX(-50%);padding:4px 6px;border-radius:4px;background:#111;color:#fff;font:12px/1.2 Segoe UI,sans-serif;white-space:nowrap;pointer-events:none;}" +
      "button:hover .tip,button:focus .tip{display:block;}" +
      "</style>" +
      '<div class="bar">' +
      buttonHtml("previous", "previous", tips.previous) +
      buttonHtml("play-pause", "play", tips.play) +
      buttonHtml("next", "next", tips.next) +
      "</div>";
    shadow.addEventListener("click", function (event) {
      var node = event.target;
      var button = node && node.closest ? node.closest("button") : null;
      if (!button && node && node.parentElement && node.parentElement.closest) button = node.parentElement.closest("button");
      if (!button) return;
      event.preventDefault();
      event.stopPropagation();
      var action = button.getAttribute("data-action");
      if (action === "previous" && handlers.onPrevious) handlers.onPrevious();
      if (action === "play-pause" && handlers.onToggle) handlers.onToggle();
      if (action === "next" && handlers.onNext) handlers.onNext();
    });
    return host;
  }

  function rememberHandlers(options) {
    options = options || {};
    handlers.onPrevious = options.onPrevious || null;
    handlers.onToggle = options.onToggle || null;
    handlers.onNext = options.onNext || null;
  }

  function discardHost() {
    if (currentHost && currentHost.parentNode) currentHost.parentNode.removeChild(currentHost);
    currentHost = null;
  }

  // Put the controls in the composer, or just above it. Does not move with replies.
  GV.mountTransport = function mountTransport(doc, options) {
    options = options || {};
    if (!doc) return null;
    ensureStyle(doc);
    rememberHandlers(options);
    var slot = GV.findComposerSlot(doc);
    if (slot.mode === "composer") {
      if (!currentHost || !currentHost.isConnected || currentHost.getAttribute("data-grok-voice-placement") !== "composer") {
        discardHost();
        currentHost = build(doc);
        currentHost.style.position = "relative";
      }
      if (currentHost.nextElementSibling !== slot.voice) {
        slot.voice.parentNode.insertBefore(currentHost, slot.voice);
      }
      currentHost.setAttribute("data-grok-voice-placement", "composer");
    } else if (slot.mode === "above") {
      if (!currentHost || !currentHost.isConnected || currentHost.getAttribute("data-grok-voice-placement") !== "above") {
        discardHost();
        currentHost = build(doc);
        (doc.documentElement || doc.body).appendChild(currentHost);
      }
      currentHost.setAttribute("data-grok-voice-placement", "above");
      currentTarget = slot.box;
      positionAbove(currentHost, slot.box);
    }
    if (currentHost) {
      currentHost.setAttribute("data-reading-id", options.readingId || "");
      paint(currentHost, options.mode || "stopped");
    }
    return currentHost;
  };

  GV.watchComposer = function watchComposer(doc, getOptions) {
    if (!doc || doc.__grokVoiceComposerWatch) return;
    doc.__grokVoiceComposerWatch = true;
    function sync() {
      GV.mountTransport(doc, getOptions ? getOptions() : {});
    }
    sync();
    var observer = new MutationObserver(function () { sync(); });
    var root = doc.documentElement || doc.body;
    if (root) observer.observe(root, { childList: true, subtree: true });
  };

  // Green outline only. The transport stays on the composer.
  GV.placeReadingControls = function placeReadingControls(doc, element, options) {
    options = options || {};
    if (!doc) return null;
    ensureStyle(doc);
    var marked = doc.querySelectorAll("." + READING_CLASS);
    for (var i = 0; i < marked.length; i++) marked[i].classList.remove(READING_CLASS);
    if (element) element.classList.add(READING_CLASS);
    options.readingId = element && element.id ? element.id : "";
    return GV.mountTransport(doc, options);
  };
})(globalThis);

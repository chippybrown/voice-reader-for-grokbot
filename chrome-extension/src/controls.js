// A small YouTube-style bar pinned over the reply that is being read.
// It is position:fixed, so it does not push the page around.
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
    return {
      previous: "Previous reply (" + (shortcuts.previous || "Alt+Left") + ")",
      play: "Play (" + (shortcuts.playPause || "Alt+Shift+P") + ")",
      pause: "Pause (" + (shortcuts.playPause || "Alt+Shift+P") + ")",
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

  function position(host, element) {
    if (!host || !element || !element.getBoundingClientRect) return;
    var rect = element.getBoundingClientRect();
    var top = rect.top + 8;
    var left = rect.left + 8;
    if (top < 8) top = 8;
    if (left < 8) left = 8;
    host.style.top = top + "px";
    host.style.left = left + "px";
  }

  function build(doc, options) {
    var tips = GV.controlTooltips();
    var host = doc.createElement("div");
    host.setAttribute("data-grok-voice-controls", "1");
    host.setAttribute("role", "toolbar");
    host.setAttribute("aria-label", "Reply playback");
    host.style.position = "fixed";
    host.style.zIndex = "2147483646";
    host.style.margin = "0";
    host.style.pointerEvents = "auto";
    var shadow = host.attachShadow({ mode: "open" });
    shadow.innerHTML =
      "<style>" +
      ":host{all:initial;}" +
      ".bar{display:flex;gap:2px;padding:2px;background:rgba(15,15,15,.9);border-radius:8px;box-shadow:0 1px 4px rgba(0,0,0,.45);}" +
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
    var view = doc.defaultView;
    if (view && !view.__grokVoiceControlsBound) {
      view.__grokVoiceControlsBound = true;
      view.addEventListener("scroll", function () { position(currentHost, currentTarget); }, true);
      view.addEventListener("resize", function () { position(currentHost, currentTarget); });
    }
    (doc.documentElement || doc.body).appendChild(host);
    return host;
  }

  // element is the bubble to outline. Pass null to remove the bar.
  GV.placeReadingControls = function placeReadingControls(doc, element, options) {
    options = options || {};
    if (!doc) return null;
    ensureStyle(doc);
    var marked = doc.querySelectorAll("." + READING_CLASS);
    for (var i = 0; i < marked.length; i++) marked[i].classList.remove(READING_CLASS);
    if (!element) {
      if (currentHost && currentHost.parentNode) currentHost.parentNode.removeChild(currentHost);
      currentHost = null;
      currentTarget = null;
      return null;
    }
    element.classList.add(READING_CLASS);
    handlers.onPrevious = options.onPrevious || null;
    handlers.onToggle = options.onToggle || null;
    handlers.onNext = options.onNext || null;
    if (!currentHost || !currentHost.isConnected) currentHost = build(doc, options);
    currentTarget = element;
    currentHost.setAttribute("data-reading-id", element.id || "");
    paint(currentHost, options.mode || "stopped");
    position(currentHost, element);
    return currentHost;
  };
})(globalThis);

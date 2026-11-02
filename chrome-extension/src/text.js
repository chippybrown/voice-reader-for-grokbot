// Visible-text and URL helpers shared by the content script and the badge.
(function (root) {
  "use strict";

  var GV = root.GrokVoice || (root.GrokVoice = {});

  function patternParts(pattern) {
    var match = /^(\*|https?):\/\/(\*|(?:\*\.)?[^/*]+)(\/.*)$/.exec(pattern);
    if (!match) return null;
    return { scheme: match[1], host: match[2], path: match[3] };
  }

  function hostMatches(pattern, hostname) {
    hostname = String(hostname || "").toLowerCase();
    pattern = String(pattern || "").toLowerCase();
    if (pattern === "*") return true;
    if (pattern.indexOf("*.") === 0) {
      var rest = pattern.slice(2);
      return hostname === rest || hostname.slice(-(rest.length + 1)) === "." + rest;
    }
    return hostname === pattern;
  }

  function pathMatches(pattern, pathname) {
    var escaped = String(pattern).replace(/[.+?^${}()|[\]\\]/g, "\\$&").replace(/\*/g, ".*");
    return new RegExp("^" + escaped + "$").test(pathname || "/");
  }

  // Chrome match-pattern check for http(s) URLs. The path is honored here.
  // host_permissions in the manifest do not honor the path; see config.js.
  GV.urlMatches = function urlMatches(url, patterns) {
    var list = patterns || GV.MATCHES || [];
    var parsed;
    try {
      parsed = new URL(url);
    } catch (err) {
      return false;
    }
    if (parsed.protocol !== "https:" && parsed.protocol !== "http:") return false;
    for (var i = 0; i < list.length; i++) {
      var parts = patternParts(list[i]);
      if (!parts) continue;
      if (parts.scheme !== "*" && parsed.protocol !== parts.scheme + ":") continue;
      if (!hostMatches(parts.host, parsed.hostname)) continue;
      if (pathMatches(parts.path, parsed.pathname || "/")) return true;
    }
    return false;
  };

  GV.patternValid = function patternValid(pattern) {
    return patternParts(pattern) !== null;
  };

  function isOnlyUrl(value) {
    return /^https?:\/\/\S+$/i.test(String(value || "").trim());
  }

  // Drop markdown punctuation and any URL, including a link written as
  // [label](https://...). The label stays. The address does not.
  GV.stripForSpeech = function stripForSpeech(text) {
    if (!text) return "";
    var value = String(text);
    value = value.replace(/```[a-zA-Z0-9_-]*\n?([\s\S]*?)```/g, function (_m, body) {
      return "\n" + (body || "") + "\n";
    });
    value = value.replace(/~~~[a-zA-Z0-9_-]*\n?([\s\S]*?)~~~/g, function (_m, body) {
      return "\n" + (body || "") + "\n";
    });
    value = value.replace(/!\[([^\]]*)\]\([^)]+\)/g, "$1");
    value = value.replace(/\[([^\]]+)\]\([^)]+\)/g, "$1");
    value = value.replace(/\[([^\]]+)\]\[[^\]]*\]/g, "$1");
    value = value.replace(/<https?:\/\/[^>\s]+>/gi, " ");
    value = value.replace(/https?:\/\/[^\s)]+/gi, " ");
    value = value.replace(/(^|\n)\s{0,3}#{1,6}\s+/g, "$1");
    value = value.replace(/(^|\n)\s{0,3}>\s?/g, "$1");
    value = value.replace(/(^|\n)\s*(?:[-*+]|\d+[.)])\s+/g, "$1");
    value = value.replace(/\*\*([^*]+)\*\*/g, "$1");
    value = value.replace(/__([^_]+)__/g, "$1");
    value = value.replace(/(^|[^\w])\*([^*\n]+)\*(?!\w)/g, "$1$2");
    value = value.replace(/(^|[^\w])_([^_\n]+)_(?!\w)/g, "$1$2");
    value = value.replace(/~~([^~]+)~~/g, "$1");
    value = value.replace(/`([^`]+)`/g, "$1");
    value = value.replace(/[*_~`#]/g, "");
    value = value.replace(/[\[\]]/g, "");
    value = value.replace(/\s+/g, " ").trim();
    return value;
  };

  function selectorList(name) {
    var selectors = (GV.SELECTORS && GV.SELECTORS[name]) || [];
    return selectors.filter(Boolean).join(", ");
  }

  function matchesAny(el, selector) {
    if (!selector) return false;
    try {
      return el.matches(selector);
    } catch (err) {
      return false;
    }
  }

  function shouldSkip(el) {
    var tag = el.tagName;
    if (tag === "SCRIPT" || tag === "STYLE" || tag === "NOSCRIPT" || tag === "SVG" ||
        tag === "IMG" || tag === "BUTTON" || tag === "TEXTAREA" || tag === "INPUT" ||
        tag === "SELECT" || tag === "CANVAS" || tag === "VIDEO" || tag === "AUDIO" ||
        tag === "IFRAME") {
      return true;
    }
    if (el.hidden) return true;
    if (el.getAttribute("aria-hidden") === "true") return true;
    if (el.closest("[hidden], [aria-hidden='true']")) return true;
    if (matchesAny(el, selectorList("skip"))) return true;
    var view = el.ownerDocument && el.ownerDocument.defaultView;
    if (!view || !view.getComputedStyle) return false;
    var style = view.getComputedStyle(el);
    if (!style) return false;
    if (style.display === "none" || style.visibility === "hidden") return true;
    if (Number(style.opacity) === 0) return true;
    return false;
  }

  // Marks a paragraph, list item, or other block the voice should pause at.
  var BOUNDARY = "\u0001";
  var SENTENCE = {
    P: 1, LI: 1, TR: 1, BLOCKQUOTE: 1, PRE: 1,
    H1: 1, H2: 1, H3: 1, H4: 1, H5: 1, H6: 1
  };

  function boxDisplay(el) {
    var view = el.ownerDocument && el.ownerDocument.defaultView;
    if (!view || !view.getComputedStyle) return "";
    try {
      var style = view.getComputedStyle(el);
      return style && style.display ? style.display : "";
    } catch (err) {
      return "";
    }
  }

  // Flex and grid items are separate boxes on screen. innerText puts a break
  // between them even when the markup has no space character.
  function isSeparatedBox(el) {
    var parent = el.parentElement;
    if (!parent) return false;
    var display = boxDisplay(parent);
    return display === "flex" || display === "inline-flex" || display === "grid" || display === "inline-grid";
  }

  function walk(node, parts) {
    if (!node) return;
    if (node.nodeType === 3) {
      var value = node.nodeValue || "";
      // Keep whitespace-only nodes. Streamdown puts the space between word
      // spans in its own text node, and dropping it glues the words together.
      if (!value || isOnlyUrl(value)) return;
      parts.push(value);
      return;
    }
    if (node.nodeType !== 1) return;
    if (shouldSkip(node)) return;
    if (node.tagName === "BR" || node.tagName === "HR") {
      parts.push(BOUNDARY);
      return;
    }
    var sentence = SENTENCE[node.tagName] === 1;
    if (sentence) parts.push(BOUNDARY);
    else if (isSeparatedBox(node)) parts.push(" ");
    var children = node.childNodes;
    for (var i = 0; i < children.length; i++) walk(children[i], parts);
    if (sentence) parts.push(BOUNDARY);
  }

  function endsWithPause(text) {
    return /[.!?…]["')\]]*$/.test(text);
  }

  // Join visible chunks. A chunk that does not already end a sentence gets a
  // period so speech pauses between paragraphs and list items.
  GV.speakableJoin = function speakableJoin(parts) {
    var out = [];
    var i;
    for (i = 0; i < parts.length; i++) {
      var text = String(parts[i] || "").replace(/\s+/g, " ").trim();
      if (!text) continue;
      if (out.length && !endsWithPause(out[out.length - 1])) out[out.length - 1] += ".";
      out.push(text);
    }
    return out.join(" ");
  };

  function speechFromParts(parts) {
    var chunks = parts.join("").split(BOUNDARY);
    var spoken = [];
    for (var i = 0; i < chunks.length; i++) {
      var text = GV.stripForSpeech(chunks[i]);
      if (text) spoken.push(text);
    }
    return GV.speakableJoin(spoken);
  }

  // Words a person can see. Link addresses, hidden nodes, and markdown
  // marks are left out. href is never read. Spacing matches the screen.
  GV.visibleSpeech = function visibleSpeech(root) {
    if (!root || root.nodeType !== 1) return "";
    if (shouldSkip(root)) return "";
    var parts = [];
    var children = root.childNodes;
    for (var i = 0; i < children.length; i++) walk(children[i], parts);
    return speechFromParts(parts);
  };

  GV.visibleRaw = function visibleRaw(root) {
    if (!root || root.nodeType !== 1) return "";
    if (shouldSkip(root)) return "";
    var parts = [];
    var children = root.childNodes;
    for (var i = 0; i < children.length; i++) walk(children[i], parts);
    return parts.join("").replace(new RegExp(BOUNDARY, "g"), " ").replace(/\s+/g, " ").trim();
  };
})(globalThis);

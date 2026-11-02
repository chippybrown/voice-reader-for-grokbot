// Find assistant replies without relying on a data-testid.
// Primary: Streamdown blocks grouped into one bubble.
// A purple or right-aligned bubble is the person's, even if it also uses
// Streamdown. Fallback: colored bubbles in the scrolling message list.
(function (root) {
  "use strict";

  var GV = root.GrokVoice || (root.GrokVoice = {});
  var CONTENT_TAG = {
    P: 1, UL: 1, OL: 1, PRE: 1, TABLE: 1, BLOCKQUOTE: 1,
    H1: 1, H2: 1, H3: 1, H4: 1, H5: 1, H6: 1
  };

  function mark() {
    return String(GV.STREAMDOWN_MARK || "streamdown").toLowerCase();
  }

  function classText(el) {
    if (!el || el.className == null) return "";
    return typeof el.className === "string" ? el.className : "";
  }

  function hasStreamdown(el) {
    return classText(el).toLowerCase().indexOf(mark()) !== -1;
  }

  function styleOf(el) {
    var view = el.ownerDocument && el.ownerDocument.defaultView;
    if (!view || !view.getComputedStyle) return null;
    try {
      return view.getComputedStyle(el);
    } catch (err) {
      return null;
    }
  }

  function parseRgb(color) {
    var match = /rgba?\(\s*(\d+)[,\s]+(\d+)[,\s]+(\d+)/.exec(color || "");
    if (!match) return null;
    var alpha = 1;
    if (color.indexOf("rgba") === 0) {
      var parts = color.split(",");
      alpha = parseFloat(parts[parts.length - 1]);
      if (!isFinite(alpha)) alpha = 1;
    }
    return { r: +match[1], g: +match[2], b: +match[3], a: alpha };
  }

  function isPurple(color) {
    var c = parseRgb(color);
    if (!c || c.a === 0) return false;
    return c.b > 120 && c.r > 70 && c.b > c.g + 40 && c.r > c.g + 20;
  }

  function hasOwnBackground(el) {
    var style = styleOf(el);
    if (!style) return false;
    var c = parseRgb(style.backgroundColor);
    return Boolean(c && c.a !== 0);
  }

  function ignored(el) {
    if (!el || el.nodeType !== 1) return true;
    var tag = el.tagName;
    if (tag === "TEXTAREA" || tag === "INPUT" || tag === "SELECT" || tag === "BUTTON") return true;
    if (el.isContentEditable) return true;
    var role = (el.getAttribute("role") || "").toLowerCase();
    if (role === "menu" || role === "menuitem" || role === "tooltip" || role === "listbox") return true;
    try {
      if (el.closest("textarea, input, select, button, [role='menu'], [role='menuitem'], [role='tooltip'], [role='listbox'], [contenteditable='true']")) {
        return true;
      }
    } catch (err) {
      return false;
    }
    return false;
  }

  function deepElements(node) {
    var out = [];
    function visit(rootNode) {
      if (!rootNode || !rootNode.querySelectorAll) return;
      var all = rootNode.querySelectorAll("*");
      for (var i = 0; i < all.length; i++) {
        out.push(all[i]);
        if (all[i].shadowRoot) visit(all[i].shadowRoot);
      }
    }
    visit(node);
    return out;
  }

  function isScrollList(el) {
    if (!el || !el.ownerDocument) return false;
    var doc = el.ownerDocument;
    if (el === doc.body || el === doc.documentElement) return false;
    var style = styleOf(el);
    if (!style) return false;
    var overflow = style.overflowY;
    if (overflow !== "auto" && overflow !== "scroll" && overflow !== "overlay") return false;
    var rect = el.getBoundingClientRect();
    return rect.width >= 180 && rect.height >= 80;
  }

  function findMessageList(doc) {
    var body = doc.body || doc.documentElement;
    if (!body) return null;
    var elements = deepElements(body);
    var best = null;
    var bestScore = -1;
    for (var i = 0; i < elements.length; i++) {
      var el = elements[i];
      if (!isScrollList(el)) continue;
      var count = 0;
      try {
        count = el.querySelectorAll('[class*="' + mark() + '"]').length;
      } catch (err) {
        count = 0;
      }
      var rect = el.getBoundingClientRect();
      var score = count * 1000 + rect.height;
      if (score > bestScore) {
        best = el;
        bestScore = score;
      }
    }
    return best;
  }

  function containsStreamdown(el) {
    if (hasStreamdown(el)) return true;
    try {
      return Boolean(el.querySelector('[class*="' + mark() + '"]'));
    } catch (err) {
      return false;
    }
  }

  function isContentBlock(el) {
    return CONTENT_TAG[el.tagName] === 1;
  }

  // Two Streamdown paragraphs inside one bubble are one reply.
  // Two row wrappers that each contain Streamdown are two messages.
  function separatesMessages(parent) {
    var kids = [];
    var children = parent.children;
    for (var i = 0; i < children.length; i++) {
      if (containsStreamdown(children[i])) kids.push(children[i]);
    }
    if (kids.length < 2) return false;
    for (var j = 0; j < kids.length; j++) {
      if (!isContentBlock(kids[j])) return true;
    }
    return false;
  }

  function bubbleFor(block, list) {
    var node = block;
    var shaded = hasOwnBackground(block) ? block : null;
    var doc = block.ownerDocument;
    var guard = 0;
    while (node.parentElement && guard < 24) {
      guard += 1;
      var parent = node.parentElement;
      if (parent === doc.body || parent === doc.documentElement) break;
      if ((list && parent === list) || separatesMessages(parent) || isScrollList(parent)) break;
      node = parent;
      if (hasOwnBackground(node)) shaded = node;
    }
    if (shaded && shaded.contains(block)) return shaded;
    return node;
  }

  function streamdownBlocks(rootNode) {
    var found = [];
    var elements = deepElements(rootNode);
    for (var i = 0; i < elements.length; i++) {
      var el = elements[i];
      if (!hasStreamdown(el) || ignored(el)) continue;
      if (el.parentElement && hasStreamdown(el.parentElement)) continue;
      found.push(el);
    }
    return found;
  }

  function attrRole(el) {
    var keys = ["data-message-author-role", "data-role", "data-author", "data-message-role"];
    var i;
    for (i = 0; i < keys.length; i++) {
      var value = (el.getAttribute(keys[i]) || "").toLowerCase();
      if (value === "user" || value === "human") return "user";
      if (value === "assistant" || value === "bot" || value === "model" || value === "grok") return "assistant";
    }
    var label = (el.getAttribute("aria-label") || "").toLowerCase();
    if (/\b(user|you)\b/.test(label) && !/assistant|\bbot\b/.test(label)) return "user";
    if (/assistant|\bbot\b|\bgrok\b/.test(label)) return "assistant";
    var cls = classText(el).toLowerCase();
    if (/(\buser\b|user-message|from-user)/.test(cls) && cls.indexOf("assistant") === -1) return "user";
    if (/assistant|bot-message|model-message/.test(cls)) return "assistant";
    return "";
  }

  function pushedToEnd(el, container) {
    var bounds = container && container.getBoundingClientRect ? container : el.ownerDocument.documentElement;
    var box = el.getBoundingClientRect();
    var frame = bounds.getBoundingClientRect();
    if (box.width < 2 || frame.width < 2) return false;
    var leftGap = box.left - frame.left;
    var rightGap = frame.right - box.right;
    return rightGap + 16 < leftGap && box.width < frame.width * 0.92;
  }

  function isUserStyled(el, container) {
    var node = el;
    var guard = 0;
    while (node && node.nodeType === 1 && guard < 12) {
      guard += 1;
      if (container && node === container) break;
      var role = attrRole(node);
      if (role === "user") return true;
      if (role === "assistant") return false;
      var style = styleOf(node);
      if (style) {
        var justify = style.justifyContent;
        if (justify === "flex-end" || justify === "end" || style.alignSelf === "flex-end") return true;
        if (isPurple(style.backgroundColor)) return true;
      }
      if (pushedToEnd(node, container)) return true;
      node = node.parentElement;
    }
    return false;
  }

  function hasInnerBubble(el) {
    var text = GV.visibleRaw(el);
    if (!text) return false;
    var nodes = el.querySelectorAll("*");
    for (var i = 0; i < nodes.length; i++) {
      var child = nodes[i];
      if (ignored(child) || !hasOwnBackground(child)) continue;
      var inner = GV.visibleRaw(child);
      if (inner && inner.length >= 8 && inner.length < text.length * 0.9) return true;
    }
    return false;
  }

  function fallbackBubbles(doc, list) {
    var rootNode = list || doc.body;
    if (!rootNode) return [];
    var elements = deepElements(rootNode);
    var hits = [];
    var bounds = rootNode.getBoundingClientRect();
    for (var i = 0; i < elements.length; i++) {
      var el = elements[i];
      if (ignored(el) || !hasOwnBackground(el)) continue;
      if (!GV.visibleRaw(el)) continue;
      var rect = el.getBoundingClientRect();
      if (bounds.height && rect.height > bounds.height * 0.92 && rect.width > bounds.width * 0.92) continue;
      if (hasInnerBubble(el)) continue;
      if (isUserStyled(el, rootNode)) continue;
      hits.push(el);
    }
    return hits;
  }

  // Assistant bubbles in document order. Each entry is one reply.
  GV.detectAssistantElements = function detectAssistantElements(doc) {
    var body = doc.body || doc.documentElement;
    if (!body) return [];
    var list = findMessageList(doc);
    var blocks = streamdownBlocks(list || body);
    if (!blocks.length) return fallbackBubbles(doc, list);
    var seen = new Set();
    var bubbles = [];
    for (var i = 0; i < blocks.length; i++) {
      var bubble = bubbleFor(blocks[i], list);
      if (!bubble || seen.has(bubble) || ignored(bubble)) continue;
      seen.add(bubble);
      if (isUserStyled(bubble, list || body)) continue;
      if (!GV.visibleRaw(bubble)) continue;
      bubbles.push(bubble);
    }
    return bubbles;
  };

  GV.elementPath = function elementPath(el) {
    var parts = [];
    var node = el;
    while (node && node.nodeType === 1 && parts.length < 8) {
      var name = node.tagName.toLowerCase();
      if (node.id) {
        parts.unshift(name + "#" + node.id);
        break;
      }
      var cls = classText(node).trim().split(/\s+/).filter(Boolean).slice(0, 2);
      if (cls.length) name += "." + cls.join(".");
      var parent = node.parentElement;
      if (parent) {
        var same = [];
        var children = parent.children;
        for (var i = 0; i < children.length; i++) {
          if (children[i].tagName === node.tagName) same.push(children[i]);
        }
        if (same.length > 1) name += ":nth-of-type(" + (same.indexOf(node) + 1) + ")";
      }
      parts.unshift(name);
      node = parent;
    }
    return parts.join(" > ");
  };
})(globalThis);

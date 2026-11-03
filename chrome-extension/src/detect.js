// Assistant replies are the Streamdown blocks of the last bot message.
// The name label, timestamp, and buttons sit outside that markdown and are
// not spoken. A purple or right-aligned bubble is the person's, even when
// it uses the same renderer.
(function (root) {
  "use strict";

  var GV = root.GrokVoice || (root.GrokVoice = {});
  var EXTRA_TAG = { UL: 1, OL: 1, PRE: 1, TABLE: 1, BLOCKQUOTE: 1, H1: 1, H2: 1, H3: 1, H4: 1, H5: 1, H6: 1 };

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
    if (String(color).indexOf("rgba") === 0) {
      var parts = String(color).split(",");
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

  function isStreamdownParagraph(el) {
    return el && el.tagName === "P" && el.getAttribute("dir") === "auto" && hasStreamdown(el);
  }

  function isContentBlock(el) {
    return isStreamdownParagraph(el) || EXTRA_TAG[el.tagName] === 1;
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

  function containsStreamdownParagraph(el) {
    if (isStreamdownParagraph(el)) return true;
    try {
      var nodes = el.querySelectorAll("p[dir='auto']");
      for (var i = 0; i < nodes.length; i++) {
        if (hasStreamdown(nodes[i])) return true;
      }
    } catch (err) {
      return false;
    }
    return false;
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
        var paras = el.querySelectorAll("p[dir='auto']");
        for (var j = 0; j < paras.length; j++) {
          if (hasStreamdown(paras[j])) count += 1;
        }
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

  // Sibling paragraphs are one reply. Sibling message rows are not.
  function separatesIntoDistinctMessages(parent) {
    var groups = [];
    var children = parent.children;
    var i;
    for (i = 0; i < children.length; i++) {
      if (containsStreamdownParagraph(children[i])) groups.push(children[i]);
    }
    if (groups.length < 2) return false;
    for (i = 0; i < groups.length; i++) {
      if (!isContentBlock(groups[i])) return true;
    }
    return false;
  }

  function plainText(el) {
    try {
      return String(el.innerText || el.textContent || "").replace(/\s+/g, " ").trim();
    } catch (err) {
      return "";
    }
  }

  // A name, timestamp, or button next to the markdown means this parent is
  // the message shell, not the body.
  function hasForeignLabel(parent) {
    var children = parent.children;
    for (var i = 0; i < children.length; i++) {
      var child = children[i];
      if (isContentBlock(child) || containsStreamdownParagraph(child)) continue;
      if (child.tagName === "BUTTON") return true;
      if (child.querySelector && child.querySelector("button")) return true;
      if (plainText(child)) return true;
    }
    return false;
  }

  function hasMessageFromLabel(el) {
    if (!el || el.nodeType !== 1) return false;
    var text = plainText(el);
    if (/^Message from\b/i.test(text) && text.length < 240) return true;
    if (el.children && el.children.length && el.children.length < 8) {
      var nodes = el.querySelectorAll("*");
      for (var i = 0; i < nodes.length && i < 16; i++) {
        var inner = plainText(nodes[i]);
        if (/^Message from\b/i.test(inner) && inner.length < 240) return true;
      }
    }
    return false;
  }

  // Another assistant or user bubble, or a "Message from …" row, means this
  // parent holds several messages. Sibling paragraphs in one bubble do not.
  function boundaryParent(parent, branch) {
    var children = parent.children;
    for (var i = 0; i < children.length; i++) {
      var child = children[i];
      if (child === branch || child.contains(branch)) continue;
      if (isContentBlock(child)) continue;
      if (containsStreamdownParagraph(child)) return true;
      if (hasMessageFromLabel(child)) return true;
    }
    return false;
  }

  function messageRowOf(block, list) {
    var node = block;
    var doc = block.ownerDocument;
    var guard = 0;
    while (node.parentElement && guard < 30) {
      guard += 1;
      var parent = node.parentElement;
      if (parent === doc.body || parent === doc.documentElement) break;
      if (list && parent === list) break;
      if (boundaryParent(parent, node) || separatesIntoDistinctMessages(parent)) break;
      if (isScrollList(parent) && boundaryParent(parent, node)) break;
      node = parent;
    }
    return node;
  }

  function markdownBox(block) {
    var node = block;
    var doc = block.ownerDocument;
    var guard = 0;
    while (node.parentElement && guard < 24) {
      guard += 1;
      var parent = node.parentElement;
      if (parent === doc.body || parent === doc.documentElement) break;
      if (hasForeignLabel(parent) || separatesIntoDistinctMessages(parent) || isScrollList(parent)) break;
      node = parent;
    }
    return node;
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

  function parentHasOtherMessages(parent, branch) {
    var children = parent.children;
    for (var i = 0; i < children.length; i++) {
      var child = children[i];
      if (child === branch || child.contains(branch)) continue;
      if (isContentBlock(child)) continue;
      if (containsStreamdownParagraph(child)) return true;
      try {
        if (child.querySelector && child.querySelector('p[dir="auto"]')) return true;
      } catch (err) {
        // Ignore a node that cannot be queried.
      }
    }
    return false;
  }

  // The message root is the nearest ancestor that still holds only this
  // message. Stop when the parent also holds another message.
  function messageRoot(paragraph) {
    var node = paragraph;
    var doc = paragraph.ownerDocument;
    var guard = 0;
    while (node.parentElement && guard < 30) {
      guard += 1;
      var parent = node.parentElement;
      if (parent === doc.body || parent === doc.documentElement) break;
      if (parentHasOtherMessages(parent, node)) break;
      node = parent;
    }
    return node;
  }

  function coloredBox(paragraph, root) {
    var node = paragraph;
    var shaded = null;
    while (node) {
      if (node !== paragraph && hasOwnBackground(node)) shaded = node;
      if (node === root) break;
      node = node.parentElement;
    }
    return shaded || root;
  }

  function isDarkGray(color) {
    var c = parseRgb(color);
    if (!c || c.a === 0) return false;
    var max = Math.max(c.r, c.g, c.b);
    var min = Math.min(c.r, c.g, c.b);
    return max < 90 && max - min < 30;
  }

  // User only when THIS bubble is purple, or its own wrapper (not the chat
  // column above it) is justify-end / margin-left auto. Anything else is assistant.
  function classifyBubble(paragraph) {
    var root = messageRoot(paragraph);
    var box = coloredBox(paragraph, root);
    var style = styleOf(box);
    if (style && isPurple(style.backgroundColor)) {
      return { role: "user", reason: "bubble-purple", bubble: box, root: root };
    }
    if (style && (style.alignSelf === "flex-end" || style.alignSelf === "end")) {
      return { role: "user", reason: "bubble-align-end", bubble: box, root: root };
    }
    var wrapper = box.parentElement;
    if (wrapper && !parentHasOtherMessages(wrapper, box)) {
      var wrapperStyle = styleOf(wrapper);
      if (wrapperStyle && (wrapperStyle.justifyContent === "flex-end" || wrapperStyle.justifyContent === "end")) {
        return { role: "user", reason: "wrapper-justify-end", bubble: box, root: root };
      }
      if (pushedToEnd(box, wrapper)) {
        return { role: "user", reason: "bubble-right-aligned", bubble: box, root: root };
      }
    }
    if (style && isDarkGray(style.backgroundColor)) {
      return { role: "assistant", reason: "bubble-dark-gray", bubble: box, root: root };
    }
    return { role: "assistant", reason: "uncertain", bubble: box, root: root };
  }

  function nearestBubble(paragraph) {
    var node = paragraph;
    var shaded = null;
    var doc = paragraph.ownerDocument;
    var guard = 0;
    while (node.parentElement && guard < 30) {
      guard += 1;
      var parent = node.parentElement;
      if (parent === doc.body || parent === doc.documentElement) break;
      if (boundaryParent(parent, node) || separatesIntoDistinctMessages(parent)) break;
      node = parent;
      if (!shaded && hasOwnBackground(node)) shaded = node;
    }
    if (shaded && shaded.contains(paragraph)) return shaded;
    return node;
  }

  function hasOwnBackground(el) {
    var style = styleOf(el);
    if (!style) return false;
    var parsed = parseRgb(style.backgroundColor);
    return Boolean(parsed && parsed.a !== 0);
  }

  function includeBlock(el, row) {
    if (!el || ignored(el)) return false;
    if (el.tagName === "P") {
      var dir = (el.getAttribute("dir") || "").toLowerCase();
      return dir === "auto" && plainText(el).length > 0;
    }
    if (!EXTRA_TAG[el.tagName]) return false;
    var box = markdownBox(el);
    var paras = row.querySelectorAll("p[dir='auto']");
    for (var i = 0; i < paras.length; i++) {
      if (!hasStreamdown(paras[i])) continue;
      if (markdownBox(paras[i]) === box) return true;
    }
    return false;
  }

  // Spoken words of one assistant message: Streamdown paragraphs plus lists,
  // headings, and tables in that same markdown box. Name labels are not blocks.
  GV.replySpeech = function replySpeech(row) {
    if (!row || !row.querySelectorAll) return "";
    var nodes = row.querySelectorAll("p, ul, ol, pre, blockquote, h1, h2, h3, h4, h5, h6, table");
    var blocks = [];
    var i;
    for (i = 0; i < nodes.length; i++) {
      var el = nodes[i];
      if (!includeBlock(el, row)) continue;
      var nested = false;
      var j;
      for (j = 0; j < blocks.length; j++) {
        if (blocks[j].contains(el)) nested = true;
      }
      if (nested) continue;
      blocks = blocks.filter(function (other) { return !el.contains(other); });
      blocks.push(el);
    }
    var parts = [];
    for (i = 0; i < blocks.length; i++) {
      var text = GV.visibleSpeech(blocks[i]);
      if (text) parts.push(text);
    }
    return GV.speakableJoin(parts);
  };

  function collectParagraphs(rootNode, found, selector) {
    if (!rootNode || !rootNode.querySelectorAll) return;
    var nodes = [];
    try {
      nodes = rootNode.querySelectorAll(selector);
    } catch (err) {
      nodes = [];
    }
    var i;
    for (i = 0; i < nodes.length; i++) {
      if (!ignored(nodes[i]) && GV.visibleRaw(nodes[i])) found.push(nodes[i]);
    }
    var all = [];
    try {
      all = rootNode.querySelectorAll("*");
    } catch (err) {
      all = [];
    }
    for (i = 0; i < all.length; i++) {
      if (all[i].shadowRoot) collectParagraphs(all[i].shadowRoot, found, selector);
    }
  }

  // Every matching paragraph in this frame, including open shadow roots.
  // Streamdown is preferred. If that matches nothing, p[dir=auto] bubbles are used.
  GV.inspectAssistant = function inspectAssistant(doc) {
    var body = doc.body || doc.documentElement;
    var empty = { blockCount: 0, replies: [], mode: "streamdown" };
    if (!body) return empty;
    var paragraphs = [];
    collectParagraphs(body, paragraphs, 'p[dir="auto"][class*="streamdown"]');
    var mode = "streamdown";
    if (!paragraphs.length) {
      mode = "fallback";
      collectParagraphs(body, paragraphs, 'p[dir="auto"]');
    }
    var seen = new Set();
    var groups = [];
    var replies = [];
    var i;
    for (i = 0; i < paragraphs.length; i++) {
      var info = classifyBubble(paragraphs[i]);
      var key = info.root || info.bubble;
      if (!key || seen.has(key)) continue;
      seen.add(key);
      var speech = GV.replySpeech(key);
      if (!speech) continue;
      var group = {
        role: info.role,
        reason: info.reason,
        speech: speech,
        element: key,
        body: info.bubble || key
      };
      groups.push(group);
      if (info.role !== "user") {
        replies.push({
          element: group.element,
          body: group.body,
          speech: speech,
          raw: speech,
          reason: info.reason
        });
      }
    }
    replies.sort(function (a, b) {
      if (!a.element || !b.element || a.element === b.element) return 0;
      var pos = a.element.compareDocumentPosition(b.element);
      if (pos & 4) return -1;
      if (pos & 2) return 1;
      return 0;
    });
    return {
      blockCount: paragraphs.length,
      replies: replies,
      groups: groups,
      mode: mode
    };
  };

  GV.detectAssistantReplies = function detectAssistantReplies(doc) {
    return GV.inspectAssistant(doc).replies;
  };

  GV.latestAssistantReply = function latestAssistantReply(doc) {
    var replies = GV.detectAssistantReplies(doc);
    return replies.length ? replies[replies.length - 1] : null;
  };

  function elementFrom(node) {
    if (!node) return null;
    if (node.nodeType === 1) return node;
    if (node.nodeType === 3 || node.nodeType === 8) return node.parentElement || null;
    return null;
  }

  function inReadingControls(el) {
    try {
      return Boolean(el.closest && el.closest("[data-grok-voice-controls]"));
    } catch (err) {
      return false;
    }
  }

  function inComposer(el) {
    if (!el || el.nodeType !== 1) return false;
    var tag = el.tagName;
    if (tag === "TEXTAREA" || tag === "INPUT" || tag === "SELECT") return true;
    if (el.isContentEditable) return true;
    var role = (el.getAttribute("role") || "").toLowerCase();
    if (role === "textbox" || role === "searchbox") return true;
    try {
      return Boolean(el.closest("textarea, input, select, [contenteditable='true'], [contenteditable='plaintext-only'], [role='textbox'], [role='searchbox']"));
    } catch (err) {
      return false;
    }
  }

  // A user bubble's own edits are not a new assistant reply. A column that
  // also holds other messages is not itself a user bubble.
  function inUserBubble(el) {
    if (!el || el.nodeType !== 1) return false;
    var node = el;
    var guard = 0;
    while (node && node.nodeType === 1 && guard < 12) {
      if (node.tagName === "P" && (node.getAttribute("dir") || "").toLowerCase() === "auto") {
        return classifyBubble(node).role === "user";
      }
      node = node.parentElement;
      guard += 1;
    }
    if (!el.querySelectorAll) return false;
    var paras = [];
    try {
      paras = el.querySelectorAll('p[dir="auto"]');
    } catch (err) {
      return false;
    }
    if (paras.length !== 1) return false;
    return classifyBubble(paras[0]).role === "user";
  }

  // Typing in the composer, or a change inside a user bubble, is not a new reply.
  GV.ignoreMutation = function ignoreMutation(record) {
    if (!record) return false;
    var nodes = [record.target];
    var added = record.addedNodes;
    if (added) {
      for (var i = 0; i < added.length; i++) nodes.push(added[i]);
    }
    var saw = false;
    for (var n = 0; n < nodes.length; n++) {
      var el = elementFrom(nodes[n]);
      if (!el) continue;
      saw = true;
      if (!inComposer(el) && !inUserBubble(el) && !inReadingControls(el)) return false;
    }
    return saw;
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

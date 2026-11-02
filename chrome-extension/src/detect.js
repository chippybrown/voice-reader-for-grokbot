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

  function includeBlock(el, row) {
    if (!el || ignored(el)) return false;
    if (el.tagName === "P") return isStreamdownParagraph(el);
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
    return parts.join(" ");
  };

  function streamdownParagraphs(rootNode) {
    var found = [];
    var elements = deepElements(rootNode);
    for (var i = 0; i < elements.length; i++) {
      var el = elements[i];
      if (isStreamdownParagraph(el) && !ignored(el)) found.push(el);
    }
    return found;
  }

  function textBetween(before, after) {
    try {
      var range = before.ownerDocument.createRange();
      range.setStartAfter(before);
      range.setEndBefore(after);
      return range.toString();
    } catch (err) {
      return "";
    }
  }

  // Paragraphs are in document order. A "Message from …" row between two
  // bubbles starts a new message even if they share a wrapper.
  function clusterParagraphs(paragraphs, list) {
    var clusters = [];
    for (var i = 0; i < paragraphs.length; i++) {
      var paragraph = paragraphs[i];
      var previous = clusters.length ? clusters[clusters.length - 1] : null;
      var lastParagraph = previous ? previous.paragraphs[previous.paragraphs.length - 1] : null;
      var split = !previous || /Message from\b/i.test(textBetween(lastParagraph, paragraph));
      if (!split) {
        var left = messageRowOf(lastParagraph, list);
        var right = messageRowOf(paragraph, list);
        if (left !== right && !left.contains(paragraph) && !right.contains(lastParagraph)) split = true;
      }
      if (split) clusters.push({ paragraphs: [paragraph] });
      else previous.paragraphs.push(paragraph);
    }
    return clusters;
  }

  function speechOfCluster(paragraphs) {
    var wanted = new Set();
    var boxes = [];
    var i;
    for (i = 0; i < paragraphs.length; i++) {
      wanted.add(paragraphs[i]);
      var box = markdownBox(paragraphs[i]);
      if (boxes.indexOf(box) === -1) boxes.push(box);
    }
    var parts = [];
    for (i = 0; i < boxes.length; i++) {
      var nodes = boxes[i].querySelectorAll("p, ul, ol, pre, blockquote, h1, h2, h3, h4, h5, h6, table");
      var blocks = [];
      var n;
      for (n = 0; n < nodes.length; n++) {
        var el = nodes[n];
        if (el.tagName === "P") {
          if (!wanted.has(el)) continue;
        } else if (!EXTRA_TAG[el.tagName] || ignored(el)) continue;
        var nested = false;
        var j;
        for (j = 0; j < blocks.length; j++) {
          if (blocks[j].contains(el)) nested = true;
        }
        if (nested) continue;
        blocks = blocks.filter(function (other) { return !el.contains(other); });
        blocks.push(el);
      }
      for (n = 0; n < blocks.length; n++) {
        var text = GV.visibleSpeech(blocks[n]);
        if (text) parts.push(text);
      }
    }
    return parts.join(" ");
  }

  // Replies in document order, top to bottom. The last entry is the one to read.
  // Nothing here is cached: callers resolve it again after every mutation.
  GV.detectAssistantReplies = function detectAssistantReplies(doc) {
    var body = doc.body || doc.documentElement;
    if (!body) return [];
    var list = findMessageList(doc);
    var all = streamdownParagraphs(body);
    var paragraphs = all;
    if (list) {
      var inside = [];
      for (var n = 0; n < all.length; n++) {
        if (list.contains(all[n])) inside.push(all[n]);
      }
      if (inside.length && inside.length === all.length) paragraphs = inside;
    }
    var kept = [];
    for (var i = 0; i < paragraphs.length; i++) {
      if (!isUserStyled(paragraphs[i], list || body)) kept.push(paragraphs[i]);
    }
    var clusters = clusterParagraphs(kept, list);
    var replies = [];
    for (i = 0; i < clusters.length; i++) {
      var group = clusters[i].paragraphs;
      var speech = speechOfCluster(group);
      if (!speech) continue;
      var box = markdownBox(group[0]);
      replies.push({
        element: box,
        body: box,
        speech: speech,
        raw: speech
      });
    }
    replies.sort(function (a, b) {
      if (!a.element || !b.element || a.element === b.element) return 0;
      var pos = a.element.compareDocumentPosition(b.element);
      if (pos & 4) return -1;
      if (pos & 2) return 1;
      return 0;
    });
    return replies;
  };

  GV.latestAssistantReply = function latestAssistantReply(doc) {
    var replies = GV.detectAssistantReplies(doc);
    return replies.length ? replies[replies.length - 1] : null;
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

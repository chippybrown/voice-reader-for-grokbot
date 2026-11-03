// One voice and one auto-read choice per bot. A bot without its own voice
// uses the default. A bot that is not checked is skipped for automatic
// reading and still plays from Previous, Next, and Replay.
(function (root) {
  "use strict";

  var GV = root.GrokVoice || (root.GrokVoice = {});

  function clean(value) {
    return String(value || "").replace(/\s+/g, " ").trim();
  }

  GV.botFromLocation = function botFromLocation(href, label) {
    var id = "";
    try {
      var url = new URL(String(href || ""));
      var match = /\/bot\/([^/?#]+)/.exec(url.pathname || "");
      if (match) id = decodeURIComponent(match[1]);
    } catch (err) {
      id = "";
    }
    var name = clean(label);
    if (name) name = name.split(/\s+[-|–—]\s+/)[0].trim();
    if (/^grok$/i.test(name)) name = "";
    if (!id) id = name || "default";
    if (!name) name = id === "default" ? "Grok" : id;
    return { id: id, name: name };
  };

  GV.botLabel = function botLabel(doc) {
    var header = "";
    try {
      var node = doc && doc.querySelector ? doc.querySelector("h1") : null;
      if (node) header = clean(node.textContent);
    } catch (err) {
      header = "";
    }
    if (header && header.length <= 80) return header;
    return doc && doc.title ? clean(doc.title) : "";
  };

  function recordFor(stored, identity) {
    var bots = stored && stored.bots ? stored.bots : {};
    var current = bots[identity.id];
    var allowNew = !stored || stored.newBotsAutoRead !== false;
    return {
      name: identity.name || (current && current.name) || identity.id,
      voiceURI: current && current.voiceURI ? String(current.voiceURI) : "",
      autoRead: current ? current.autoRead !== false : allowNew
    };
  }

  GV.botSettingsFor = function botSettingsFor(stored, identity) {
    return recordFor(stored || {}, identity || { id: "default", name: "Grok" });
  };

  GV.rememberBot = function rememberBot(stored, identity) {
    var bots = {};
    var source = stored && stored.bots ? stored.bots : {};
    var key;
    for (key in source) {
      if (Object.prototype.hasOwnProperty.call(source, key)) bots[key] = source[key];
    }
    bots[identity.id] = recordFor(stored || {}, identity);
    return bots;
  };

  GV.botVoiceURI = function botVoiceURI(stored, identity) {
    var record = recordFor(stored || {}, identity || { id: "default", name: "Grok" });
    if (record.voiceURI) return record.voiceURI;
    return stored && stored.voiceURI ? String(stored.voiceURI) : "";
  };

  GV.botAutoRead = function botAutoRead(stored, identity) {
    return recordFor(stored || {}, identity || { id: "default", name: "Grok" }).autoRead !== false;
  };
})(globalThis);

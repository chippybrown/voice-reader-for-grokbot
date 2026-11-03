// Decide whether a GitHub release is a newer extension build.
// Tags that do not start with ext-v are ignored. Prereleases are ignored
// unless the beta switch is on. Drafts are ignored.
(function (root) {
  "use strict";

  var GV = root.GrokVoice || (root.GrokVoice = {});

  GV.parseExtensionVersion = function parseExtensionVersion(tag) {
    var raw = String(tag || "").trim();
    if (raw.indexOf("ext-v") === 0) raw = raw.slice(5);
    else if (raw.charAt(0) === "v" || raw.charAt(0) === "V") raw = raw.slice(1);
    if (!/^\d+(?:\.\d+){0,3}$/.test(raw)) return null;
    return raw.split(".").map(function (part) { return parseInt(part, 10); });
  };

  GV.compareVersions = function compareVersions(left, right) {
    var length = Math.max(left.length, right.length);
    for (var i = 0; i < length; i++) {
      var a = left[i] || 0;
      var b = right[i] || 0;
      if (a !== b) return a > b ? 1 : -1;
    }
    return 0;
  };

  GV.pickExtensionUpdate = function pickExtensionUpdate(releases, current, options) {
    var beta = Boolean(options && options.beta);
    var currentParts = GV.parseExtensionVersion(current);
    if (!currentParts) currentParts = GV.parseExtensionVersion("ext-v" + current);
    if (!currentParts) currentParts = [0];
    var best = null;
    var bestParts = currentParts;
    var list = releases || [];
    for (var i = 0; i < list.length; i++) {
      var release = list[i];
      if (!release || release.draft) continue;
      if (release.prerelease && !beta) continue;
      var tag = String(release.tag_name || "");
      if (tag.indexOf("ext-v") !== 0) continue;
      var parts = GV.parseExtensionVersion(tag);
      if (!parts) continue;
      if (GV.compareVersions(parts, bestParts) > 0) {
        best = release;
        bestParts = parts;
      }
    }
    if (!best) return null;
    var url = best.html_url || "";
    var assets = best.assets || [];
    for (var a = 0; a < assets.length; a++) {
      var asset = assets[a];
      if (asset && asset.name === "Grok-Voice-Reader-Extension.zip" && asset.browser_download_url) {
        url = asset.browser_download_url;
      }
    }
    return { tag: best.tag_name, version: bestParts.join("."), url: url };
  };

  GV.updateCheckDue = function updateCheckDue(lastMs, nowMs) {
    var last = Number(lastMs) || 0;
    var now = Number(nowMs) || 0;
    if (!last) return true;
    var gap = GV.UPDATE_INTERVAL_MS || (24 * 60 * 60 * 1000);
    return now - last >= gap;
  };
})(globalThis);

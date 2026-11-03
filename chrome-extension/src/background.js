/* global GrokVoice */
importScripts("config.js", "text.js", "updates.js");

var GV = globalThis.GrokVoice;
var framesByTab = {};
globalThis.frameReportsFor = function (tabId) {
  var bucket = framesByTab[tabId] || {};
  var reports = [];
  for (var key in bucket) {
    if (Object.prototype.hasOwnProperty.call(bucket, key)) reports.push(bucket[key]);
  }
  reports.sort(function (a, b) { return a.frameId - b.frameId; });
  return reports;
};

function rememberFrame(tabId, frameId, report) {
  if (!framesByTab[tabId]) framesByTab[tabId] = {};
  framesByTab[tabId][frameId] = report;
}

function showOn(tabId) {
  chrome.action.setBadgeText({ tabId: tabId, text: "ON" });
  chrome.action.setBadgeBackgroundColor({ tabId: tabId, color: "#146c43" });
  if (!chrome.action.setBadgeTextColor) return;
  var colored = chrome.action.setBadgeTextColor({ tabId: tabId, color: "#ffffff" });
  if (colored && colored.catch) colored.catch(function () {});
}

function refreshBadge(tabId) {
  if (tabId == null) return;
  chrome.tabs.get(tabId).then(function (tab) {
    return chrome.storage.local.get(GV.DEFAULTS).then(function (stored) {
      var enabled = stored.enabled !== false;
      var matches = Boolean(tab.url && GV.urlMatches(tab.url));
      if (enabled && matches) showOn(tabId);
      else chrome.action.setBadgeText({ tabId: tabId, text: "" });
    });
  }).catch(function () {
    // The tab closed before the badge could update.
  });
}

function refreshAll() {
  chrome.tabs.query({}).then(function (tabs) {
    tabs.forEach(function (tab) { refreshBadge(tab.id); });
  }).catch(function () {});
}

chrome.runtime.onInstalled.addListener(function () {
  chrome.storage.local.get(GV.DEFAULTS).then(function (stored) {
    return chrome.storage.local.set({
      enabled: stored.enabled !== false,
      voiceURI: stored.voiceURI || "",
      rate: GV.clampRate(stored.rate)
    });
  }).then(refreshAll).catch(function () {});
});

chrome.runtime.onStartup.addListener(refreshAll);
chrome.tabs.onActivated.addListener(function (info) { refreshBadge(info.tabId); });
chrome.tabs.onUpdated.addListener(function (tabId, changeInfo) {
  if (changeInfo.status === "complete" || changeInfo.url) refreshBadge(tabId);
});
chrome.storage.onChanged.addListener(function (changes, area) {
  if (area === "local" && changes.enabled) refreshAll();
});

chrome.tabs.onRemoved.addListener(function (tabId) {
  delete framesByTab[tabId];
});

chrome.runtime.onMessage.addListener(function (message, sender, sendResponse) {
  if (!message) return;
  if (message.type === "frame-report" && sender.tab) {
    rememberFrame(sender.tab.id, sender.frameId, {
      frameId: sender.frameId,
      url: message.href || sender.url || "",
      blocks: message.blocks || 0,
      groups: message.groups || 0,
      snippet: message.snippet || "",
      reason: message.reason || "",
      mode: message.mode || "",
      botId: message.botId || "",
      botName: message.botName || "",
      playback: message.playback || ""
    });
    try { sendResponse({ ok: true }); } catch (err) { /* port closed */ }
    return;
  }
  if (message.type === "popup-status") {
    chrome.tabs.query({ active: true, currentWindow: true }).then(function (tabs) {
      var tab = tabs[0];
      return chrome.storage.local.get(GV.DEFAULTS).then(function (stored) {
        sendResponse({
          ok: true,
          enabled: stored.enabled !== false,
          frames: tab ? globalThis.frameReportsFor(tab.id) : []
        });
      });
    }).catch(function () {
      try { sendResponse({ ok: false, frames: [] }); } catch (err) { /* port closed */ }
    });
    return true;
  }
  if (message.type === "broadcast" && sender.tab == null) {
    broadcastCommand(message.command, sendResponse);
    return true;
  }
  if (message.type === "check-update") {
    checkUpdates(Boolean(message.force)).then(function (notice) {
      try { sendResponse({ ok: true, notice: notice || null }); } catch (err) { /* port closed */ }
    }).catch(function () {
      try { sendResponse({ ok: false, notice: null }); } catch (err) { /* port closed */ }
    });
    return true;
  }
  if (message.type !== "watch-state" || !sender.tab) return;
  try {
    if (message.enabled) showOn(sender.tab.id);
    else chrome.action.setBadgeText({ tabId: sender.tab.id, text: "" });
    sendResponse({ ok: true });
  } catch (err) {
    try { sendResponse({ ok: false }); } catch (inner) { /* port already closed */ }
  }
});

function broadcastCommand(command, sendResponse) {
  chrome.tabs.query({ active: true, currentWindow: true }).then(function (tabs) {
    var tab = tabs[0];
    if (!tab) {
      if (sendResponse) sendResponse({ ok: false });
      return;
    }
    var reports = globalThis.frameReportsFor(tab.id);
    var ids = reports.map(function (report) { return report.frameId; });
    if (!ids.length) ids = [0];
    var pending = ids.length;
    var text = "";
    var mode = "";
    ids.forEach(function (frameId) {
      chrome.tabs.sendMessage(tab.id, { type: command }, { frameId: frameId }, function (response) {
        void chrome.runtime.lastError;
        if (response && response.text) text = response.text;
        if (response && response.mode) mode = response.mode;
        pending -= 1;
        if (!pending && sendResponse) {
          try {
            sendResponse({ ok: Boolean(text) || command === "stop", text: text, mode: mode });
          } catch (err) { /* port closed */ }
        }
      });
    });
  }).catch(function () {
    if (sendResponse) {
      try { sendResponse({ ok: false }); } catch (err) { /* port closed */ }
    }
  });
}

function checkUpdates(force) {
  return chrome.storage.local.get(GV.DEFAULTS).then(function (stored) {
    var now = Date.now();
    if (!force && !GV.updateCheckDue(stored.updateCheckedAt, now)) {
      return stored.updateNotice || null;
    }
    return fetch("https://api.github.com/repos/" + GV.REPO + "/releases?per_page=30", {
      headers: {
        Accept: "application/vnd.github+json",
        "User-Agent": "grok-voice-reader"
      }
    }).then(function (response) {
      if (!response.ok) throw new Error("status " + response.status);
      return response.json();
    }).then(function (list) {
      var notice = GV.pickExtensionUpdate(list, chrome.runtime.getManifest().version, {
        beta: stored.betaUpdates === true
      });
      return chrome.storage.local.set({
        updateCheckedAt: now,
        updateNotice: notice
      }).then(function () { return notice; });
    }).catch(function () {
      return chrome.storage.local.set({ updateCheckedAt: now }).then(function () {
        return stored.updateNotice || null;
      });
    });
  });
}

if (chrome.commands && chrome.commands.onCommand) {
  chrome.commands.onCommand.addListener(function (command) {
    broadcastCommand(command);
  });
}

checkUpdates(false);
refreshAll();

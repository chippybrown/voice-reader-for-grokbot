/* global GrokVoice */
importScripts("config.js", "text.js");

var GV = globalThis.GrokVoice;

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

chrome.runtime.onMessage.addListener(function (message, sender) {
  if (!message || message.type !== "watch-state" || !sender.tab) return;
  if (message.enabled) showOn(sender.tab.id);
  else chrome.action.setBadgeText({ tabId: sender.tab.id, text: "" });
});

refreshAll();

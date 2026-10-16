/* pwa.js — Service Worker 注册 + 离线徽标 + 队列回放 */
(function () {
  'use strict';

  var SW_URL = '/sw.js';
  var SW_SCOPE = '/';
  var UPDATE_TOAST_ID = 'pwa-update-toast';

  function byId(id) {
    if (typeof window.$ === 'function') {
      try { return window.$(id); } catch (e) { /* ignore */ }
    }
    return document.getElementById(id);
  }

  function setBadge(count) {
    var n = Number(count) || 0;
    var badge = byId('offline-badge');
    if (!badge) return;
    if (n > 0) {
      badge.textContent = String(n);
      badge.hidden = false;
      badge.setAttribute('aria-hidden', 'false');
    } else {
      badge.textContent = '';
      badge.hidden = true;
      badge.setAttribute('aria-hidden', 'true');
    }
  }

  function refreshBadgeFromNavigator() {
    var n = 0;
    try {
      var q = window.__sbOfflineQueue;
      if (q && typeof q.size === 'function') n = q.size();
      else if (q && typeof q.count === 'function') n = q.count();
      else if (q && typeof q.length === 'number') n = q.length;
      else if (Array.isArray(q)) n = q.length;
    } catch (e) { /* ignore */ }
    setBadge(n);
  }

  function tryReplayQueue() {
    var q = window.__sbOfflineQueue;
    if (!q || typeof q.replay !== 'function') return;
    q.replay().then(function (res) {
      var ok = (res && typeof res.ok === 'number') ? res.ok : 0;
      if (ok > 0 && typeof window.__sbOnQueueSynced === 'function') {
        try { window.__sbOnQueueSynced(ok); } catch (e) { console.warn('[pwa] __sbOnQueueSynced 抛错', e); }
      }
    }).catch(function (e) { console.warn('[pwa] 离线队列回放失败', e); });
  }

  function showUpdateToast(reg) {
    if (byId(UPDATE_TOAST_ID)) return;
    var toast = document.createElement('div');
    toast.id = UPDATE_TOAST_ID;
    toast.setAttribute('role', 'status');
    toast.style.cssText = [
      'position:fixed',
      'left:50%',
      'bottom:16px',
      'transform:translateX(-50%)',
      'z-index:9999',
      'background:#111',
      'color:#fff',
      'padding:10px 14px',
      'border-radius:8px',
      'font-size:14px',
      'box-shadow:0 4px 16px rgba(0,0,0,.3)',
      'display:flex',
      'gap:10px',
      'align-items:center'
    ].join(';');

    var text = document.createElement('span');
    text.textContent = '发现新版本';

    var btn = document.createElement('button');
    btn.type = 'button';
    btn.textContent = '刷新';
    btn.style.cssText = [
      'background:#fff',
      'color:#111',
      'border:0',
      'border-radius:6px',
      'padding:4px 10px',
      'font-size:13px',
      'cursor:pointer'
    ].join(';');
    btn.addEventListener('click', function () {
      try {
        if (reg && reg.waiting) reg.waiting.postMessage({ type: 'SKIP_WAITING' });
      } catch (e) { /* ignore */ }
      window.location.reload();
    });

    toast.appendChild(text);
    toast.appendChild(btn);
    document.body.appendChild(toast);
  }

  function registerServiceWorker() {
    if (!('serviceWorker' in navigator)) return;
    window.addEventListener('load', function () {
      navigator.serviceWorker.register(SW_URL, { scope: SW_SCOPE }).then(function (reg) {
        if (reg.waiting && navigator.serviceWorker.controller) {
          showUpdateToast(reg);
        }
        reg.addEventListener('updatefound', function () {
          var nw = reg.installing;
          if (!nw) return;
          nw.addEventListener('statechange', function () {
            if (nw.state === 'installed' && navigator.serviceWorker.controller) {
              showUpdateToast(reg);
            }
          });
        });
      }).catch(function (e) {
        console.warn('[pwa] SW 注册失败', e);
      });

      navigator.serviceWorker.addEventListener('controllerchange', function () {
        // 新 SW 接管后，无需强制刷新，交由用户点击 toast 处理
      });
    });
  }

  function init() {
    registerServiceWorker();
    refreshBadgeFromNavigator();
    if (navigator.onLine) { tryReplayQueue(); }

    window.addEventListener('online', function () {
      refreshBadgeFromNavigator();
      tryReplayQueue();
    });

    window.addEventListener('offline', function () {
      refreshBadgeFromNavigator();
    });

    window.addEventListener('sb:queue-changed', function () {
      refreshBadgeFromNavigator();
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();

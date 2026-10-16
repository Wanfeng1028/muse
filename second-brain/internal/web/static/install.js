// install.js — PWA 安装入口
// 约定：#install-banner / #install-banner-install / #install-banner-later
//       #install-ios-sheet / #install-ios-sheet-close
//       #btn-install-app
// 显隐一律走 hidden 属性，不碰 style.display。

(function () {
  'use strict';

  var DISMISS_KEY = 'sb-install-dismissed-at';
  var DISMISS_TTL = 7 * 24 * 60 * 60 * 1000; // 7 天

  function $(id) {
    return document.getElementById(id);
  }

  function isStandalone() {
    try {
      if (window.matchMedia && window.matchMedia('(display-mode: standalone)').matches) {
        return true;
      }
    } catch (e) {}
    if (window.navigator && window.navigator.standalone === true) {
      return true;
    }
    return false;
  }

  function isIOS() {
    var ua = window.navigator.userAgent || '';
    var platform = window.navigator.platform || '';
    var iOSDevice = /iPad|iPhone|iPod/.test(ua) ||
      (platform === 'MacIntel' && window.navigator.maxTouchPoints > 1);
    if (!iOSDevice) {
      return false;
    }
    // iOS 上的 Chrome / Firefox 仍是 WebKit，但不支持 beforeinstallprompt，也不支持"添加到主屏幕"的标准流程
    if (/CriOS|FxiOS/.test(ua)) {
      return false;
    }
    return true;
  }

  function readDismissedAt() {
    try {
      var raw = window.localStorage.getItem(DISMISS_KEY);
      if (!raw) {
        return 0;
      }
      var n = parseInt(raw, 10);
      return isNaN(n) ? 0 : n;
    } catch (e) {
      return 0;
    }
  }

  function markDismissed() {
    try {
      window.localStorage.setItem(DISMISS_KEY, String(Date.now()));
    } catch (e) {}
  }

  function clearDismissed() {
    try {
      window.localStorage.removeItem(DISMISS_KEY);
    } catch (e) {}
  }

  function isDismissedRecently() {
    var at = readDismissedAt();
    if (!at) {
      return false;
    }
    return Date.now() - at < DISMISS_TTL;
  }

  function hideAll() {
    var banner = $('install-banner');
    if (banner) {
      banner.hidden = true;
    }
    var sheet = $('install-ios-sheet');
    if (sheet) {
      sheet.hidden = true;
    }
  }

  function showBanner() {
    var banner = $('install-banner');
    if (banner) {
      banner.hidden = false;
    }
  }

  function hideBanner() {
    var banner = $('install-banner');
    if (banner) {
      banner.hidden = true;
    }
  }

  function showIOSSheet() {
    var sheet = $('install-ios-sheet');
    if (sheet) {
      sheet.hidden = false;
    }
  }

  function hideIOSSheet() {
    var sheet = $('install-ios-sheet');
    if (sheet) {
      sheet.hidden = true;
    }
  }

  function init() {
    hideAll();

    if (isStandalone()) {
      // 已安装，不再打扰
      return;
    }

    var btnInstallApp = $('btn-install-app');
    var banner = $('install-banner');
    var bannerInstall = $('install-banner-install');
    var bannerLater = $('install-banner-later');
    var iosSheet = $('install-ios-sheet');
    var iosSheetClose = $('install-ios-sheet-close');

    // 所有攒下的 deferredPrompt 只在这里
    var deferredPrompt = null;

    // ---------- iOS 分支 ----------
    if (isIOS()) {
      if (btnInstallApp) {
        btnInstallApp.addEventListener('click', function () {
          showIOSSheet();
        });
      }
      if (iosSheetClose) {
        iosSheetClose.addEventListener('click', function () {
          hideIOSSheet();
        });
      }
      if (iosSheet) {
        iosSheet.addEventListener('click', function (ev) {
          if (ev.target === iosSheet) {
            hideIOSSheet();
          }
        });
      }
      return;
    }

    // ---------- 桌面 / Android Chromium 分支 ----------

    window.addEventListener('beforeinstallprompt', function (ev) {
      ev.preventDefault();
      deferredPrompt = ev;

      // 7 天内用户手动关过 banner 就不打扰
      if (!isDismissedRecently()) {
        showBanner();
      }
    });

    window.addEventListener('appinstalled', function () {
      deferredPrompt = null;
      clearDismissed();
      hideBanner();
      hideIOSSheet();
    });

    if (bannerInstall) {
      bannerInstall.addEventListener('click', function () {
        if (!deferredPrompt) {
          hideBanner();
          return;
        }
        var promptEvent = deferredPrompt;
        deferredPrompt = null;
        promptEvent.prompt();
        var choice = promptEvent.userChoice;
        if (choice && typeof choice.then === 'function') {
          choice.then(function (result) {
            if (result && result.outcome === 'accepted') {
              hideBanner();
              clearDismissed();
            } else {
              hideBanner();
              markDismissed();
            }
          }).catch(function () {
            hideBanner();
          });
        } else {
          hideBanner();
        }
      });
    }

    if (bannerLater) {
      bannerLater.addEventListener('click', function () {
        hideBanner();
        markDismissed();
      });
    }

    if (btnInstallApp) {
      btnInstallApp.addEventListener('click', function () {
        if (deferredPrompt) {
          var promptEvent = deferredPrompt;
          deferredPrompt = null;
          promptEvent.prompt();
          var choice = promptEvent.userChoice;
          if (choice && typeof choice.then === 'function') {
            choice.then(function (result) {
              if (result && result.outcome === 'accepted') {
                hideBanner();
                clearDismissed();
              } else {
                hideBanner();
                markDismissed();
              }
            }).catch(function () {
              hideBanner();
            });
          } else {
            hideBanner();
          }
          return;
        }

        // 事件还没来：显示 banner，文案已说明按钮等事件到了就能用
        showBanner();
        if (window.console && typeof window.console.info === 'function') {
          window.console.info('[PWA] 浏览器安装事件尚未就绪，也可点击地址栏右侧的安装图标完成安装。');
        }
      });
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();

(function () {
  'use strict';

  if (!window.DFI18N) throw new Error('i18n.js 未加载');

  var user = null;

  // bindLanguage 内赋值，供 reloadMe 同步语言单选按钮
  var syncLangRadios = null;

  var I18N = {
    'doc.title': { 'zh-CN': '账号 · AI 短剧工坊', 'en': 'Account · AI Drama Factory' },
    'page.title': { 'zh-CN': '账号', 'en': 'Account' },
    'profile.title': { 'zh-CN': '个人资料', 'en': 'Profile' },
    'profile.nickname': { 'zh-CN': '昵称', 'en': 'Nickname' },
    'profile.edit': { 'zh-CN': '编辑', 'en': 'Edit' },
    'profile.email': { 'zh-CN': '邮箱', 'en': 'Email' },
    'profile.role': { 'zh-CN': '角色', 'en': 'Role' },
    'profile.save': { 'zh-CN': '保存', 'en': 'Save' },
    'profile.cancel': { 'zh-CN': '取消', 'en': 'Cancel' },
    'sec.title': { 'zh-CN': '账号与安全', 'en': 'Account & Security' },
    'sec.email': { 'zh-CN': '邮箱', 'en': 'Email' },
    'sec.change': { 'zh-CN': '修改', 'en': 'Change' },
    'sec.newEmail': { 'zh-CN': '新邮箱', 'en': 'New email' },
    'sec.currentPassword': { 'zh-CN': '当前密码', 'en': 'Current password' },
    'sec.password': { 'zh-CN': '密码', 'en': 'Password' },
    'sec.oldPassword': { 'zh-CN': '旧密码', 'en': 'Old password' },
    'sec.newPassword': { 'zh-CN': '新密码', 'en': 'New password' },
    'sec.pwHint': { 'zh-CN': '至少 8 位，且包含字母和数字', 'en': 'At least 8 characters, with letters and numbers' },
    'sec.pwHintOk': { 'zh-CN': '密码符合要求', 'en': 'Password meets requirements' },
    'sec.sessions': { 'zh-CN': '登录会话', 'en': 'Sessions' },
    'sec.refresh': { 'zh-CN': '刷新', 'en': 'Refresh' },
    'sec.revoke': { 'zh-CN': '撤销', 'en': 'Revoke' },
    'sec.currentDevice': { 'zh-CN': '本机', 'en': 'This device' },
    'pref.title': { 'zh-CN': '个性化', 'en': 'Preferences' },
    'pref.themeSystem': { 'zh-CN': '跟随系统', 'en': 'System' },
    'pref.themeLight': { 'zh-CN': '浅色', 'en': 'Light' },
    'pref.themeDark': { 'zh-CN': '深色', 'en': 'Dark' },
    'pref.language': { 'zh-CN': '语言', 'en': 'Language' },
    'logout.title': { 'zh-CN': '退出', 'en': 'Sign out' },
    'logout.desc': { 'zh-CN': '退出后需要重新登录才能访问。', 'en': "You'll need to sign in again after signing out." },
    'logout.btn': { 'zh-CN': '退出登录', 'en': 'Sign out' },
    'err.generic': { 'zh-CN': '操作失败', 'en': 'Operation failed' },
    'err.nicknameEmpty': { 'zh-CN': '昵称不能为空', 'en': 'Nickname cannot be empty' },
    'err.saveFail': { 'zh-CN': '保存失败', 'en': 'Save failed' },
    'err.fillEmailPassword': { 'zh-CN': '请填写新邮箱和当前密码', 'en': 'Please enter the new email and current password' },
    'err.changeFail': { 'zh-CN': '修改失败', 'en': 'Update failed' },
    'err.fillOldNew': { 'zh-CN': '请填写旧密码和新密码', 'en': 'Please enter the old and new passwords' },
    'err.weakPassword': { 'zh-CN': '密码至少 8 位，且包含字母和数字', 'en': 'At least 8 characters, with letters and numbers' },
    'err.loadFail': { 'zh-CN': '加载失败', 'en': 'Load failed' },
    'err.revokeFail': { 'zh-CN': '撤销失败', 'en': 'Revoke failed' },
    'session.empty': { 'zh-CN': '暂无其他会话', 'en': 'No other sessions' }
  };

  DFI18N.register(I18N);

  function tr(key) {
    return DFI18N.tr(key);
  }

  function $(id) { return document.getElementById(id); }

  function showErr(el, msg) {
    el.textContent = msg || tr('err.generic');
    el.hidden = false;
  }
  function clearErr(el) {
    el.hidden = true;
    el.textContent = '';
  }

  function validPassword(pw) {
    return typeof pw === 'string' && pw.length >= 8 && /[A-Za-z]/.test(pw) && /[0-9]/.test(pw);
  }

  function renderAvatar(u) {
    var wrap = $('avatar-wrap');
    wrap.innerHTML = Auth.geometricAvatar(u.id != null ? u.id : (u.email || ''), 64);
  }

  function renderProfile(u) {
    $('nickname-view').textContent = u.nickname || '—';
    $('email-view').textContent = u.email || '—';
    $('role-view').textContent = u.role || '—';
    renderAvatar(u);
  }

  function reloadMe() {
    return Auth.me().then(function (u) {
      user = u;
      renderProfile(u);
      var lang = u && u.language === 'en' ? 'en' : 'zh-CN';
      try {
        localStorage.setItem('df-lang', lang);
      } catch (e) {
        // 存储不可用时忽略
      }
      DFI18N.applyI18n();
      // 服务端语言可能与本地初始值不一致，同步语言单选按钮
      if (typeof syncLangRadios === 'function') syncLangRadios(lang);
      return u;
    });
  }

  function bindNickname() {
    var view = $('nickname-view');
    var editor = $('nickname-editor');
    var input = $('nickname-input');
    var err = $('profile-error');

    $('nickname-edit').addEventListener('click', function () {
      clearErr(err);
      input.value = user && user.nickname ? user.nickname : '';
      view.hidden = true;
      $('nickname-edit').hidden = true;
      editor.hidden = false;
      input.focus();
    });

    $('nickname-cancel').addEventListener('click', function () {
      clearErr(err);
      editor.hidden = true;
      view.hidden = false;
      $('nickname-edit').hidden = false;
    });

    $('nickname-save').addEventListener('click', function () {
      clearErr(err);
      var nickname = input.value.trim();
      if (!nickname) { showErr(err, tr('err.nicknameEmpty')); return; }
      $('nickname-save').disabled = true;
      Auth.updateProfile(nickname, user ? user.avatarUrl : null).then(function (u) {
        user = u;
        renderProfile(u);
        editor.hidden = true;
        view.hidden = false;
        $('nickname-edit').hidden = false;
      }).catch(function (e) {
        showErr(err, e && e.message ? e.message : tr('err.saveFail'));
      }).then(function () {
        $('nickname-save').disabled = false;
      });
    });
  }

  function bindEmail() {
    var form = $('email-form');
    var err = $('email-error');
    $('email-change-toggle').addEventListener('click', function () {
      clearErr(err);
      form.hidden = !form.hidden;
    });
    form.querySelector('[data-cancel]').addEventListener('click', function () {
      clearErr(err);
      form.reset();
      form.hidden = true;
    });
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      clearErr(err);
      var newEmail = form.newEmail.value.trim();
      var password = form.password.value;
      if (!newEmail || !password) { showErr(err, tr('err.fillEmailPassword')); return; }
      form.querySelector('button[type=submit]').disabled = true;
      Auth.changeEmail(newEmail, password).then(function (u) {
        user = u;
        renderProfile(u);
        form.reset();
        form.hidden = true;
      }).catch(function (e2) {
        showErr(err, e2 && e2.message ? e2.message : tr('err.changeFail'));
      }).then(function () {
        form.querySelector('button[type=submit]').disabled = false;
      });
    });
  }

  function bindPassword() {
    var form = $('password-form');
    var err = $('password-error');
    var hint = $('pw-hint');

    function syncHint() {
      var pw = form.newPassword.value;
      var ok = validPassword(pw) && pw.length > 0;
      hint.classList.toggle('is-ok', ok);
      hint.textContent = ok ? tr('sec.pwHintOk') : tr('sec.pwHint');
    }
    form.newPassword.addEventListener('input', syncHint);
    syncHint();

    $('password-change-toggle').addEventListener('click', function () {
      clearErr(err);
      form.hidden = !form.hidden;
    });
    form.querySelector('[data-cancel]').addEventListener('click', function () {
      clearErr(err);
      form.reset();
      syncHint();
      form.hidden = true;
    });
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      clearErr(err);
      var oldPassword = form.oldPassword.value;
      var newPassword = form.newPassword.value;
      if (!oldPassword || !newPassword) { showErr(err, tr('err.fillOldNew')); return; }
      if (!validPassword(newPassword)) { showErr(err, tr('err.weakPassword')); return; }
      form.querySelector('button[type=submit]').disabled = true;
      Auth.changePassword(oldPassword, newPassword).then(function () {
        form.reset();
        syncHint();
        form.hidden = true;
      }).catch(function (e2) {
        showErr(err, e2 && e2.message ? e2.message : tr('err.changeFail'));
      }).then(function () {
        form.querySelector('button[type=submit]').disabled = false;
      });
    });
  }

  function fmtTime(s) {
    if (!s) return '—';
    var d = new Date(s);
    if (isNaN(d.getTime())) return '—';
    var p = function (n) { return n < 10 ? '0' + n : '' + n; };
    return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate()) + ' ' + p(d.getHours()) + ':' + p(d.getMinutes());
  }

  function renderSessions(list) {
    var ul = $('session-list');
    ul.innerHTML = '';
    if (!list || !list.length) {
      var empty = document.createElement('li');
      empty.className = 'session-empty';
      empty.textContent = tr('session.empty');
      ul.appendChild(empty);
      return;
    }
    list.forEach(function (s) {
      var li = document.createElement('li');
      li.className = 'session-item';

      var main = document.createElement('div');
      main.className = 'session-main';

      var dev = document.createElement('div');
      dev.className = 'session-device';
      dev.textContent = s.deviceInfo || '—';
      if (s.current) {
        var tag = document.createElement('span');
        tag.className = 'tag';
        tag.textContent = tr('sec.currentDevice');
        dev.appendChild(tag);
      }
      main.appendChild(dev);

      var meta = document.createElement('div');
      meta.className = 'session-meta';
      meta.textContent = (s.ip || '—') + ' · ' + fmtTime(s.createdAt);
      main.appendChild(meta);

      li.appendChild(main);

      if (!s.current) {
        var btn = document.createElement('button');
        btn.className = 'btn btn-quiet btn-sm';
        btn.type = 'button';
        btn.textContent = tr('sec.revoke');
        btn.addEventListener('click', function () {
          btn.disabled = true;
          Auth.revokeSession(s.id).then(function () {
            return loadSessions();
          }).catch(function (e) {
            showErr($('sessions-error'), e && e.message ? e.message : tr('err.revokeFail'));
          }).then(function () {
            btn.disabled = false;
          });
        });
        li.appendChild(btn);
      }

      ul.appendChild(li);
    });
  }

  function loadSessions() {
    clearErr($('sessions-error'));
    return Auth.sessions().then(function (list) {
      renderSessions(list);
    }).catch(function (e) {
      showErr($('sessions-error'), e && e.message ? e.message : tr('err.loadFail'));
    });
  }

  function bindSessions() {
    $('sessions-refresh').addEventListener('click', function () {
      loadSessions();
    });
  }

  var mql = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;

  function applyTheme(mode) {
    var effective = mode;
    if (mode === 'system') {
      effective = mql && mql.matches ? 'dark' : 'light';
    }
    document.documentElement.setAttribute('data-bs-theme', effective === 'dark' ? 'dark' : 'light');
  }

  function readTheme() {
    try {
      var t = localStorage.getItem('df-theme');
      if (t === 'dark' || t === 'light' || t === 'system') return t;
    } catch (e) {}
    return 'system';
  }

  function bindTheme() {
    var current = readTheme();
    var radios = document.querySelectorAll('input[name="theme"]');
    radios.forEach(function (r) {
      if (r.value === current) r.checked = true;
      r.addEventListener('change', function () {
        if (!r.checked) return;
        try { localStorage.setItem('df-theme', r.value); } catch (e) {}
        applyTheme(r.value);
      });
    });

    if (mql) {
      var onSys = function () {
        if (readTheme() === 'system') applyTheme('system');
      };
      if (mql.addEventListener) mql.addEventListener('change', onSys);
      else if (mql.addListener) mql.addListener(onSys);
    }
  }

  function bindLogout() {
    var btn = $('logout-btn');
    if (!btn) return;
    btn.addEventListener('click', function () {
      btn.disabled = true;
      Auth.logout().catch(function () {
        window.location.href = '/login.html';
      });
    });
  }

  function bindLanguage() {
    var radios = document.querySelectorAll('input[name="lang"]');
    if (!radios || !radios.length) { return; }
    var err = $('lang-error');

    function syncChecked(lang) {
      for (var i = 0; i < radios.length; i++) {
        radios[i].checked = radios[i].value === lang;
      }
    }
    // 供 reloadMe 在服务端语言与本地不一致时同步单选按钮
    syncLangRadios = syncChecked;

    function currentChecked() {
      for (var i = 0; i < radios.length; i++) {
        if (radios[i].checked) { return radios[i].value === 'en' ? 'en' : 'zh-CN'; }
      }
      return DFI18N.readLang();
    }

    syncChecked(DFI18N.getLang());

    for (var i = 0; i < radios.length; i++) {
      radios[i].addEventListener('change', function () {
        var next = this.value === 'en' ? 'en' : 'zh-CN';
        var prev = DFI18N.getLang();
        if (next === prev) { syncChecked(next); return; }
        if (err) { clearErr(err); }
        this.disabled = true;
        var self = this;
        DFI18N.setLang(next).then(function () {
          syncChecked(next);
        }).catch(function (e2) {
          if (err) {
            showErr(err, e2 && e2.message ? e2.message : tr('err.generic'));
          }
          syncChecked(prev);
        }).then(function () {
          self.disabled = false;
        });
      });
    }
  }

  function boot() {
    DFI18N.applyI18n();

    bindNickname();
    bindEmail();
    bindPassword();
    bindSessions();
    bindTheme();
    bindLogout();
    bindLanguage();

    reloadMe().catch(function () {
      // Auth.requireAuth 已处理跳转；这里静默
    });
    loadSessions();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();

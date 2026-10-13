(function () {
  'use strict';

  var user = null;

  function $(id) { return document.getElementById(id); }

  function showErr(el, msg) {
    el.textContent = msg || '操作失败';
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
      if (!nickname) { showErr(err, '昵称不能为空'); return; }
      $('nickname-save').disabled = true;
      Auth.updateProfile(nickname, user ? user.avatarUrl : null).then(function (u) {
        user = u;
        renderProfile(u);
        editor.hidden = true;
        view.hidden = false;
        $('nickname-edit').hidden = false;
      }).catch(function (e) {
        showErr(err, e && e.message ? e.message : '保存失败');
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
      if (!newEmail || !password) { showErr(err, '请填写新邮箱和当前密码'); return; }
      form.querySelector('button[type=submit]').disabled = true;
      Auth.changeEmail(newEmail, password).then(function (u) {
        user = u;
        renderProfile(u);
        form.reset();
        form.hidden = true;
      }).catch(function (e2) {
        showErr(err, e2 && e2.message ? e2.message : '修改失败');
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
      hint.textContent = ok ? '密码符合要求' : '至少 8 位，且包含字母和数字';
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
      if (!oldPassword || !newPassword) { showErr(err, '请填写旧密码和新密码'); return; }
      if (!validPassword(newPassword)) { showErr(err, '密码至少 8 位，且包含字母和数字'); return; }
      form.querySelector('button[type=submit]').disabled = true;
      Auth.changePassword(oldPassword, newPassword).then(function () {
        form.reset();
        syncHint();
        form.hidden = true;
      }).catch(function (e2) {
        showErr(err, e2 && e2.message ? e2.message : '修改失败');
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
      empty.textContent = '—';
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
        tag.textContent = '本机';
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
        btn.textContent = '撤销';
        btn.addEventListener('click', function () {
          btn.disabled = true;
          Auth.revokeSession(s.id).then(function () {
            return loadSessions();
          }).catch(function (e) {
            showErr($('sessions-error'), e && e.message ? e.message : '撤销失败');
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
      showErr($('sessions-error'), e && e.message ? e.message : '加载失败');
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

  function boot() {
    bindNickname();
    bindEmail();
    bindPassword();
    bindSessions();
    bindTheme();
    bindLogout();

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

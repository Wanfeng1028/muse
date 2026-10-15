(function (global) {
  'use strict';

  var AUTH_BASE = '/api/auth';
  var LOGIN_PATH = '/login.html';
  var HOME_PATH = '/index.html';
  var GUEST_PAGES = ['/login.html', '/register.html', '/oauth-callback.html'];

  function isGuestPage() {
    var p = global.location.pathname;
    for (var i = 0; i < GUEST_PAGES.length; i++) {
      if (p === GUEST_PAGES[i] || p.indexOf(GUEST_PAGES[i]) === 0) return true;
    }
    return false;
  }

  function currentPathWithQuery() {
    return global.location.pathname + global.location.search;
  }

  function redirectToLogin() {
    if (isGuestPage()) return;
    var next = encodeURIComponent(currentPathWithQuery());
    global.location.href = LOGIN_PATH + '?next=' + next;
  }

  function makeError(status, body) {
    var err = new Error((body && body.message) || '请求失败');
    err.status = status;
    err.code = body && body.code;
    err.body = body;
    return err;
  }

  function rawFetch(path, options) {
    var opts = options || {};
    var headers = opts.headers || {};
    if (opts.body !== undefined && !(opts.body instanceof FormData)) {
      headers['Content-Type'] = 'application/json';
    }
    // noAuth 参数保留以兼容既有调用；认证态由 httpOnly Cookie（df_at/df_rt）承载，前端不再注入 Authorization 头
    return fetch(path, {
      method: opts.method || 'GET',
      headers: headers,
      body: opts.body !== undefined
        ? (opts.body instanceof FormData ? opts.body : JSON.stringify(opts.body))
        : undefined,
      credentials: 'same-origin'
    }).then(function (res) {
      var ct = res.headers.get('content-type') || '';
      var parse = ct.indexOf('application/json') >= 0
        ? res.json().catch(function () { return null; })
        : res.text().then(function (t) { return t ? { message: t } : null; });
      return parse.then(function (body) {
        if (!res.ok) throw makeError(res.status, body);
        return body;
      });
    });
  }

  var refreshing = null;

  // 认证态由 httpOnly Cookie（df_at/df_rt）承载，浏览器自动携带；前端不触碰 token。
  function tryRefresh() {
    if (refreshing) return refreshing;
    refreshing = rawFetch(AUTH_BASE + '/refresh', { method: 'POST', body: {}, noAuth: true })
      .then(function () {
        return true;
      })
      .catch(function () {
        redirectToLogin();
        return false;
      })
      .then(function (v) { refreshing = null; return v; });
    return refreshing;
  }

  function request(path, options, retried) {
    return rawFetch(AUTH_BASE + path, options).catch(function (err) {
      if (err && err.status === 401 && !retried) {
        return tryRefresh().then(function (ok) {
          if (!ok) { redirectToLogin(); throw err; }
          return request(path, options, true);
        });
      }
      if (err && err.status === 401) {
        redirectToLogin();
      }
      throw err;
    });
  }

  var Auth = {
    isGuestPage: isGuestPage,

    me: function () {
      return request('/me', { method: 'GET' });
    },

    login: function (email, password) {
      return rawFetch(AUTH_BASE + '/login', { method: 'POST', body: { email: email, password: password }, noAuth: true });
    },

    register: function (email, password, nickname) {
      return rawFetch(AUTH_BASE + '/register', { method: 'POST', body: { email: email, password: password, nickname: nickname }, noAuth: true });
    },

    logout: function () {
      return rawFetch(AUTH_BASE + '/logout', { method: 'POST' }).then(function (r) {
        global.location.href = LOGIN_PATH;
        return r;
      }).catch(function (err) {
        global.location.href = LOGIN_PATH;
        throw err;
      });
    },

    updateProfile: function (nickname, avatarUrl, language) {
      var body = { nickname: nickname, avatarUrl: avatarUrl };
      if (language !== undefined) body.language = language;
      return request('/profile', { method: 'PUT', body: body });
    },

    changePassword: function (oldPassword, newPassword) {
      return request('/password', { method: 'PUT', body: { oldPassword: oldPassword, newPassword: newPassword } });
    },

    changeEmail: function (newEmail, password) {
      return request('/email', { method: 'PUT', body: { newEmail: newEmail, password: password } });
    },

    sessions: function () {
      return request('/sessions', { method: 'GET' });
    },

    revokeSession: function (id) {
      return request('/sessions/' + encodeURIComponent(id), { method: 'DELETE' });
    },

    oauthUrl: function (provider) {
      return request('/oauth/' + encodeURIComponent(provider) + '/url', { method: 'GET' });
    },

    oauthCallback: function (provider, code, state) {
      return request('/oauth/' + encodeURIComponent(provider) + '/callback?code=' + encodeURIComponent(code) + '&state=' + encodeURIComponent(state), { method: 'GET' });
    },

    requireAuth: function () {
      if (isGuestPage()) return Promise.resolve(null);
      return Auth.me().catch(function () {
        return null;
      });
    },

    guardGuest: function () {
      return Auth.me().then(function (user) {
        global.location.href = HOME_PATH;
        return user;
      }).catch(function () {
        return null;
      });
    },

    geometricAvatar: geometricAvatar
  };

  function hashString(str) {
    var h = 2166136261 >>> 0;
    for (var i = 0; i < str.length; i++) {
      h ^= str.charCodeAt(i);
      h = Math.imul(h, 16777619) >>> 0;
    }
    return h >>> 0;
  }

  var AVATAR_PALETTE = [
    { bg: 'var(--surface-2)', a: '#6b7f9e', b: '#8fa3bd', c: '#4c5c74' },
    { bg: 'var(--surface-2)', a: '#7a9b76', b: '#a3bf9f', c: '#56704f' },
    { bg: 'var(--surface-2)', a: '#b08a6a', b: '#c9ac90', c: '#8a6844' },
    { bg: 'var(--surface-2)', a: '#8a7ea6', b: '#aca2c4', c: '#635a7d' },
    { bg: 'var(--surface-2)', a: '#a47f85', b: '#c7a5aa', c: '#7d5c62' },
    { bg: 'var(--surface-2)', a: '#6f9aa0', b: '#93b8bd', c: '#4c7075' }
  ];

  function geometricAvatar(seedStr, size) {
    var seed = String(seedStr == null ? '' : seedStr);
    var h = hashString(seed || 'anon');
    var pal = AVATAR_PALETTE[h % AVATAR_PALETTE.length];
    var s = size || 48;
    var r = s / 2;

    var variant = (h >> 3) % 4;

    var cx1 = (h >> 5) % 60 + 20;
    var cy1 = (h >> 9) % 60 + 20;
    var r1 = (h >> 13) % 10 + 14;

    var cx2 = (h >> 7) % 70 + 15;
    var cy2 = (h >> 11) % 70 + 15;
    var r2 = (h >> 17) % 8 + 10;

    var shapes = '';

    if (variant === 0) {
      shapes += '<circle cx="' + cx1 + '%" cy="' + cy1 + '%" r="' + r1 + '%" fill="' + pal.a + '" opacity="0.85"/>';
      shapes += '<circle cx="' + cx2 + '%" cy="' + cy2 + '%" r="' + r2 + '%" fill="' + pal.b + '" opacity="0.7"/>';
    } else if (variant === 1) {
      shapes += '<polygon points="' + (cx1) + ',' + (cy1 - r1) + ' ' + (cx1 + r1) + ',' + (cy1 + r1 * 0.6) + ' ' + (cx1 - r1) + ',' + (cy1 + r1 * 0.6) + '" fill="' + pal.a + '" opacity="0.85"/>';
      shapes += '<circle cx="' + cx2 + '%" cy="' + cy2 + '%" r="' + r2 + '%" fill="' + pal.b + '" opacity="0.7"/>';
    } else if (variant === 2) {
      shapes += '<path d="M ' + (cx1 - r1) + ' ' + cy1 + ' A ' + r1 + ' ' + r1 + ' 0 0 1 ' + (cx1 + r1) + ' ' + cy1 + '" stroke="' + pal.a + '" stroke-width="8" fill="none" stroke-linecap="round" opacity="0.85"/>';
      shapes += '<circle cx="' + cx2 + '%" cy="' + cy2 + '%" r="' + r2 + '%" fill="' + pal.b + '" opacity="0.7"/>';
    } else {
      shapes += '<circle cx="' + cx1 + '%" cy="' + cy1 + '%" r="' + r1 + '%" fill="' + pal.a + '" opacity="0.85"/>';
      shapes += '<polygon points="' + (cx2) + ',' + (cy2 - r2) + ' ' + (cx2 + r2) + ',' + (cy2 + r2 * 0.6) + ' ' + (cx2 - r2) + ',' + (cy2 + r2 * 0.6) + '" fill="' + pal.b + '" opacity="0.7"/>';
    }

    var svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="' + s + '" height="' + s + '" role="img" aria-label="头像">' +
      '<rect width="100" height="100" rx="' + (s >= 96 ? 24 : 999) + '" fill="' + pal.bg + '"/>' +
      shapes +
      '</svg>';

    return svg;
  }

  global.Auth = Auth;
})(window);

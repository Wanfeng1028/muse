(function () {
  'use strict';

  var listEl = document.getElementById('store-list');
  var emptyEl = document.getElementById('store-empty');
  var searchEl = document.getElementById('store-search');
  var fileEl = document.getElementById('store-file');
  var installBtn = document.getElementById('store-install-btn');

  var allPlugins = [];

  function iconForName(name) {
    var n = (name || '').toLowerCase();
    if (n.indexOf('file') >= 0) return 'folder';
    if (n.indexOf('editor') >= 0) return 'file-text';
    if (n.indexOf('terminal') >= 0) return 'terminal';
    if (n.indexOf('setting') >= 0) return 'settings';
    if (n.indexOf('theme') >= 0) return 'palette';
    if (n.indexOf('image') >= 0) return 'image';
    if (n.indexOf('music') >= 0) return 'music';
    if (n.indexOf('note') >= 0) return 'notebook';
    if (n.indexOf('git') >= 0) return 'git-branch';
    return 'puzzle';
  }

  function escapeHtml(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function renderList(plugins) {
    listEl.innerHTML = '';
    if (!plugins || plugins.length === 0) {
      emptyEl.style.display = 'block';
      return;
    }
    emptyEl.style.display = 'none';

    plugins.forEach(function (p) {
      var card = document.createElement('div');
      card.className = 'store-card';

      var iconName = iconForName(p.name);
      var versionText = p.version ? escapeHtml(p.version) : '1.0.0';
      var descText = p.description ? escapeHtml(p.description) : '暂无描述';

      var perms = Array.isArray(p.permissions) ? p.permissions : [];
      var permsHtml = perms.map(function (perm) {
        return '<span class="store-perm-tag">' + escapeHtml(perm) + '</span>';
      }).join('');

      var installed = !!p.installed;
      var actionLabel = installed ? '卸载' : '安装';
      var actionClass = installed ? 'store-btn' : 'store-btn primary';
      var actionIcon = installed ? 'trash-2' : 'download';

      card.innerHTML =
        '<div class="store-card-icon"><i data-lucide="' + iconName + '"></i></div>' +
        '<div class="store-card-body">' +
          '<div class="store-card-top">' +
            '<span class="store-card-name">' + escapeHtml(p.name) + '</span>' +
            '<span class="store-card-version">v' + versionText + '</span>' +
          '</div>' +
          '<p class="store-card-desc">' + descText + '</p>' +
          '<div class="store-card-perms">' + permsHtml + '</div>' +
          '<div class="store-card-actions">' +
            '<button type="button" class="' + actionClass + '" data-id="' + escapeHtml(p.id) + '" data-installed="' + installed + '">' +
              '<i data-lucide="' + actionIcon + '"></i>' +
              '<span>' + actionLabel + '</span>' +
            '</button>' +
          '</div>' +
          '<div class="store-error" data-error-for="' + escapeHtml(p.id) + '"></div>' +
        '</div>';

      listEl.appendChild(card);
    });

    if (window.lucide && typeof window.lucide.createIcons === 'function') {
      window.lucide.createIcons();
    }

    var buttons = listEl.querySelectorAll('button[data-id]');
    buttons.forEach(function (btn) {
      btn.addEventListener('click', function () {
        var id = btn.getAttribute('data-id');
        var isInstalled = btn.getAttribute('data-installed') === 'true';
        if (isInstalled) {
          uninstallPlugin(id);
        } else {
          installFromCard(id);
        }
      });
    });
  }

  function showError(id, message) {
    var el = listEl.querySelector('[data-error-for="' + id + '"]');
    if (el) {
      el.textContent = message;
      el.style.display = 'block';
    }
  }

  function clearErrors() {
    var errs = listEl.querySelectorAll('.store-error');
    errs.forEach(function (el) {
      el.textContent = '';
      el.style.display = 'none';
    });
  }

  function loadPlugins() {
    return fetch('/api/plugins', { method: 'GET' })
      .then(function (res) {
        if (!res.ok) {
          throw new Error('加载插件列表失败（HTTP ' + res.status + '）');
        }
        return res.json();
      })
      .then(function (data) {
        allPlugins = Array.isArray(data) ? data : (data && Array.isArray(data.plugins) ? data.plugins : []);
        applyFilter();
      })
      .catch(function (err) {
        listEl.innerHTML = '';
        emptyEl.style.display = 'block';
        emptyEl.textContent = '加载插件列表失败：' + err.message;
      });
  }

  function applyFilter() {
    var keyword = (searchEl.value || '').trim().toLowerCase();
    if (!keyword) {
      renderList(allPlugins);
      return;
    }
    var filtered = allPlugins.filter(function (p) {
      var name = (p.name || '').toLowerCase();
      var desc = (p.description || '').toLowerCase();
      return name.indexOf(keyword) >= 0 || desc.indexOf(keyword) >= 0;
    });
    renderList(filtered);
  }

  function installFromCard(id) {
    clearErrors();
    fetch('/api/plugins/install', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: id })
    })
      .then(function (res) {
        if (!res.ok) {
          return res.text().then(function (text) {
            throw new Error(text || ('安装失败（HTTP ' + res.status + '）'));
          });
        }
        return res.json().catch(function () { return {}; });
      })
      .then(function () {
        return loadPlugins();
      })
      .catch(function (err) {
        showError(id, '安装失败：' + err.message);
      });
  }

  function uninstallPlugin(id) {
    clearErrors();
    fetch('/api/plugins/' + encodeURIComponent(id), { method: 'DELETE' })
      .then(function (res) {
        if (!res.ok) {
          return res.text().then(function (text) {
            throw new Error(text || ('卸载失败（HTTP ' + res.status + '）'));
          });
        }
        return res.json().catch(function () { return {}; });
      })
      .then(function () {
        return loadPlugins();
      })
      .catch(function (err) {
        showError(id, '卸载失败：' + err.message);
      });
  }

  function uploadAndInstall() {
    var file = fileEl.files && fileEl.files[0];
    if (!file) {
      return;
    }
    clearErrors();
    installBtn.disabled = true;

    var form = new FormData();
    form.append('file', file);

    fetch('/api/plugins/install', {
      method: 'POST',
      body: form
    })
      .then(function (res) {
        if (!res.ok) {
          return res.text().then(function (text) {
            throw new Error(text || ('安装失败（HTTP ' + res.status + '）'));
          });
        }
        return res.json().catch(function () { return {}; });
      })
      .then(function () {
        fileEl.value = '';
        return loadPlugins();
      })
      .catch(function (err) {
        emptyEl.style.display = 'block';
        emptyEl.textContent = '安装失败：' + err.message;
      })
      .then(function () {
        installBtn.disabled = false;
      });
  }

  if (installBtn) {
    installBtn.addEventListener('click', uploadAndInstall);
  }
  if (searchEl) {
    searchEl.addEventListener('input', applyFilter);
  }

  loadPlugins();
})();

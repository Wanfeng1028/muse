// ==================== 通用工具 ====================

/**
 * fetch JSON 封装
 * @param {string} path 请求路径
 * @param {object} opts fetch 选项
 * @returns {Promise<any>}
 */
// API Token：首次 401 时弹窗索取，存 sessionStorage。
function sentinelToken() {
  return sessionStorage.getItem('sentinel_token') || '';
}

function askSentinelToken() {
  if (typeof window.__sentinelAskToken === 'function') {
    return window.__sentinelAskToken();
  }
  const t = prompt('需要 API Token 才能访问（SENTINEL_API_TOKEN），请输入：');
  if (t) sessionStorage.setItem('sentinel_token', t.trim());
  return Promise.resolve();
}
window.__sentinelAskToken = window.__sentinelAskToken || null;

async function api(path, opts = {}, _retried) {
  const headers = {
    'Content-Type': 'application/json',
    ...(opts.headers || {})
  };
  const token = sentinelToken();
  // 公开状态页接口不带 token
  if (token && !path.startsWith('/api/status/')) {
    headers['Authorization'] = 'Bearer ' + token;
  }
  const res = await fetch(path, { ...opts, headers });

  if (res.status === 401 && !_retried && !path.startsWith('/api/status/')) {
    const r = askSentinelToken();
    if (r && r.then) await r;
    if (sentinelToken()) return api(path, opts, true);
  }

  if (!res.ok) {
    let msg = String(res.status);
    try {
      const data = await res.json();
      if (data && data.error) msg = data.error;
    } catch (_) {
      // 忽略解析错误
    }
    throw new Error(msg);
  }

  // 204 等无内容情况
  if (res.status === 204) return null;
  try {
    return await res.json();
  } catch (_) {
    return null;
  }
}

/**
 * HTML 转义
 * @param {any} s
 * @returns {string}
 */
function esc(s) {
  if (s === null || s === undefined) return '';
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/**
 * ISO 时间格式化 -> "MM-DD HH:mm"
 * @param {string} iso
 * @returns {string}
 */
function fmtTime(iso) {
  if (!iso) return '-';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '-';
  const pad = (n) => String(n).padStart(2, '0');
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/**
 * 时长 human 化
 * <60s -> "Xs"；<1h -> "Xm"；否则 "XhYm"
 * @param {number} sec
 * @returns {string}
 */
function fmtDur(sec) {
  if (sec === null || sec === undefined || isNaN(sec)) return '-';
  sec = Number(sec);
  if (sec < 0) sec = 0;
  if (sec < 60) return `${Math.floor(sec)}s`;
  if (sec < 3600) return `${Math.floor(sec / 60)}m`;
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  return `${h}h${m}m`;
}

// ==================== Dashboard ====================

/**
 * 仪表盘初始化
 */
async function initDashboard() {
  const overviewEl = document.getElementById('overview');
  const listEl = document.getElementById('monitor-list');
  const incidentsEl = document.getElementById('recent-incidents');

  // 全部不存在则直接返回
  if (!overviewEl && !listEl && !incidentsEl) return;

  try {
    const tasks = [];
    tasks.push(
      overviewEl
        ? api('/api/overview').then((data) => renderOverview(overviewEl, data))
        : Promise.resolve()
    );
    tasks.push(
      listEl
        ? api('/api/monitors').then((data) => renderMonitorList(listEl, data))
        : Promise.resolve()
    );
    tasks.push(
      incidentsEl
        ? api('/api/incidents?limit=10').then((data) => renderRecentIncidents(incidentsEl, data))
        : Promise.resolve()
    );

    await Promise.all(tasks);
  } catch (err) {
    console.error('[initDashboard]', err);
    if (overviewEl) {
      overviewEl.innerHTML = `<div class="error">加载失败：${esc(err.message)}</div>`;
    }
  }
}

/**
 * 渲染概览七张卡
 * @param {HTMLElement} el
 * @param {object} data
 */
function renderOverview(el, data) {
  const d = data || {};
  const cards = [
    { label: '监控总数', value: d.total_monitors ?? 0 },
    { label: '正常', value: d.up_monitors ?? 0, cls: 'ok' },
    { label: '异常', value: d.down_monitors ?? 0, cls: 'down' },
    { label: '未知', value: d.unknown_monitors ?? 0, cls: 'unknown' },
    { label: '24h 可用率', value: d.uptime_24h != null ? `${Number(d.uptime_24h).toFixed(2)}%` : '-' },
    { label: '24h 事故数', value: d.incidents_24h ?? 0 },
    { label: '平均响应', value: d.avg_latency_ms != null ? `${Math.round(d.avg_latency_ms)}ms` : '-' }
  ];

  el.innerHTML = cards
    .map(
      (c) => `
    <div class="card ${c.cls || ''}">
      <div class="card-value">${esc(c.value)}</div>
      <div class="card-label">${esc(c.label)}</div>
    </div>`
    )
    .join('');
}

/**
 * 渲染监控列表
 * @param {HTMLElement} el
 * @param {Array} monitors
 */
function renderMonitorList(el, monitors) {
  const list = Array.isArray(monitors) ? monitors : [];

  if (list.length === 0) {
    el.innerHTML = '<div class="empty">暂无监控</div>';
    return;
  }

  el.innerHTML = list
    .map((m) => {
      // 状态圆点
      let dotCls = 'dot-unknown';
      if (m.last_ok === true) dotCls = 'dot-ok';
      else if (m.last_ok === false) dotCls = 'dot-down';

      const uptime =
        m.uptime_24h != null ? `${Number(m.uptime_24h).toFixed(2)}%` : '-';
      const lastChecked = fmtTime(m.last_checked_at);

      return `
      <div class="monitor-row" data-id="${esc(m.id)}">
        <span class="dot ${dotCls}" title="${
        m.last_ok === true ? '正常' : m.last_ok === false ? '异常' : '未知'
      }"></span>
        <span class="m-name">${esc(m.name || '(未命名)')}</span>
        <span class="m-target">${esc(m.target || '')}</span>
        <span class="m-uptime">${esc(uptime)}</span>
        <span class="m-time">${esc(lastChecked)}</span>
      </div>`;
    })
    .join('');
}

/**
 * 渲染最近事故（前 10 条）
 * @param {HTMLElement} el
 * @param {Array} incidents
 */
function renderRecentIncidents(el, incidents) {
  const list = Array.isArray(incidents) ? incidents.slice(0, 10) : [];

  if (list.length === 0) {
    el.innerHTML = '<div class="empty">暂无事故</div>';
    return;
  }

  el.innerHTML = list
    .map((it) => {
      const started = fmtTime(it.started_at);
      const dur =
        it.duration_sec != null
          ? fmtDur(it.duration_sec)
          : it.resolved_at
          ? fmtDur((new Date(it.resolved_at) - new Date(it.started_at)) / 1000)
          : '进行中';
      const name = it.monitor_name || it.name || `#${it.monitor_id}`;
      const reason = it.reason || it.message || '';
      const resolved = it.resolved_at ? '已恢复' : '未恢复';
      return `
      <div class="incident-row ${it.resolved_at ? 'resolved' : 'ongoing'}">
        <span class="i-name">${esc(name)}</span>
        <span class="i-time">${esc(started)}</span>
        <span class="i-dur">${esc(dur)}</span>
        <span class="i-status">${esc(resolved)}</span>
        <span class="i-reason">${esc(reason)}</span>
      </div>`;
    })
    .join('');
}

// ==================== Monitors 页面 ====================

/**
 * 监控管理页面初始化
 */
async function initMonitorsPage() {
  const tableEl = document.getElementById('monitor-table');
  const formEl = document.getElementById('monitor-form');
  const rowMethod = document.getElementById('row-method');
  const rowExpected = document.getElementById('row-expected');
  const kindEl = document.getElementById('f-kind');

  if (!tableEl && !formEl) return;

  // 保存当前编辑 id
  let editingId = null;

  async function loadMonitors() {
    if (!tableEl) return;
    try {
      const data = await api('/api/monitors');
      renderMonitorTable(tableEl, data);
      bindTableActions();
    } catch (err) {
      console.error('[loadMonitors]', err);
      tableEl.innerHTML = `<div class="error">加载失败：${esc(err.message)}</div>`;
    }
  }

  function renderMonitorTable(el, monitors) {
    const list = Array.isArray(monitors) ? monitors : [];
    if (list.length === 0) {
      el.innerHTML = '<div class="empty">暂无监控</div>';
      return;
    }
    el.innerHTML = `
      <table>
        <thead>
          <tr>
            <th>名称</th>
            <th>类型</th>
            <th>目标</th>
            <th>状态</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          ${list
            .map((m) => {
              let dotCls = 'dot-unknown';
              if (m.last_ok === true) dotCls = 'dot-ok';
              else if (m.last_ok === false) dotCls = 'dot-down';
              return `
              <tr data-id="${esc(m.id)}">
                <td>${esc(m.name || '')}</td>
                <td>${esc(m.kind || '')}</td>
                <td>${esc(m.target || '')}</td>
                <td><span class="dot ${dotCls}"></span></td>
                <td class="actions">
                  <button type="button" data-act="check">立即检查</button>
                  <button type="button" data-act="edit">编辑</button>
                  <button type="button" data-act="delete">删除</button>
                </td>
              </tr>`;
            })
            .join('')}
        </tbody>
      </table>`;

    // 保存列表数据供编辑使用
    el._monitors = list;
  }

  function bindTableActions() {
    if (!tableEl) return;
    tableEl.querySelectorAll('tr[data-id]').forEach((tr) => {
      tr.addEventListener('click', async (ev) => {
        const btn = ev.target.closest('button[data-act]');
        if (!btn) return;
        const id = tr.getAttribute('data-id');
        const act = btn.getAttribute('data-act');

        if (act === 'delete') {
          if (!confirm('确定删除该监控？')) return;
          try {
            await api(`/api/monitors/${encodeURIComponent(id)}`, { method: 'DELETE' });
            await loadMonitors();
          } catch (err) {
            alert('删除失败：' + err.message);
          }
        } else if (act === 'check') {
          try {
            const result = await api(`/api/monitors/${encodeURIComponent(id)}/check`, {
              method: 'POST'
            });
            let msg = '检查完成';
            if (result) {
              if (result.ok != null) msg += result.ok ? '：正常' : '：异常';
              if (result.latency_ms != null) msg += `（${Math.round(result.latency_ms)}ms）`;
              if (result.error) msg += ` - ${result.error}`;
            }
            alert(msg);
            await loadMonitors();
          } catch (err) {
            alert('检查失败：' + err.message);
          }
        } else if (act === 'edit') {
          const list = tableEl._monitors || [];
          const item = list.find((x) => String(x.id) === String(id));
          if (!item) return;
          editingId = item.id;
          fillForm(item);
        }
      });
    });
  }

  // kind 切换时隐藏/显示 method、expected 行
  function updateKindRows() {
    if (!kindEl) return;
    const isTcp = kindEl.value === 'tcp';
    if (rowMethod) rowMethod.style.display = isTcp ? 'none' : '';
    if (rowExpected) rowExpected.style.display = isTcp ? 'none' : '';
  }

  function fillForm(item) {
    if (!formEl) return;
    const set = (name, val) => {
      const el = formEl.querySelector(`[name="${name}"]`);
      if (el) el.value = val != null ? val : '';
    };
    set('name', item.name);
    set('kind', item.kind);
    set('target', item.target);
    set('method', item.method);
    set('expected', item.expected);
    set('interval_sec', item.interval_sec);
    set('timeout_sec', item.timeout_sec);
    updateKindRows();
    const title = document.getElementById('form-title');
    if (title) title.textContent = '编辑监控';
  }

  function resetForm() {
    if (!formEl) return;
    formEl.reset();
    editingId = null;
    const title = document.getElementById('form-title');
    if (title) title.textContent = '新建监控';
    updateKindRows();
  }

  // 绑定 kind 切换
  if (kindEl) {
    kindEl.addEventListener('change', updateKindRows);
    updateKindRows();
  }

  // 表单提交
  if (formEl) {
    formEl.addEventListener('submit', async (ev) => {
      ev.preventDefault();
      const fd = new FormData(formEl);
      const payload = {};
      fd.forEach((v, k) => {
        payload[k] = v;
      });
      // 数值字段转换
      ['interval_sec', 'timeout_sec'].forEach((k) => {
        if (payload[k] !== undefined && payload[k] !== '') {
          payload[k] = Number(payload[k]);
        }
      });
      // tcp 时移除 method / expected
      if (payload.kind === 'tcp') {
        delete payload.method;
        delete payload.expected;
      }

      try {
        if (editingId != null) {
          await api(`/api/monitors/${encodeURIComponent(editingId)}`, {
            method: 'PUT',
            body: JSON.stringify(payload)
          });
        } else {
          await api('/api/monitors', {
            method: 'POST',
            body: JSON.stringify(payload)
          });
        }
        resetForm();
        await loadMonitors();
      } catch (err) {
        alert('保存失败：' + err.message);
      }
    });
  }

  await loadMonitors();
}

// ==================== Incidents 页面 ====================

/**
 * 事故页面初始化
 */
async function initIncidentsPage() {
  const filterEl = document.getElementById('f-monitor');
  const tableEl = document.getElementById('incident-table');

  if (!filterEl && !tableEl) return;

  // 填充监控下拉
  if (filterEl) {
    try {
      const monitors = await api('/api/monitors');
      const list = Array.isArray(monitors) ? monitors : [];
      filterEl.innerHTML =
        '<option value="">全部</option>' +
        list
          .map(
            (m) =>
              `<option value="${esc(m.id)}">${esc(m.name || m.target || '#' + m.id)}</option>`
          )
          .join('');
    } catch (err) {
      console.error('[initIncidentsPage] 加载监控失败', err);
    }

    filterEl.addEventListener('change', () => loadIncidents());
  }

  async function loadIncidents() {
    if (!tableEl) return;
    const monitorId = filterEl ? filterEl.value : '';
    const qs = monitorId ? `?monitor_id=${encodeURIComponent(monitorId)}&limit=100` : '?limit=100';

    try {
      const data = await api('/api/incidents' + qs);
      renderIncidentTable(tableEl, data);
    } catch (err) {
      console.error('[loadIncidents]', err);
      tableEl.innerHTML = `<div class="error">加载失败：${esc(err.message)}</div>`;
    }
  }

  function renderIncidentTable(el, incidents) {
    const list = Array.isArray(incidents) ? incidents : [];
    if (list.length === 0) {
      el.innerHTML = '<div class="empty">暂无事故</div>';
      return;
    }
    el.innerHTML = `
      <table>
        <thead>
          <tr>
            <th>监控</th>
            <th>开始时间</th>
            <th>恢复时间</th>
            <th>持续</th>
            <th>状态</th>
            <th>原因</th>
          </tr>
        </thead>
        <tbody>
          ${list
            .map((it) => {
              const name = it.monitor_name || it.name || `#${it.monitor_id}`;
              const started = fmtTime(it.started_at);
              const resolvedAt = it.resolved_at ? fmtTime(it.resolved_at) : '-';
              let dur = '-';
              if (it.duration_sec != null) {
                dur = fmtDur(it.duration_sec);
              } else if (it.resolved_at && it.started_at) {
                dur = fmtDur(
                  (new Date(it.resolved_at) - new Date(it.started_at)) / 1000
                );
              } else {
                dur = '进行中';
              }
              const status = it.resolved_at ? '已恢复' : '未恢复';
              const reason = it.reason || it.message || '';
              return `
              <tr class="${it.resolved_at ? 'resolved' : 'ongoing'}">
                <td>${esc(name)}</td>
                <td>${esc(started)}</td>
                <td>${esc(resolvedAt)}</td>
                <td>${esc(dur)}</td>
                <td>${esc(status)}</td>
                <td>${esc(reason)}</td>
              </tr>`;
            })
            .join('')}
        </tbody>
      </table>`;
  }

  await loadIncidents();
}

// ==================== 自动分发 ====================

document.addEventListener('DOMContentLoaded', () => {
  // 根据页面元素决定初始化哪个
  if (document.getElementById('monitor-table') || document.getElementById('monitor-form')) {
    initMonitorsPage();
  } else if (document.getElementById('incident-table') || document.getElementById('f-monitor')) {
    initIncidentsPage();
  } else if (
    document.getElementById('overview') ||
    document.getElementById('monitor-list') ||
    document.getElementById('recent-incidents')
  ) {
    initDashboard();
  }
});

// 暴露到全局，方便手动调用
window.api = api;
window.esc = esc;
window.fmtTime = fmtTime;
window.fmtDur = fmtDur;
window.initDashboard = initDashboard;
window.initMonitorsPage = initMonitorsPage;
window.initIncidentsPage = initIncidentsPage;

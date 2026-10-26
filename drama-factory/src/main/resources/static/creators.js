(function () {
  'use strict';

  var PAGE_I18N = {
    'cr.pageTitle': { 'zh-CN': '创作者计划 · AI 短剧工坊', 'en': 'Creator Program · AI Short Drama Studio' },
    'cr.heading': { 'zh-CN': '创作者计划', 'en': 'Creator Program' },
    'cr.subtitle': { 'zh-CN': '创作者主页、资料与关注；分成与激励规则待商业方案公布', 'en': 'Creator pages, profiles, and follows; incentive and revenue rules are pending a commercial decision' },
    'cr.search': { 'zh-CN': '搜索', 'en': 'Search' },
    'cr.searchPh': { 'zh-CN': '按主页标识或名称搜索', 'en': 'Search by handle or name' },
    'cr.sort': { 'zh-CN': '排序', 'en': 'Sort' },
    'cr.sortNewest': { 'zh-CN': '最新创建', 'en': 'Newest' },
    'cr.sortFollowers': { 'zh-CN': '关注最多', 'en': 'Most followed' },
    'cr.sortSkills': { 'zh-CN': 'Skill 最多', 'en': 'Most Skills' },
    'cr.empty': { 'zh-CN': '还没有创作者主页', 'en': 'No creator pages yet' },
    'cr.formTitle': { 'zh-CN': '创建或编辑我的主页', 'en': 'Create or edit my page' },
    'cr.handle': { 'zh-CN': '主页标识', 'en': 'Handle' },
    'cr.handlePh': { 'zh-CN': '小写字母/数字/短横线，如 neo', 'en': 'Lowercase letters, digits, or hyphens, e.g. neo' },
    'cr.displayName': { 'zh-CN': '展示名称', 'en': 'Display name' },
    'cr.bio': { 'zh-CN': '简介', 'en': 'Bio' },
    'cr.website': { 'zh-CN': '个人网站', 'en': 'Website' },
    'cr.save': { 'zh-CN': '保存主页', 'en': 'Save page' },
    'cr.incentiveNote': { 'zh-CN': '分成与激励规则尚未公布，这里不展示任何收益数字', 'en': 'Incentive and revenue rules are not announced yet, so no income figures are shown here' },
    'cr.skills': { 'zh-CN': 'Skill', 'en': 'Skills' },
    'cr.installs': { 'zh-CN': '安装', 'en': 'Installs' },
    'cr.rating': { 'zh-CN': '评分', 'en': 'Rating' },
    'cr.ratingNone': { 'zh-CN': '暂无评分', 'en': 'No ratings yet' },
    'cr.followers': { 'zh-CN': '关注', 'en': 'Followers' },
    'cr.follow': { 'zh-CN': '关注', 'en': 'Follow' },
    'cr.unfollow': { 'zh-CN': '取消关注', 'en': 'Unfollow' },
    'cr.followed': { 'zh-CN': '已关注', 'en': 'Followed' },
    'cr.unfollowed': { 'zh-CN': '已取消关注', 'en': 'Unfollowed' },
    'cr.loadFailed': { 'zh-CN': '加载失败', 'en': 'Failed to load' },
    'cr.saveSuccess': { 'zh-CN': '保存成功', 'en': 'Saved' },
    'cr.saveFailed': { 'zh-CN': '保存失败', 'en': 'Save failed' },
    'cr.detailFailed': { 'zh-CN': '加载详情失败', 'en': 'Failed to load details' },
    'cr.back': { 'zh-CN': '返回列表', 'en': 'Back to list' },
    'cr.viewDetail': { 'zh-CN': '查看主页', 'en': 'View page' },
    'cr.feedTitle': { 'zh-CN': '关注动态', 'en': 'Following feed' },
    'cr.feedEmpty': { 'zh-CN': '还没有关注动态：先关注创作者，或关注的创作者暂未发布新 Skill', 'en': 'No following feed yet: follow creators first, or followed creators have not published new Skills' },
    'cr.feedRefresh': { 'zh-CN': '刷新动态', 'en': 'Refresh feed' },
  };

  if (window.DFI18N && typeof window.DFI18N.register === 'function') { window.DFI18N.register(PAGE_I18N); }
  // 翻译辅助：优先 DFI18N，否则返回 fallback（与 skills.js 同款约定）
  function _t(key, fallback) {
    try {
      if (window.DFI18N && typeof window.DFI18N.tr === 'function') {
        var v = window.DFI18N.tr(key);
        if (v && v !== key) return v;
      }
    } catch (e) { /* 忽略，走 fallback */ }
    return fallback;
  }

// HTML 转义，防止 XSS
function esc(s) {
  if (s === null || s === undefined) return '';
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

// 格式化时间为 YYYY-MM-DD HH:mm，无效则原样返回
function fmtDateTime(s) {
  if (!s) return '';
  const d = new Date(s);
  if (isNaN(d.getTime())) return String(s);
  const p = (n) => String(n).padStart(2, '0');
  return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate()) + ' ' + p(d.getHours()) + ':' + p(d.getMinutes());
}

// 显示全局提示，2.5 秒后自动隐藏
function showToast(msg) {
  const el = document.getElementById('toast');
  if (el) {
    el.textContent = msg;
    el.hidden = false;
    setTimeout(() => { el.hidden = true; }, 2500);
  } else {
    const div = document.createElement('div');
    div.className = 'toast';
    div.textContent = msg;
    document.body.appendChild(div);
    setTimeout(() => { div.remove(); }, 2500);
  }
}

// fetch 封装：非 2xx 抛出携带服务端 detail/message 的错误，204 返回 null
async function api(path, options) {
  const opts = Object.assign({}, options);
  if (opts.body !== null && typeof opts.body === 'object') {
    opts.body = JSON.stringify(opts.body);
    opts.headers = Object.assign({ 'Content-Type': 'application/json' }, opts.headers || {});
  }
  const res = await fetch(path, opts);
  if (!res.ok) {
    let msg = res.statusText || ('HTTP ' + res.status);
    try {
      const data = await res.json();
      if (data && (data.detail || data.message)) msg = data.detail || data.message;
    } catch (e) { /* 保留默认消息 */ }
    throw new Error(msg);
  }
  if (res.status === 204) return null;
  return res.json();
}

// 按搜索词与排序加载创作者列表并渲染卡片
async function loadCreators() {
  const grid = document.getElementById('creatorGrid');
  if (!grid) return;
  const empty = document.getElementById('creatorEmpty');
  const searchEl = document.getElementById('creatorSearch');
  const sortEl = document.getElementById('creatorSort');
  const search = searchEl ? searchEl.value.trim() : '';
  const sort = sortEl ? sortEl.value : '';
  try {
    const list = await api('/api/creators?search=' + encodeURIComponent(search) + '&sort=' + encodeURIComponent(sort));
    const items = Array.isArray(list) ? list : [];
    grid.innerHTML = items.map((c) => (
      '<div class="card mb-3">' +
        '<div class="card-body">' +
          '<div class="d-flex align-items-center gap-2 mb-2"><strong>' + esc(c.displayName) + '</strong><span class="text-muted">@' + esc(c.handle) + '</span></div>' +
          '<p class="text-muted mb-2">' + esc(c.bio || '') + '</p>' +
          '<div class="mb-2">Skill ' + esc(c.skillCount ?? 0) + ' · 关注 ' + esc(c.followerCount ?? 0) + '</div>' +
          '<button type="button" class="btn btn-outline-primary creator-detail-btn" data-detail-handle="' + esc(c.handle) + '">' + esc(_t('cr.viewDetail', '查看主页')) + '</button>' +
        '</div>' +
      '</div>'
    )).join('');
    if (empty) empty.hidden = items.length > 0;
  } catch (err) {
    showToast(_t('cr.loadFailed', '加载失败'));
  }
}

// 当前详情卡展示的创作者及其关注状态
let currentHandle = null;
let currentFollowed = false;

// 拉取并渲染单个创作者详情卡片
async function showDetail(handle) {
  try {
    const detail = await api('/api/creators/' + encodeURIComponent(handle));
    const ratingNone = _t('cr.ratingNone', '暂无评分');
    document.getElementById('creatorDetailCard').hidden = false;
    document.getElementById('creatorDetailTitle').textContent = (detail.displayName || '') + ' @' + (detail.handle || handle);
    document.getElementById('creatorDetailBio').textContent = detail.bio || '';
    document.getElementById('creatorStatSkills').textContent = detail.skillCount;
    document.getElementById('creatorStatInstalls').textContent = detail.totalInstalls;
    document.getElementById('creatorStatRating').textContent = detail.avgRating == null ? ratingNone : Number(detail.avgRating).toFixed(1);
    document.getElementById('creatorStatFollowers').textContent = detail.followerCount;
    document.getElementById('creatorDetailSkills').innerHTML = (detail.skills || []).map(function (s) {
      return '<div>' + esc((s.name || '') + ' · 安装 ' + (s.installCount || 0) + ' · ' + (s.avgRating == null ? ratingNone : Number(s.avgRating).toFixed(1))) + '</div>';
    }).join('');
    document.getElementById('creatorFollowBtn').textContent = detail.followedByMe ? _t('cr.unfollow', '取消关注') : _t('cr.follow', '关注');
    currentHandle = detail.handle || handle;
    currentFollowed = !!detail.followedByMe;
  } catch (err) {
    showToast(_t('cr.detailFailed', '加载详情失败'));
  }
}

// 关注/取消关注当前详情卡中的创作者
async function toggleFollow() {
  if (!currentHandle) return;
  try {
    const method = currentFollowed ? 'DELETE' : 'POST';
    const res = await api('/api/creators/' + encodeURIComponent(currentHandle) + '/follow', { method: method });
    if (typeof res.followed === 'boolean') currentFollowed = res.followed;
    document.getElementById('creatorFollowBtn').textContent = currentFollowed ? _t('cr.unfollow', '取消关注') : _t('cr.follow', '关注');
    if (res.followerCount != null) document.getElementById('creatorStatFollowers').textContent = res.followerCount;
    showToast(method === 'POST' ? _t('cr.followed', '已关注') : _t('cr.unfollowed', '已取消关注'));
    loadFeed();
  } catch (err) {
    showToast(_t('cr.saveFailed', '保存失败'));
  }
}

// 保存创作者：先尝试按 handle 更新（PUT），不存在或失败则创建（POST），成功后刷新列表并展示详情
async function submitForm(e) {
  e.preventDefault();
  const handle = document.getElementById('crHandle').value.trim();
  const displayName = document.getElementById('crDisplayName').value.trim();
  const bio = document.getElementById('crBio').value.trim();
  const website = document.getElementById('crWebsite').value.trim();
  if (!handle) {
    showToast(_t('cr.saveFailed', '保存失败'));
    return;
  }
  const body = { handle: handle, displayName: displayName, bio: bio, website: website };
  try {
    try {
      await api('/api/creators/' + encodeURIComponent(handle), { method: 'PUT', body: body });
    } catch (err) {
      await api('/api/creators', { method: 'POST', body: body });
    }
    showToast(_t('cr.saveSuccess', '保存成功'));
    loadCreators();
    showDetail(handle);
  } catch (err) {
    showToast(_t('cr.saveFailed', '保存失败'));
  }
}

async function loadFeed() {
  const grid = document.getElementById('creatorFeed');
  if (!grid) return;
  const empty = document.getElementById('creatorFeedEmpty');
  try {
    const list = await api('/api/creators/feed');
    const items = Array.isArray(list) ? list : [];
    grid.innerHTML = items.map((f) => (
      '<div class="col-12"><div class="card"><div class="card-body">'
      + '<div>' + esc((f.displayName || '') + ' @' + (f.handle || '')) + '</div>'
      + '<div>' + esc(f.skillName || '') + ' · 安装 ' + (f.installCount || 0) + ' · ' + (f.avgRating == null ? _t('cr.ratingNone', '暂无评分') : Number(f.avgRating).toFixed(1)) + '</div>'
      + '<div class="text-secondary">' + esc(f.skillDescription || '') + ' · ' + fmtDateTime(f.createdAt) + '</div>'
      + '</div></div></div>'
    )).join('');
    if (empty) empty.hidden = items.length > 0;
  } catch (err) {
    showToast(_t('cr.loadFailed', '加载失败'));
  }
}

// 初始化：应用 i18n，绑定搜索防抖/排序/详情/关注/返回/表单事件，并首次加载列表
document.addEventListener('DOMContentLoaded', function () {
  if (typeof DFI18N !== 'undefined' && DFI18N) DFI18N.applyI18n(document);
  let searchTimer = null;
  document.getElementById('creatorSearch').addEventListener('input', function () {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(loadCreators, 300);
  });
  document.getElementById('creatorSort').addEventListener('change', loadCreators);
  document.getElementById('creatorGrid').addEventListener('click', function (e) {
    const item = e.target.closest('[data-detail-handle]');
    if (item) showDetail(item.getAttribute('data-detail-handle'));
  });
  document.getElementById('creatorFollowBtn').addEventListener('click', toggleFollow);
  document.getElementById('creatorBackBtn').addEventListener('click', function () {
    document.getElementById('creatorDetailCard').hidden = true;
  });
  document.getElementById('creatorForm').addEventListener('submit', submitForm);
  document.getElementById('creatorFeedRefresh').addEventListener('click', loadFeed);
  loadCreators();
  loadFeed();
});
})();

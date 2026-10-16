(function () {
  'use strict';

  const state = { queue: [], idx: 0, total: 0, digestMode: false };

  const $el = (id) => document.getElementById(id);

  function refreshBadge() {
    return api('/api/review/stats')
      .then((stats) => {
        const dueToday = (stats && stats.dueToday) || 0;
        const badge = $el('review-badge');
        if (badge) {
          if (dueToday > 0) {
            badge.textContent = String(dueToday);
            badge.hidden = false;
          } else {
            badge.hidden = true;
          }
        }
        updateBanner(dueToday);
      })
      .catch(() => {});
  }

  function ensureBanner() {
    let banner = $el('review-banner');
    if (banner) return banner;
    const listPane = document.querySelector('.list-pane') || document.querySelector('#list-pane');
    if (!listPane) return null;
    const header = listPane.querySelector('.list-header') || listPane.querySelector('#list-header');
    banner = document.createElement('div');
    banner.className = 'review-banner';
    banner.id = 'review-banner';
    banner.innerHTML = '<span class="review-banner-text"></span>' +
      '<button id="btn-banner-start" type="button">开始复习</button>';
    if (header && header.parentNode === listPane) {
      listPane.insertBefore(banner, header);
    } else {
      listPane.insertBefore(banner, listPane.firstChild);
    }
    const btn = banner.querySelector('#btn-banner-start');
    btn.addEventListener('click', () => {
      if (window.__sbShowView) window.__sbShowView('review');
      window.__sbStartReview();
    });
    return banner;
  }

  function updateBanner(n) {
    const banner = ensureBanner();
    if (!banner) return;
    const textEl = banner.querySelector('.review-banner-text');
    const btn = banner.querySelector('#btn-banner-start');
    if (n > 0) {
      textEl.innerHTML = '今日待复习 <strong>' + n + '</strong> 篇';
      btn.hidden = false;
    } else {
      textEl.textContent = '今日复习已完成';
      btn.hidden = true;
    }
  }

  function renderCard() {
    const item = state.queue[state.idx];
    if (!item) {
      showDone();
      return;
    }
    const progress = $el('review-progress');
    if (progress) progress.textContent = (state.idx + 1) + ' / ' + state.queue.length;

    const titleEl = $el('review-title');
    const snippetEl = $el('review-snippet');
    const tagsEl = $el('review-tags');
    const front = $el('review-front');
    const back = $el('review-back');
    const grading = $el('review-grading');
    const done = $el('review-done');
    const card = $el('review-card');

    let title = item.title || '';
    if (state.digestMode && !/^今日回顾/.test(title)) {
      title = '今日回顾 · ' + title;
    }
    if (titleEl) titleEl.textContent = title;
    if (snippetEl) snippetEl.textContent = item.snippet || '';
    if (tagsEl) {
      tagsEl.innerHTML = '';
      const tags = item.tags || [];
      tags.forEach((t) => {
        const span = document.createElement('span');
        span.className = 'tag';
        span.textContent = t;
        tagsEl.appendChild(span);
      });
    }
    const full = $el('review-full');
    if (full) full.innerHTML = '';
    if (back) back.hidden = true;
    if (front) front.hidden = false;
    if (grading) grading.hidden = false;
    if (done) done.hidden = true;
    if (card) card.hidden = false;
  }

  function showDone() {
    const card = $el('review-card');
    const grading = $el('review-grading');
    const done = $el('review-done');
    if (card) card.hidden = true;
    if (grading) grading.hidden = true;
    if (done) done.hidden = false;
    api('/api/review/stats')
      .then((stats) => {
        const total = state.total || 0;
        const streakDays = (stats && stats.streakDays) || 0;
        const textEl = $el('review-done-text');
        if (textEl) {
          textEl.textContent = '今天复习了 ' + total + ' 篇，连续坚持 ' + streakDays + ' 天';
        }
        refreshBadge();
      })
      .catch(() => {
        refreshBadge();
      });
  }

  function showEmpty() {
    const card = $el('review-card');
    const grading = $el('review-grading');
    const done = $el('review-done');
    const titleEl = $el('review-title');
    const snippetEl = $el('review-snippet');
    const tagsEl = $el('review-tags');
    const front = $el('review-front');
    const back = $el('review-back');
    const flip = $el('btn-flip');
    const progress = $el('review-progress');

    if (card) card.hidden = false;
    if (grading) grading.hidden = true;
    if (done) done.hidden = false;
    if (front) front.hidden = false;
    if (back) back.hidden = true;
    if (flip) flip.hidden = true;
    if (titleEl) titleEl.textContent = '今天没有待复习的';
    if (snippetEl) snippetEl.textContent = '新笔记明天会自动出现在这里';
    if (tagsEl) tagsEl.innerHTML = '';
    if (progress) progress.textContent = '';

    const doneBtn = done ? done.querySelector('button') : null;
    const doneText = $el('review-done-text');
    if (doneText) doneText.textContent = '都复习完了';
  }

  window.__sbStartReview = async function () {
    state.digestMode = false;
    const flip = $el('btn-flip');
    if (flip) flip.hidden = false;
    try {
      const res = await api('/api/review/queue?limit=50');
      const notes = (res && res.notes) || (Array.isArray(res) ? res : []);
      state.queue = notes;
      state.idx = 0;
      state.total = notes.length;
      if (!notes.length) {
        showEmpty();
        refreshBadge();
        return;
      }
      renderCard();
    } catch (e) {
      state.queue = [];
      state.idx = 0;
      state.total = 0;
      showEmpty();
      refreshBadge();
    }
  };

  function bindFlip() {
    const btnFlip = $el('btn-flip');
    const btnUnflip = $el('btn-unflip');
    if (btnFlip) {
      btnFlip.addEventListener('click', async () => {
        const item = state.queue[state.idx];
        if (!item) return;
        const full = $el('review-full');
        const front = $el('review-front');
        const back = $el('review-back');
        try {
          const res = await api('/api/notes/' + encodeURIComponent(item.id) + '/preview');
          let html = '';
          if (res && typeof res === 'object') {
            html = res.html || res.content || res.preview || '';
          } else if (typeof res === 'string') {
            html = res;
          }
          if (full) full.innerHTML = html;
        } catch (e) {
          if (full) full.innerHTML = '';
        }
        if (front) front.hidden = true;
        if (back) back.hidden = false;
      });
    }
    if (btnUnflip) {
      btnUnflip.addEventListener('click', () => {
        const front = $el('review-front');
        const back = $el('review-back');
        if (front) front.hidden = false;
        if (back) back.hidden = true;
      });
    }
  }

  function bindGrades() {
    [0, 3, 4, 5].forEach((g) => {
      const btn = $el('grade-' + g);
      if (!btn) return;
      btn.addEventListener('click', async () => {
        const item = state.queue[state.idx];
        if (!item) return;
        try {
          await api('/api/review/' + encodeURIComponent(item.id), {
            method: 'POST',
            body: { grade: g },
          });
        } catch (e) {
          // 离线判定：无网络，或 fetch 类网络错误
          if (!navigator.onLine || /failed to fetch|networkerror|load failed/i.test(e.message || '')) {
            // 注意：离线评分回放时按默认 local 用户归属，多用户场景下离线评分可能串用户，已在文档诚实声明
            await window.__sbOfflineQueue?.enqueue({
              method: 'POST',
              url: '/api/review/' + encodeURIComponent(item.id),
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ grade: g }),
            });
          }
          // 非离线错误：忽略错误，继续推进
        }
        state.idx += 1;
        if (state.idx < state.queue.length) {
          renderCard();
        } else {
          showDone();
        }
      });
    });
  }

  function bindDigest() {
    const btn = $el('btn-digest');
    if (!btn) return;
    btn.addEventListener('click', async () => {
      try {
        const res = await api('/api/review/digest?n=5');
        const notes = (res && res.notes) || (Array.isArray(res) ? res : []);
        if (!notes.length) {
          state.queue = [];
          state.idx = 0;
          state.total = 0;
          showEmpty();
          return;
        }
        state.digestMode = true;
        state.queue = notes;
        state.idx = 0;
        state.total = notes.length;
        const flip = $el('btn-flip');
        if (flip) flip.hidden = false;
        if (window.__sbShowView) window.__sbShowView('review');
        renderCard();
      } catch (e) {
        // 忽略
      }
    });
  }

  function bindExit() {
    const btn = $el('btn-review-exit');
    if (!btn) return;
    btn.addEventListener('click', () => {
      if (window.__sbShowView) window.__sbShowView('editor');
    });
  }

  // v0.6：使用者切换时按新身份刷新徽标/横幅；若正停在复习视图则重载队列。
  window.__sbOnUserChange = function () {
    refreshBadge();
    const rv = $el('review-view');
    if (rv && !rv.hidden && typeof window.__sbStartReview === 'function') {
      window.__sbStartReview();
    }
  };

  function init() {
    ensureBanner();
    bindFlip();
    bindGrades();
    bindDigest();
    bindExit();
    refreshBadge();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();

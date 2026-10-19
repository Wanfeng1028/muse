(function () {
  'use strict';


  const state = { queue: [], idx: 0, total: 0, digestMode: false, digestUser: '', loadSeq: 0 };


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

    if (progress) {
      let text = (state.idx + 1) + ' / ' + state.queue.length;
      if (state.digestMode && state.digestUser) {
        text += ' · ' + state.digestUser + ' 的回顾';
      }
      progress.textContent = text;
    }


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
    const hardBtn = $el('btn-hard-toggle');
    if (hardBtn) {
      const isHard = !!(item && item.hard);
      hardBtn.setAttribute('aria-pressed', isHard ? 'true' : 'false');
      hardBtn.classList.toggle('is-hard', isHard);
      hardBtn.textContent = isHard ? '已标记为困难' : '标记为困难';
    }
  }

  function showDone() {
    const card = $el('review-card');
    const grading = $el('review-grading');
    const done = $el('review-done');
    if (card) card.hidden = true;
    if (grading) grading.hidden = true;
    if (done) done.hidden = false;
    const total = state.total || 0;
    const hardMarked = state.hardMarkedThisSession || 0;
    const setNum = (id, v) => {
      const el = $el(id);
      if (el) el.textContent = String(v);
    };
    setNum('done-num-reviewed', total);
    setNum('done-num-hard', hardMarked);
    const hintEl = $el('review-done-hint');
    api('/api/review/stats')
      .then((stats) => {
        const streakDays = (stats && stats.streakDays) || 0;
        const reviewed7d = (stats && stats.reviewed7d) || 0;
        setNum('done-num-streak', streakDays);
        setNum('done-num-week', reviewed7d);
        const textEl = $el('review-done-text');
        if (textEl) {
          textEl.textContent = '今天复习了 ' + total + ' 篇，连续坚持 ' + streakDays + ' 天';
        }
        // 提示语：只陈述事实，不加油打气
        if (hintEl) {
          if (hardMarked > 0) {
            hintEl.textContent = '其中 ' + hardMarked + ' 篇标了困难，它们会更早回来。';
          } else if (total > 0) {
            hintEl.textContent = '没有标困难的卡片。';
          } else {
            hintEl.textContent = '';
          }
        }
        refreshBadge();
      })
      .catch(() => {
        refreshBadge();
      });
    // 下一轮开始时清零本轮计数
    state.hardMarkedThisSession = 0;
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
    // 空队列时也填充完成面板的真实数字（本轮复习 0 篇，但连续天数/近 7 天是真实值）
    const setNum = (id, v) => {
      const el = $el(id);
      if (el) el.textContent = String(v);
    };
    setNum('done-num-reviewed', 0);
    setNum('done-num-hard', 0);
    api('/api/review/stats')
      .then((stats) => {
        setNum('done-num-streak', (stats && stats.streakDays) || 0);
        setNum('done-num-week', (stats && stats.reviewed7d) || 0);
      })
      .catch(() => {});
  }

  window.__sbStartReview = async function () {
    state.digestMode = false;
    const seq = ++state.loadSeq;
    const flip = $el('btn-flip');
    if (flip) flip.hidden = false;
    try {
      const res = await api('/api/review/queue?limit=50');
      if (seq !== state.loadSeq) return; // 过期请求的结果作废（v0.9 竞态修复）
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


  async function loadDigest() {
    const seq = ++state.loadSeq;
    try {
      const res = await api('/api/review/digest?n=5');
      if (seq !== state.loadSeq) return; // 过期请求的结果作废（v0.9 竞态修复）
      const notes = (res && res.notes) || (Array.isArray(res) ? res : []);
      if (!notes.length) {
        state.queue = [];
        state.idx = 0;
        state.total = 0;
        state.digestUser = '';
        showEmpty();
        return;
      }
      state.digestMode = true;
      state.digestUser = (typeof window.__sbCurrentUser === 'function') ? window.__sbCurrentUser() : 'local';
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
  }

  function bindDigest() {
    const btn = $el('btn-digest');
    if (!btn) return;
    btn.addEventListener('click', loadDigest);
  }


  function bindExit() {
    const btn = $el('btn-review-exit');
    if (!btn) return;
    btn.addEventListener('click', () => {
      if (window.__sbShowView) window.__sbShowView('editor');
    });
  }


  // v0.6：使用者切换时按新身份刷新徽标/横幅；若正停在复习视图则重载队列。
  // v0.9：digest 模式下按新使用者重载今日回顾。
  window.__sbOnUserChange = function () {
    refreshBadge();
    const rv = $el('review-view');
    if (rv && !rv.hidden) {
      if (state.digestMode && typeof loadDigest === 'function') {
        loadDigest();
      } else if (typeof window.__sbStartReview === 'function') {
        window.__sbStartReview();
      }
    }
  };


  function bindHardToggle() {
    const btn = $el('btn-hard-toggle');
    if (!btn) return;
    btn.addEventListener('click', async () => {
      const item = state.queue[state.idx];
      if (!item) return;
      const target = !(btn.getAttribute('aria-pressed') === 'true');
      btn.disabled = true;
      try {
        await api('/api/review/' + encodeURIComponent(item.id) + '/hard', {
          method: 'POST',
          body: { hard: target },
        });
        item.hard = target;
      } catch (e) {
        // 失败不改本地态，按钮保持原样
      }
      btn.disabled = false;
      if (item.hard === target) {
        btn.setAttribute('aria-pressed', String(target));
        btn.classList.toggle('is-hard', target);
        btn.textContent = target ? '已标记为困难' : '标记为困难';
        if (target) state.hardMarkedThisSession = (state.hardMarkedThisSession || 0) + 1;
        else state.hardMarkedThisSession = Math.max(0, (state.hardMarkedThisSession || 0) - 1);
      }
    });
  }

  function init() {
    ensureBanner();
    bindFlip();
    bindGrades();
    bindHardToggle();
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

'use strict';

// Points rules. Single source of truth for the rules themselves; the same
// values are also published as the configs seed (see config-seed.js) so
// the client reads them from the config function instead of hardcoding.
// Earn rules use a daily key (Asia/Shanghai) for daily caps.
const EARN_RULES = {
  signin: { delta: 10, dailyLimit: 1, label: '每日签到' },
  video: { delta: 20, dailyLimit: 5, label: '激励视频' },
  invite: { delta: 100, dailyLimit: 0, label: '邀请好友' },
  profile: { delta: 30, dailyLimit: 0, label: '完善资料', once: true },
  share: { delta: 5, dailyLimit: 1, label: '分享海报' },
  inviteeBonus: { delta: 50, dailyLimit: 0, label: '被邀奖励' }
};

const SPEND_RULES = {
  advancedInterpret: { delta: -50, label: '高级解读' },
  aiInterpret: { delta: -30, label: 'AI 解读' },
  pro7d: { delta: -300, label: '7 天 Pro' },
  pro30d: { delta: -1500, label: '30 天 Pro' }
};

// Date key in Asia/Shanghai, e.g. '2026-11-01'. Pure function of a Date.
function dayKey(date) {
  const d = date || new Date();
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit'
  }).formatToParts(d);
  const get = function (type) {
    const found = parts.find(function (p) { return p.type === type; });
    return found ? found.value : '';
  };
  return get('year') + '-' + get('month') + '-' + get('day');
}

// Count how many ledger entries for (rule, day) already exist today.
// `entries` is a list of ledger docs with { rule, dayKey }.
function countToday(entries, rule, today) {
  return (entries || []).filter(function (e) {
    return e.rule === rule && e.dayKey === today;
  }).length;
}

// Pure earn-eligibility check. Returns { allowed: true } or
// { allowed: false, reason: '...' }. The points function passes the
// relevant ledger slice; this module never touches the database.
function canEarn(rule, options) {
  options = options || {};
  const def = EARN_RULES[rule];
  if (!def) {
    return { allowed: false, reason: 'UNKNOWN_RULE' };
  }
  if (def.once && options.alreadyClaimed) {
    return { allowed: false, reason: 'ALREADY_CLAIMED' };
  }
  if (def.dailyLimit > 0) {
    const used = countToday(options.todayEntries || [], rule, options.today || dayKey());
    if (used >= def.dailyLimit) {
      return { allowed: false, reason: 'DAILY_LIMIT_REACHED' };
    }
  }
  return { allowed: true };
}

function canSpend(rule, balance) {
  const def = SPEND_RULES[rule];
  if (!def) {
    return { allowed: false, reason: 'UNKNOWN_RULE' };
  }
  if ((balance || 0) + def.delta < 0) {
    return { allowed: false, reason: 'INSUFFICIENT_POINTS' };
  }
  return { allowed: true };
}

module.exports = {
  EARN_RULES: EARN_RULES,
  SPEND_RULES: SPEND_RULES,
  dayKey: dayKey,
  countToday: countToday,
  canEarn: canEarn,
  canSpend: canSpend
};

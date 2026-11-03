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
  advancedInterpret: { delta: -100, label: '高级解读' },
  aiInterpret: { delta: -30, label: 'AI 解读' },
  pro7d: { delta: -300, label: '7 天 Pro' },
  pro30d: { delta: -1500, label: '30 天 Pro' },
  // 2026-11-01 chat-agent round (pure-points model, per the 2026-11-01
  // 19:30 correction; the earlier flat "AI chat 10/round" idea is void:
  // chat text is free up to a daily token quota, then 1 point per 1000
  // tokens, so chat has NO flat spend rule here).
  // Same minor gate and balance check as the other spend rules
  // (see points/index.js). One yuan = 100 points.
  dimInterpret: { delta: -20, label: '维度解读' },
  aiPersona: { delta: -100, label: 'AI 定制形象' },
  compare: { delta: -60, label: '合盘对照' },
  chatImage: { delta: -40, label: '对话内生图' },
  posterBg: { delta: -40, label: '海报背景 AI 生成' },
  hdExport: { delta: -40, label: '高清命盘图导出' },
  annualFortune: { delta: -100, label: '年度运势' }
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

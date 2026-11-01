'use strict';

// chat-agent: lightweight pure chat for 星命盘 (2026-11-01 19:30
// correction: NO multi-step tool loop). Each round packs context and
// sends it to the backend model in one call:
//   system prompt (cloud env only) + chart key-data summary (built by
//   the client from its local engine; the function treats it as
//   user-supplied context and truncates it defensively) + session
//   history (last N rounds) + the user's question
// -> model returns text (chat) or an image (action 'image').
//
// The system prompt lives ONLY in the cloud function environment
// config CHAT_SYSTEM_PROMPT. It is never written to a file, never
// returned, never logged. Without it the function runs a grounded
// template fallback (summary restatement, no model call, no charge)
// and says so explicitly; it never fabricates an answer.
//
// Billing (pure-points model, 19:40/19:41/19:48/19:49 corrections):
// - Chat text: 2,000,000 tokens free per user per natural day (chat
//   text only). Overage: 10 points per 1,000,000 tokens, settled on
//   actual usage, rounded up to whole points. 1 point = 100,000 tokens.
// - Budget cap: the model call carries a maxTokens cap computed from
//   quota remaining + balance, so a round can never cost more than the
//   user can pay. If the affordable budget cannot cover the input +
//   a 200-token minimum answer, the round is refused BEFORE generation
//   (no charge). Non-streaming generation cannot stop mid-stream, so
//   the cap + pre-check is the honest implementation of the
//   "interrupt, keep the generated part" rule: a capped answer that
//   ends without terminal punctuation is marked truncated and the
//   note says the generated part is kept.
// - Never overdraft: the post-hoc charge is capped at the balance and
//   any shortfall is logged (estimates are conservative, so a shortfall
//   should not happen in practice). Failed generations are not charged.
// - Minors: free quota only, never charged. When the quota is exhausted
//   a minor gets MINOR_QUOTA_EXHAUSTED (no paid path), not a charge.
// - In-chat image: fixed 40 points (chatImage), reserved before
//   generation and refunded on failure. Minors are refused
//   (MINOR_PAID_BLOCKED) because images have no free quota.
// - Audit: every round (including refusals) writes a chatLogs doc with
//   question (truncated), categories, tokens, charge and provider.
//   The system prompt is never written to any log.

const cloud = require('wx-server-sdk');
const https = require('https');
const { ok, fail, requireOpenid } = require('./shared/errors');
const { getUser, getConfigDoc, appendLedger, logQuota } = require('./shared/db-helpers');
const { SPEND_RULES, dayKey } = require('./shared/points');
const { SEED_CONFIGS, DISCLAIMER } = require('./shared/config-seed');
const { detect, scanOutput, complianceHits } = require('./shared/chat-safety');
const { shouldDegrade } = require('./shared/quota');
const adapter = require('./shared/ai-adapter');

cloud.init({ env: cloud.DYNAMIC_CURRENT_ENV });
const db = cloud.database();

const SUMMARY_MAX_CHARS = 2000;
const QUESTION_MAX_CHARS = 1000;
const HISTORY_TEXT_MAX_CHARS = 500;
const MIN_OUTPUT_TOKENS = 200;
const EARN_GUIDE = '可通过每日签到（+10）、激励视频（+20/次，每日上限 5 次）、分享（+5/日）、邀请好友（+100/人，需填邀请码）或充值（1 元 = 50 积分）获得积分。';

// Best-effort off-topic guard. A question is refused only when it
// matches a task-request marker AND contains no chart keyword at all;
// chart-framed questions (even finance-adjacent ones) pass to the
// model, which the system prompt instructs to refuse advice outside
// entertainment interpretation. The guard is logged, not silent.
const CHART_KEYWORDS = ['宫', '星', '命盘', '紫微', '四化', '大运', '流年', '流月', '格局', '运势', '命宫', '财帛', '官禄', '夫妻', '疾厄', '身宫', '主星', '排盘', '命主', '身主'];
const OFFTOPIC_MARKERS = [
  '写代码', '编程', '写程序', '翻译', '数学题', '解题', '作业', '论文', '作文',
  '炒股', '股票', '彩票', '足球', '天气', '订票', '酒店', '菜谱', '做菜',
  '新闻', '时政', '政治', '考试答案', '歌词',
  'write code', 'translate', 'homework', 'stock', 'weather', 'news'
];

function isOffTopic(question) {
  const hasChart = CHART_KEYWORDS.some(function (k) { return question.indexOf(k) >= 0; });
  if (hasChart) return false;
  return OFFTOPIC_MARKERS.some(function (k) { return question.toLowerCase().indexOf(k.toLowerCase()) >= 0; });
}

function sanitizeHistory(raw, rounds) {
  if (!Array.isArray(raw)) return [];
  const cleaned = [];
  raw.forEach(function (m) {
    if (!m || (m.role !== 'user' && m.role !== 'assistant') || typeof m.text !== 'string') return;
    cleaned.push({ role: m.role, text: m.text.slice(0, HISTORY_TEXT_MAX_CHARS) });
  });
  return cleaned.slice(-rounds * 2);
}

function templateFallback(summary) {
  return '结合本盘关键数据：\n' + summary
    + '\n（云端对话系统提示词未配置，当前为模板回退：仅复述本盘数据，未调用模型，不耗积分。）'
    + DISCLAIMER;
}

async function audit(entry) {
  try {
    await db.collection('chatLogs').add({ data: Object.assign({}, entry, { createdAt: new Date() }) });
  } catch (e) {
    // Audit failure must not break the round, but it must be visible.
    console.error('chat audit failed', e.message);
  }
}

async function todayChatUsage(openid, day) {
  const res = await db.collection('chatLogs')
    .where({ openid: openid, dayKey: day, kind: 'chat' }).limit(1000).get()
    .catch(function () { return { data: [] }; });
  let tokens = 0;
  let calls = 0;
  (res.data || []).forEach(function (d) {
    tokens += (d.totalTokens || 0);
    calls += 1;
  });
  return { tokens: tokens, calls: calls };
}

function downloadBuffer(url) {
  return new Promise(function (resolve, reject) {
    https.get(url, { timeout: 120000 }, function (res) {
      if (res.statusCode < 200 || res.statusCode >= 300) {
        reject(new Error('IMAGE_DOWNLOAD_HTTP_' + res.statusCode));
        return;
      }
      const parts = [];
      res.on('data', function (c) { parts.push(c); });
      res.on('end', function () { resolve(Buffer.concat(parts)); });
    }).on('error', reject);
  });
}

async function handleChat(event, openid, user) {
  const chatCfg = await getConfigDoc(db, 'chat', SEED_CONFIGS);
  const chat = (chatCfg.doc && chatCfg.doc._id === 'chat') ? chatCfg.doc : {};
  const dailyTokenQuota = chat.dailyTokenQuota || 2000000;
  const dailyCallCap = chat.dailyCallCap || 100;
  const historyRounds = chat.historyRounds || 10;
  const maxOutputTokens = chat.maxOutputTokens || 2000;
  const pointsPerMillion = chat.pointsPerMillionTokens || 10;
  const tokensPerPoint = 1000000 / pointsPerMillion;

  const questionRaw = String(event.question || '').trim();
  if (!questionRaw) {
    return fail('INVALID_PARAMS', '问题不能为空');
  }
  const questionTruncated = questionRaw.length > QUESTION_MAX_CHARS;
  const question = questionRaw.slice(0, QUESTION_MAX_CHARS);
  const summaryRaw = String(event.summary || '').trim();
  if (!summaryRaw) {
    return fail('INVALID_PARAMS', '需先排盘：对话需要本盘关键数据摘要');
  }
  const summary = summaryRaw.slice(0, SUMMARY_MAX_CHARS);
  const history = sanitizeHistory(event.history, historyRounds);

  // Safety: input detection first (refused rounds are audited, and the
  // input is never echoed back as an instruction).
  const detection = detect(question);
  if (detection.blocked) {
    await audit({
      openid: openid, dayKey: dayKey(), kind: 'chat', outcome: 'blocked',
      question: question.slice(0, 500), categories: detection.categories,
      totalTokens: 0, chargedPoints: 0
    });
    return fail('INJECTION_BLOCKED', '这个问题包含指令劫持内容，已拒绝并记录。请换一个与本盘有关的问题。');
  }
  if (isOffTopic(question)) {
    await audit({
      openid: openid, dayKey: dayKey(), kind: 'chat', outcome: 'off-topic',
      question: question.slice(0, 500), totalTokens: 0, chargedPoints: 0
    });
    return fail('OFF_TOPIC', '这个问题与本盘无关，我只能结合你的命盘聊天。换一个与命盘、运势有关的问题吧。');
  }

  const minor = !!user.minor;
  const day = dayKey();
  const usage = await todayChatUsage(openid, day);
  if (usage.calls >= dailyCallCap) {
    return fail('RATE_LIMITED', '今日对话次数已达上限（' + dailyCallCap + ' 次），请明日再来。');
  }
  const quotaRemaining = Math.max(0, dailyTokenQuota - usage.tokens);
  const balance = user.pointsBalance || 0;
  // Conservative input estimate: 1 char = 1 token (overestimates
  // Chinese-heavy text, which keeps the budget cap on the safe side).
  const historyChars = history.reduce(function (n, m) { return n + m.text.length; }, 0);
  const inputEstimate = summary.length + historyChars + question.length;
  const affordable = quotaRemaining + (minor ? 0 : balance * tokensPerPoint);
  if (affordable - inputEstimate < MIN_OUTPUT_TOKENS) {
    if (minor) {
      return fail('MINOR_QUOTA_EXHAUSTED', '今日免费对话额度已用完，未成年人不可付费购买额度，明日重置后再来。');
    }
    const need = Math.ceil(Math.max(0, inputEstimate + MIN_OUTPUT_TOKENS - quotaRemaining) / tokensPerPoint);
    return fail('INSUFFICIENT_POINTS', '积分不足：本次对话预估需 ' + need + ' 积分（超出免费额度部分按每百万 tokens ' + pointsPerMillion + ' 积分结算），当前余额 ' + balance + '。' + EARN_GUIDE);
  }
  const maxOutput = Math.min(maxOutputTokens, Math.floor(affordable - inputEstimate));
  const capped = maxOutput < maxOutputTokens;

  const systemPrompt = process.env.CHAT_SYSTEM_PROMPT || '';
  if (!systemPrompt) {
    // Honest degraded path: no model call, no charge, no fabrication.
    const text = templateFallback(summary);
    await audit({
      openid: openid, dayKey: dayKey(), kind: 'chat', outcome: 'template-fallback',
      question: question.slice(0, 500), summary: summary.slice(0, 500),
      totalTokens: 0, chargedPoints: 0, degraded: true
    });
    return ok({
      text: text, chargedPoints: 0, tokensUsed: 0, quotaCoveredTokens: 0,
      degraded: true, truncated: false, questionTruncated: questionTruncated,
      disclaimer: DISCLAIMER
    });
  }

  const aiCfg = await getConfigDoc(db, 'ai', SEED_CONFIGS);
  const quotaCfg = await getConfigDoc(db, 'quota', SEED_CONFIGS);
  const budget = (quotaCfg.doc && quotaCfg.doc.dailyTokenBudget) || 0;
  const threshold = (quotaCfg.doc && quotaCfg.doc.thresholdPercent) || 85;
  const todayQuotaRes = await db.collection('quotaLogs')
    .where({ provider: 'cloudbase', dayKey: day }).get()
    .catch(function () { return { data: [] }; });
  let usedProviderTokens = 0;
  (todayQuotaRes.data || []).forEach(function (d) { usedProviderTokens += (d.totalTokens || 0); });
  const forceFallback = shouldDegrade(usedProviderTokens, budget, threshold);

  const messages = [{ role: 'system', content: systemPrompt }];
  history.forEach(function (m) { messages.push(m); });
  messages.push({
    role: 'user',
    content: '本盘关键数据摘要：\n' + summary + '\n用户问题：' + question
  });

  let result;
  try {
    result = await adapter.generateTextWithFallback({
      messages: messages,
      maxTokens: maxOutput,
      cloudbaseModel: (aiCfg.doc && aiCfg.doc.cloudbaseChatModel) || 'deepseek-v4-flash',
      botsrouterApiKey: process.env.BOTSROUTER_API_KEY || '',
      botsrouterBaseUrl: process.env.BOTSROUTER_BASE_URL || '',
      botsrouterModel: (aiCfg.doc && aiCfg.doc.botsrouterChatModel) || '',
      forceFallback: forceFallback
    });
  } catch (e) {
    // Failed generation is never charged.
    await audit({
      openid: openid, dayKey: dayKey(), kind: 'chat', outcome: 'failed',
      question: question.slice(0, 500), totalTokens: 0, chargedPoints: 0,
      error: e.code || e.message
    });
    return fail(e.code || 'AI_UNAVAILABLE', '对话服务暂不可用（主备均失败），请稍后重试，未扣费。原因：' + (e.message || ''));
  }

  let text = result.text || '';
  const usageInfo = result.usage || {};
  const promptTokens = usageInfo.prompt_tokens || inputEstimate;
  const completionTokens = usageInfo.completion_tokens || text.length;
  const totalTokens = usageInfo.total_tokens || (promptTokens + completionTokens);
  const quotaCovered = Math.min(totalTokens, quotaRemaining);
  const overage = Math.max(0, totalTokens - quotaRemaining);

  // Output self-check BEFORE any charge: a flagged output is discarded
  // for a template fallback and charged 0 (failed answers are not
  // charged). Tokens are still recorded because upstream spent them.
  const outputScan = scanOutput(text);
  const compliance = complianceHits(text);
  let flagged = outputScan.flagged || compliance.length > 0;
  if (flagged) {
    text = templateFallback(summary);
    await audit({
      openid: openid, dayKey: dayKey(), kind: 'chat', outcome: 'output-flagged',
      question: question.slice(0, 500), totalTokens: totalTokens,
      chargedPoints: 0, provider: result.provider, degraded: true,
      flagReasons: (outputScan.reasons || []).concat(compliance)
    });
    await logQuota(db, {
      openid: openid, kind: 'chat', provider: result.provider,
      model: result.provider === 'cloudbase'
        ? ((aiCfg.doc && aiCfg.doc.cloudbaseChatModel) || 'deepseek-v4-flash')
        : ((aiCfg.doc && aiCfg.doc.botsrouterChatModel) || ''),
      promptTokens: promptTokens, completionTokens: completionTokens, totalTokens: totalTokens
    });
    return ok({
      text: text, chargedPoints: 0, tokensUsed: totalTokens,
      quotaCoveredTokens: quotaCovered, degraded: true, truncated: false,
      questionTruncated: questionTruncated, disclaimer: DISCLAIMER
    });
  }

  // Settle: overage at 10 points per million tokens, rounded up.
  // Never overdraft: the charge is capped at the balance and any
  // shortfall is logged (the conservative estimates make it unlikely).
  let computedCharge = 0;
  if (!minor && overage > 0) {
    computedCharge = Math.ceil((overage * pointsPerMillion) / 1000000);
  }
  let charged = computedCharge;
  let shortfall = 0;
  if (charged > balance) {
    shortfall = charged - balance;
    charged = balance;
  }
  if (charged > 0) {
    await appendLedger(db, { openid: openid, rule: 'chatOverage', delta: -charged, totalTokens: totalTokens, overageTokens: overage });
  }

  // Truncation note: a budget-capped answer that ends without terminal
  // punctuation is treated as cut off; the generated part is kept.
  let truncated = false;
  const trimmed = text.trim();
  if (capped && trimmed && !/[。！？.!?]$/.test(trimmed)) {
    truncated = true;
    text = text + '\n（本回答因可用额度触顶而截断，已生成部分已保留；赚积分后可继续追问。）';
  }
  await audit({
    openid: openid, dayKey: dayKey(), kind: 'chat', outcome: 'ok',
    question: question.slice(0, 500), summary: summary.slice(0, 500),
    totalTokens: totalTokens, quotaCoveredTokens: quotaCovered,
    chargedPoints: charged, shortfallPoints: shortfall,
    provider: result.provider, degraded: !!result.degraded, truncated: truncated
  });
  await logQuota(db, {
    openid: openid, kind: 'chat', provider: result.provider,
    model: result.provider === 'cloudbase'
      ? ((aiCfg.doc && aiCfg.doc.cloudbaseChatModel) || 'deepseek-v4-flash')
      : ((aiCfg.doc && aiCfg.doc.botsrouterChatModel) || ''),
    promptTokens: promptTokens, completionTokens: completionTokens, totalTokens: totalTokens
  });
  return ok({
    text: text, chargedPoints: charged, tokensUsed: totalTokens,
    quotaCoveredTokens: quotaCovered, degraded: !!result.degraded,
    truncated: truncated, questionTruncated: questionTruncated,
    disclaimer: DISCLAIMER
  });
}

async function handleImage(event, openid, user) {
  const prompt = String(event.prompt || '').trim();
  if (!prompt) {
    return fail('INVALID_PARAMS', '生图需要一句话描述');
  }
  // In-chat images are always paid (no free quota for images).
  if (user.minor) {
    return fail('MINOR_PAID_BLOCKED', '未成年人不可使用付费生图，基础形象与知识科普仍可免费使用');
  }
  const cost = -(SPEND_RULES.chatImage.delta || -40);
  const balance = user.pointsBalance || 0;
  if (balance < cost) {
    return fail('INSUFFICIENT_POINTS', '积分不足：对话内生图需 ' + cost + ' 积分，当前余额 ' + balance + '。' + EARN_GUIDE);
  }
  // Reserve first, refund on failure: failed generations are not charged.
  await appendLedger(db, { openid: openid, rule: 'chatImage', delta: -cost, prompt: prompt.slice(0, 200) });
  const aiCfg = await getConfigDoc(db, 'ai', SEED_CONFIGS);
  const quotaCfg = await getConfigDoc(db, 'quota', SEED_CONFIGS);
  const budget = (quotaCfg.doc && quotaCfg.doc.dailyTokenBudget) || 0;
  const threshold = (quotaCfg.doc && quotaCfg.doc.thresholdPercent) || 85;
  const todayQuotaRes = await db.collection('quotaLogs')
    .where({ provider: 'cloudbase', dayKey: dayKey() }).get()
    .catch(function () { return { data: [] }; });
  let usedProviderTokens = 0;
  (todayQuotaRes.data || []).forEach(function (d) { usedProviderTokens += (d.totalTokens || 0); });
  const forceFallback = shouldDegrade(usedProviderTokens, budget, threshold);
  let result;
  try {
    result = await adapter.generateImageWithFallback({
      prompt: prompt,
      cloudbaseModel: (aiCfg.doc && aiCfg.doc.cloudbaseImageModel) || 'HY-Image-3.0-Plus-4090-Tob-v1.0',
      size: event.size || '1024x1024',
      botsrouterApiKey: process.env.BOTSROUTER_API_KEY || '',
      botsrouterBaseUrl: process.env.BOTSROUTER_BASE_URL || '',
      botsrouterModel: (aiCfg.doc && aiCfg.doc.botsrouterImageModel) || '',
      forceFallback: forceFallback
    });
    const buffer = await downloadBuffer(result.url);
    const upload = await cloud.uploadFile({
      cloudPath: 'ai-images/chat-' + openid + '-' + Date.now() + '.jpg',
      fileContent: buffer
    });
    await audit({
      openid: openid, dayKey: dayKey(), kind: 'image', outcome: 'ok',
      prompt: prompt.slice(0, 200), chargedPoints: cost, provider: result.provider
    });
    return ok({ fileID: upload.fileID, chargedPoints: cost, provider: result.provider });
  } catch (e) {
    await appendLedger(db, { openid: openid, rule: 'refund', delta: cost, origRule: 'chatImage', reason: 'CHAT_IMAGE_FAILED' });
    await audit({
      openid: openid, dayKey: dayKey(), kind: 'image', outcome: 'failed',
      prompt: prompt.slice(0, 200), chargedPoints: 0, refundedPoints: cost,
      error: e.code || e.message
    });
    return fail(e.code || 'AI_IMAGE_UNAVAILABLE', '生图服务暂不可用（主备均失败），已退还 ' + cost + ' 积分。原因：' + (e.message || ''));
  }
}

exports.main = async (event, context) => {
  try {
    const wxContext = cloud.getWXContext();
    const openid = requireOpenid(wxContext);
    if (!openid) {
      return fail('NOT_LOGGED_IN', '无法获取微信登录态，请先调用 login');
    }
    const user = await getUser(db, openid);
    if (!user) {
      return fail('USER_NOT_FOUND', '用户不存在，请先调用 login');
    }
    const action = event.action;
    if (action === 'chat') {
      return await handleChat(event, openid, user);
    }
    if (action === 'image') {
      return await handleImage(event, openid, user);
    }
    return fail('UNKNOWN_ACTION', '未知 action: ' + String(action));
  } catch (e) {
    console.error('chat-agent failed', e);
    return fail('CHAT_AGENT_FAILED', e.message || '对话服务异常');
  }
};

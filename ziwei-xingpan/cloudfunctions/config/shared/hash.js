'use strict';

const crypto = require('crypto');

function sha256Hex(text) {
  return crypto.createHash('sha256').update(text, 'utf8').digest('hex');
}

// Recursively sort object keys so the same chart parameters always hash
// the same way regardless of key insertion order. Arrays keep their order.
function normalize(value) {
  if (value === null || value === undefined) {
    return null;
  }
  if (Array.isArray(value)) {
    return value.map(function (item) { return normalize(item); });
  }
  if (typeof value === 'object') {
    const out = {};
    Object.keys(value).sort().forEach(function (key) {
      out[key] = normalize(value[key]);
    });
    return out;
  }
  return value;
}

function normalizedJson(value) {
  return JSON.stringify(normalize(value));
}

// Hash of the normalized birth/chart parameters. The server computes this
// from the parameters the client sends; the chart body itself is stored
// as uploaded by the client (the backend stores charts, it does not cast them).
function chartHash(chartParams) {
  return sha256Hex(normalizedJson(chartParams || {}));
}

// AI interpretation cache key: normalized chart parameters + interpretation type.
function aiCacheKey(chartParams, interpretType) {
  return sha256Hex(normalizedJson(chartParams || {}) + '|' + String(interpretType || 'full'));
}

// Image cache key: prompt hash, or date + chart hash for daily-fortune images.
function imageCacheKey(options) {
  options = options || {};
  if (options.chartParams && options.dateKey) {
    return sha256Hex('daily|' + String(options.dateKey) + '|' + normalizedJson(options.chartParams));
  }
  return sha256Hex('prompt|' + String(options.prompt || ''));
}

// Deterministic invite code derived from openid. Collision handling lives
// in the invite function (it checks the code owner before assigning).
function inviteCodeFromOpenid(openid, attempt) {
  const suffix = attempt ? String(attempt) : '';
  const hash = sha256Hex(String(openid) + suffix);
  const num = parseInt(hash.slice(0, 8), 16).toString(36).toUpperCase();
  return 'ZW' + num.padStart(8, '0').slice(0, 8);
}

module.exports = {
  sha256Hex: sha256Hex,
  normalize: normalize,
  normalizedJson: normalizedJson,
  chartHash: chartHash,
  aiCacheKey: aiCacheKey,
  imageCacheKey: imageCacheKey,
  inviteCodeFromOpenid: inviteCodeFromOpenid
};

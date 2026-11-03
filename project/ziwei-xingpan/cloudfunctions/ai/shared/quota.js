'use strict';

// Quota helpers. Usage is counted in quotaLogs (one doc per AI call).
// When used / budget >= thresholdPercent, the caller must degrade to the
// fallback provider and say so in the response; never fail silently.
const DEFAULT_THRESHOLD_PERCENT = 85;

function usageRatio(used, budget) {
  if (!budget || budget <= 0) {
    return 0;
  }
  return used / budget;
}

function shouldDegrade(used, budget, thresholdPercent) {
  const threshold = (thresholdPercent === undefined || thresholdPercent === null)
    ? DEFAULT_THRESHOLD_PERCENT
    : thresholdPercent;
  if (!budget || budget <= 0) {
    return false;
  }
  return usageRatio(used, budget) * 100 >= threshold;
}

module.exports = {
  DEFAULT_THRESHOLD_PERCENT: DEFAULT_THRESHOLD_PERCENT,
  usageRatio: usageRatio,
  shouldDegrade: shouldDegrade
};

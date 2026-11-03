'use strict';

// Invite tiers. Reward: { tier, days } means that many days of that tier.
const TIERS = [
  { count: 3, tier: 'pro', days: 7 },
  { count: 10, tier: 'pro', days: 30 },
  { count: 30, tier: 'max', days: 30 }
];

// Tiers newly earned at `successCount` that are not in `alreadyGranted`
// (a list of tier counts already granted). Pure function.
function newlyEarnedTiers(successCount, alreadyGranted) {
  const granted = alreadyGranted || [];
  return TIERS.filter(function (t) {
    return successCount >= t.count && granted.indexOf(t.count) === -1;
  });
}

// Next tier target for display, or null when all tiers are earned.
function nextTier(successCount) {
  for (let i = 0; i < TIERS.length; i++) {
    if (successCount < TIERS[i].count) {
      return TIERS[i];
    }
  }
  return null;
}

module.exports = { TIERS: TIERS, newlyEarnedTiers: newlyEarnedTiers, nextTier: nextTier };

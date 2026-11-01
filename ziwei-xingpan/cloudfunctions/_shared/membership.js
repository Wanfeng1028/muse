'use strict';

// Membership helpers. A membership doc: { openid, tier, expiresAt, autoRenew }.
// expiresAt is a Date (or null for the free tier, which never expires).
// The effective tier is free once expiresAt has passed; cancelling
// auto-renew only flips autoRenew, the tier stays until expiresAt.
function effectiveTier(membership, now) {
  const current = now || new Date();
  if (!membership || !membership.tier || membership.tier === 'free') {
    return 'free';
  }
  if (membership.expiresAt && new Date(membership.expiresAt) <= current) {
    return 'free';
  }
  return membership.tier;
}

// Expiry after granting `days`: extend from the existing expiry when the
// membership is still active, otherwise from now.
function extendedExpiry(membership, days, now) {
  const current = now || new Date();
  let base = current;
  if (membership && membership.expiresAt) {
    const existing = new Date(membership.expiresAt);
    if (existing > current) {
      base = existing;
    }
  }
  return new Date(base.getTime() + days * 24 * 60 * 60 * 1000);
}

// Tier rank for the no-downgrade grant rule (free < plus < pro < max).
// 2026-11-01: Plus tier added (pure-points model).
// A reward, points redemption or purchase must never downgrade a user who
// already holds a higher effective tier: in that case the higher tier is
// kept and only its expiry is extended by `days`. Otherwise the granted
// tier applies with the extended expiry. Pure function.
const TIER_RANK = { free: 0, plus: 1, pro: 2, max: 3 };

function grantTier(membership, tier, days, now) {
  const current = now || new Date();
  const effective = effectiveTier(membership, current);
  const keep = (TIER_RANK[effective] || 0) > (TIER_RANK[tier] || 0);
  return {
    tier: keep ? effective : tier,
    expiresAt: extendedExpiry(membership, days, current),
    keptHigherTier: keep
  };
}

module.exports = { effectiveTier: effectiveTier, extendedExpiry: extendedExpiry, grantTier: grantTier, TIER_RANK: TIER_RANK };

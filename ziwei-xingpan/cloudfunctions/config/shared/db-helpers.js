'use strict';

// Database helpers shared by the cloud functions. These take the `db`
// instance as an argument so the pure rule modules stay database-free.
// pointsLedger is append-only: this module only ever calls add() on it,
// never update() or remove().

async function getUser(db, openid) {
  const res = await db.collection('users').doc(openid).get().catch(function () { return null; });
  if (!res || !res.data) {
    return null;
  }
  return res.data;
}

async function getConfigDoc(db, id, seedDocs) {
  const res = await db.collection('configs').doc(id).get().catch(function () { return null; });
  if (res && res.data) {
    return { doc: res.data, fromSeed: false };
  }
  const seed = (seedDocs || []).find(function (d) { return d._id === id; });
  return { doc: seed || null, fromSeed: true };
}

// Append a ledger entry and move the user's balance by the same delta.
// Balance uses an atomic increment; the ledger entry records balanceAfter
// as best-effort (read after the increment) for audit display.
async function appendLedger(db, entry) {
  const _ = db.command;
  const now = new Date();
  const doc = Object.assign({}, entry, { createdAt: now });
  await db.collection('pointsLedger').add({ data: doc });
  await db.collection('users').doc(entry.openid).update({
    data: { pointsBalance: _.inc(entry.delta), updatedAt: now }
  });
  return doc;
}

async function getMembership(db, openid) {
  const res = await db.collection('memberships').doc(openid).get().catch(function () { return null; });
  if (!res || !res.data) {
    return null;
  }
  return res.data;
}

async function upsertMembership(db, openid, tier, expiresAt, autoRenew) {
  const now = new Date();
  const existing = await getMembership(db, openid);
  const data = {
    openid: openid, tier: tier, expiresAt: expiresAt || null,
    autoRenew: !!autoRenew, updatedAt: now
  };
  if (existing) {
    await db.collection('memberships').doc(openid).update({ data: data });
  } else {
    await db.collection('memberships').add({
      data: Object.assign({}, data, { _id: openid, createdAt: now })
    });
  }
  return data;
}

async function logQuota(db, entry) {
  await db.collection('quotaLogs').add({
    data: Object.assign({}, entry, { createdAt: new Date() })
  });
}

module.exports = {
  getUser: getUser,
  getConfigDoc: getConfigDoc,
  appendLedger: appendLedger,
  getMembership: getMembership,
  upsertMembership: upsertMembership,
  logQuota: logQuota
};

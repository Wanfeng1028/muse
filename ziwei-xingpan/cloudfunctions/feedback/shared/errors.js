'use strict';

// Unified response envelope for all cloud functions.
// Success: { code: 0, data: ... , ...extra }
// Failure: { code: 'ERR_CODE', message: '...' , ...extra }
// No function ever returns a fake success when a dependency is unconfigured.

function ok(data, extra) {
  return Object.assign({ code: 0, data: data === undefined ? null : data }, extra || {});
}

function fail(code, message, extra) {
  return Object.assign({ code: code, message: message || code }, extra || {});
}

function requireOpenid(wxContext) {
  const openid = wxContext && wxContext.OPENID;
  if (!openid) {
    return null;
  }
  return openid;
}

module.exports = { ok: ok, fail: fail, requireOpenid: requireOpenid };

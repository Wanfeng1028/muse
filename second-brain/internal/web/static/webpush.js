(function () {
'use strict';

function supportOK() {
if (!('serviceWorker' in navigator) || !('PushManager' in window) || !('Notification' in window)) {
var tip = $('webpush-tip');
if (tip) tip.textContent = '这个浏览器不支持推送，换个新版 Chrome / Edge / Safari 试试';
var sub = $('btn-webpush-subscribe');
var unsub = $('btn-webpush-unsubscribe');
if (sub) sub.disabled = true;
if (unsub) unsub.disabled = true;
return false;
}
return true;
}

function urlBase64ToUint8Array(base64String) {
var padding = '='.repeat((4 - (base64String.length % 4)) % 4);
var base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
var rawData = atob(base64);
var outputArray = new Uint8Array(rawData.length);
for (var i = 0; i < rawData.length; ++i) {
outputArray[i] = rawData.charCodeAt(i);
}
return outputArray;
}

function keyToBase64Url(key) {
var bytes = new Uint8Array(key);
var binary = '';
for (var i = 0; i < bytes.length; i++) {
binary += String.fromCharCode(bytes[i]);
}
return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function friendlyError(err) {
var msg = err && err.message ? err.message : String(err);
if (msg.indexOf('Failed to fetch') >= 0) return '网络没连上';
return msg;
}

async function refreshState() {
if (!supportOK()) return;
var tip = $('webpush-tip');
var permEl = $('webpush-permission');
var statusEl = $('webpush-status');
var subBtn = $('btn-webpush-subscribe');
var unsubBtn = $('btn-webpush-unsubscribe');

var perm = Notification.permission;
if (permEl) {
if (perm === 'granted') permEl.textContent = '已允许';
else if (perm === 'denied') permEl.textContent = '已拒绝，去浏览器设置里打开';
else permEl.textContent = '还没问过你';
}

try {
var reg = await navigator.serviceWorker.getRegistration();
var sub = reg ? await reg.pushManager.getSubscription() : null;
if (sub) {
if (statusEl) statusEl.textContent = '已开启，这台设备会收到提醒';
if (subBtn) subBtn.hidden = true;
if (unsubBtn) unsubBtn.hidden = false;
} else {
if (statusEl) statusEl.textContent = '还没开';
if (subBtn) subBtn.hidden = false;
if (unsubBtn) unsubBtn.hidden = true;
}
} catch (e) {
if (tip) tip.textContent = '查订阅状态失败，刷新页面再试';
}
}

async function subscribe() {
if (!supportOK()) return;
var tip = $('webpush-tip');
try {
var perm = await Notification.requestPermission();
if (perm !== 'granted') {
if (tip) tip.textContent = '没打开通知权限就收不到提醒，去浏览器地址栏左边把通知打开再试';
return;
}

var publicKey;
try {
var res = await api('/api/push/vapid-public-key');
publicKey = res && res.public_key ? res.public_key : (res && res.publicKey ? res.publicKey : '');
if (!publicKey) throw new Error('no key');
} catch (e) {
if (tip) tip.textContent = '服务器还没配好推送（缺 VAPID 密钥），联系管理员配一下 SB_VAPID_* 环境变量';
return;
}

var reg = await navigator.serviceWorker.ready;
var sub = await reg.pushManager.subscribe({
userVisibleOnly: true,
applicationServerKey: urlBase64ToUint8Array(publicKey)
});

var endpoint = sub.endpoint;
var p256dh = keyToBase64Url(sub.getKey('p256dh'));
var auth = keyToBase64Url(sub.getKey('auth'));

await api('/api/push/subscriptions', {
method: 'POST',
headers: { 'Content-Type': 'application/json' },
body: JSON.stringify({ endpoint: endpoint, p256dh: p256dh, auth: auth })
});

if (tip) tip.textContent = '开好了，明天到点就会收到提醒';
await refreshState();
} catch (e) {
if (tip) tip.textContent = '订阅失败：' + friendlyError(e);
}
}

async function unsubscribe() {
if (!supportOK()) return;
var tip = $('webpush-tip');
try {
var reg = await navigator.serviceWorker.getRegistration();
var sub = reg ? await reg.pushManager.getSubscription() : null;
if (sub) {
await api('/api/push/subscriptions', {
method: 'DELETE',
headers: { 'Content-Type': 'application/json' },
body: JSON.stringify({ endpoint: sub.endpoint })
});
await sub.unsubscribe();
}
if (tip) tip.textContent = '已关闭，这个浏览器不会再收到提醒';
await refreshState();
} catch (e) {
if (tip) tip.textContent = '关闭失败，刷新再试';
}
}

function bind() {
var subBtn = $('btn-webpush-subscribe');
var unsubBtn = $('btn-webpush-unsubscribe');
if (subBtn) subBtn.addEventListener('click', subscribe);
if (unsubBtn) unsubBtn.addEventListener('click', unsubscribe);
}

window.__sbRefreshWebPush = refreshState;

bind();
if ($('btn-webpush-subscribe')) refreshState();
})();

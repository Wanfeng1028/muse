/**
 * 没有 ffmpeg 时，用浏览器抽帧"看"视频。
 *
 * 用 browser_eval 注入执行。原理跟 LingCut 应用自己的一样：
 *   <video crossOrigin="anonymous"> → seek → canvas.drawImage → toBlob
 * 然后上传七牛，**只回传 URL**，避免把 base64 灌进上下文。
 *
 * 说明:
 *  - oss.ytop.cc 支持 CORS，所以 drawImage 后 canvas 不会污染
 *  - 必须先跑过 scripts/engine.js（需要页面已登录，才能取 upload-token）
 *
 * 返回: [{ tag, t, url }]  —— 再用 fetch-assets.mjs 下载后审阅
 */
(() => {
  const JOBS = [
    // { tag: 'v01', url: 'https://oss.ytop.cc/lingcut/videos/xxx.mp4', times: [0.3, 2.8] },
  ];

  window.__extractFrames = async (jobs = JOBS) => {
    const out = [];
    const canvas = document.createElement('canvas');
    for (const { tag, url, times } of jobs) {
      const v = document.createElement('video');
      v.crossOrigin = 'anonymous';
      v.preload = 'auto';
      v.src = url;
      try {
        await new Promise((res, rej) => { v.onloadeddata = res; v.onerror = () => rej(new Error('video load failed')); });
      } catch (e) { out.push({ tag, error: e.message }); continue; }

      canvas.width = v.videoWidth;
      canvas.height = v.videoHeight;
      const ctx = canvas.getContext('2d');

      for (const t of times) {
        v.currentTime = t;
        await new Promise(res => { v.onseeked = res; });
        ctx.drawImage(v, 0, 0);
        const blob = await new Promise(res => canvas.toBlob(res, 'image/jpeg', 0.85));
        if (!blob) { out.push({ tag, t, error: 'canvas tainted' }); continue; }

        const key = `lingcut/images/${Date.now()}-${Math.random().toString(36).slice(2, 8)}.jpg`;
        const tok = await (await fetch('/api/system/qiniu/upload-token', {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'include',
          body: JSON.stringify({ key }),
        })).json();
        const form = new FormData();
        form.append('token', tok.token);
        form.append('key', key);
        form.append('file', new File([blob], key.split('/').pop(), { type: 'image/jpeg' }));
        const up = await fetch('https://up-z1.qiniup.com', { method: 'POST', body: form });
        out.push({ tag, t, up: up.status, url: `${tok.domain}/${key}` });
        await new Promise(r => setTimeout(r, 80));
      }
    }
    return out;
  };

  return 'installed __extractFrames (jobs=' + JOBS.length + ')';
})()

/**
 * LingCut 画布引擎驱动 —— 用 browser_eval 把本文件整体注入页面。
 *
 * 注入后页面出现 window.__lc，提供精确的画布操作能力。
 * 原理：应用没有把引擎挂到 window，但引擎实例在 React fiber 的 hook 里，
 *       遍历 fiber 树即可拿到（见 findEngine）。
 *
 * 用法：
 *   browser_eval( <本文件内容> )                  // 注入
 *   browser_eval("__lc.eng.nodes.length")          // 验证
 */
(() => {
  const PROJ = parseInt(location.pathname.match(/\/canvas\/(\d+)/)?.[1] ?? '0', 10);

  /** 遍历 React fiber 找画布引擎（nodeMap 是 Map 且 addNode 是函数） */
  const findEngine = () => {
    const el = [...document.querySelectorAll('*')].find(e =>
      Object.getOwnPropertyNames(e).some(n => n.startsWith('__reactContainer$')));
    if (!el) return null;
    const key = Object.getOwnPropertyNames(el).find(n => n.startsWith('__reactContainer$'));
    const root = el[key];
    const isEngine = o => o && typeof o === 'object' && o.nodeMap instanceof Map && typeof o.addNode === 'function';
    let found = null;
    const seen = new Set();
    const dfs = (node, d) => {
      if (!node || found || seen.has(node) || d > 400) return;
      seen.add(node);
      let hook = node.memoizedState, i = 0;
      while (hook && i++ < 120) {
        const v = hook.memoizedState;
        if (isEngine(v)) { found = v; return; }
        if (v && v.current && isEngine(v.current)) { found = v.current; return; }
        hook = hook.next;
      }
      dfs(node.child, d + 1);
      dfs(node.sibling, d);
    };
    dfs(root.child, 0);
    return found;
  };

  const sleep = ms => new Promise(r => setTimeout(r, ms));

  window.__lc = {
    PROJ,

    get eng() { return this._eng && this._eng.nodeMap ? this._eng : (this._eng = findEngine()); },
    get canvas() { return document.querySelector('canvas.leafer-canvas-view'); },

    // ---------- 数据 ----------
    async data() {
      const r = await fetch('/api/projects/' + this.PROJ, { credentials: 'include' });
      return JSON.parse((await r.json()).project.canvas_data);
    },
    async save() {
      const r = await fetch('/api/projects/' + this.PROJ, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' }, credentials: 'include',
        body: JSON.stringify({ canvas_data: JSON.stringify(this.eng.toJSON()) }),
      });
      return r.status;
    },

    // ---------- 编辑 ----------
    addNode(type, x, y) { return this.eng.addNode(type, x, y); },
    setData(id, data) { this.eng.updateNodeData(id, data); return id; },
    move(id, x, y) { this.eng.updateNodePosition(id, x, y); return id; },
    connect(srcId, tgtId) { return this.eng.addConnection(srcId, tgtId); },
    remove(id) { this.eng.removeNode(id); },
    node(id) { return this.eng.nodes.find(n => n.id === id); },

    // ---------- 视图 ----------
    transform() { return this.eng.getTransform(); },
    setTransform(x, y, k) { this.eng.setTransform(x, y, k); },
    fit() { this.eng.fitToView(120); },

    /** 无头模式下画布不自动重绘，改动后必须调用 */
    repaint() {
      const cv = this.canvas, r = cv.getBoundingClientRect();
      for (const d of [-120, 120]) {
        cv.dispatchEvent(new WheelEvent('wheel', { deltaY: d, clientX: r.x + 400, clientY: r.y + 400, bubbles: true, cancelable: true }));
      }
    },

    /** 把节点摆到指定屏幕位置（k=1，按钮尺寸正常） */
    focusNode(id, sx = 120, sy = 60) {
      const n = this.node(id);
      if (!n) return null;
      this.setTransform(sx - n.group.x, sy - n.group.y, 1);
      try { this.eng.forceUpdate?.(); } catch {}
      this.repaint();
      return n;
    },

    /** 关掉可能挡住点击的浮层（快捷操作菜单背景） */
    async closePopup() {
      const bd = [...document.querySelectorAll('div')].find(d =>
        /z-\[19[0-9]\]/.test(d.className || '') && (d.className || '').includes('fixed inset-0'));
      if (!bd) return;
      const r = bd.getBoundingClientRect();
      bd.dispatchEvent(new MouseEvent('click', {
        clientX: r.x + 30, clientY: r.y + 700, bubbles: true, cancelable: true, button: 0, buttons: 0, which: 1, view: window,
      }));
      await sleep(500);
    },

    /** 触发生成：聚焦 → 选中 → 点 ↑ */
    async gen(id) {
      await this.closePopup();
      this.focusNode(id, 120, 60);
      this.eng.selectNode(id);
      await sleep(1300);
      const btn = [...document.querySelectorAll('button')].find(b => b.textContent.trim() === '↑');
      if (!btn) return { ok: false, reason: 'no ↑ button' };
      const r = btn.getBoundingClientRect();
      const cx = r.x + r.width / 2, cy = r.y + r.height / 2;
      const mk = buttons => ({ clientX: cx, clientY: cy, bubbles: true, cancelable: true, button: 0, buttons, which: buttons ? 1 : 0, view: window });
      btn.dispatchEvent(new MouseEvent('mousedown', mk(1)));
      await sleep(60);
      btn.dispatchEvent(new MouseEvent('mouseup', mk(0)));
      btn.dispatchEvent(new MouseEvent('click', mk(0)));
      await sleep(1200);
      return { ok: true, generating: !!this.node(id)?.data?.generating };
    },

    /** 轮询多个节点直到生成结束 */
    async wait(ids, { timeoutMs = 600000, intervalMs = 8000 } = {}) {
      const t0 = Date.now();
      while (Date.now() - t0 < timeoutMs) {
        const st = ids.map(id => { const n = this.node(id); return { id, g: !!n?.data?.generating, src: n?.data?.src || null, err: n?.data?.genError || null }; });
        if (st.every(x => !x.g)) return st;
        await sleep(intervalMs);
      }
      return ids.map(id => { const n = this.node(id); return { id, g: !!n?.data?.generating, src: n?.data?.src || null, err: 'timeout' }; });
    },
  };

  return { injected: true, PROJ, engineFound: !!window.__lc.eng, nodes: window.__lc.eng?.nodes.length ?? null };
})()

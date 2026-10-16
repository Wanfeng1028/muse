/**
 * offline-queue.js — second-brain「第二大脑」离线写操作队列
 *
 * 存储：IndexedDB `sb-offline` v1，对象仓库 `queue`，keyPath `id`（自增）。
 * 记录：{ id, method, url, headers, body, enqueuedAt }（body 为字符串或 null）
 *
 * ⚠️ 幂等诚实声明（务必阅读）：
 *   后端 POST /api/notes 没有客户端幂等键。因此「离线新建笔记」在联网回放时
 *   会在服务端生成一个【全新的 id】，与离线期间本地临时使用的任何 id 无关，
 *   也无法保证不产生重复笔记。若同一份离线数据被回放两次，就会重复创建。
 *   相比之下，PUT /api/notes/{id}、DELETE /api/notes/{id}、POST /api/review/{id}
 *   都是按 id 定位资源的操作，重复回放是安全（幂等/半幂等）的。
 *   若需要严格的离线建笔记去重，必须由后端支持客户端幂等键（如 Idempotency-Key）。
 *
 * 说明：
 *   - 原生 JS，无依赖。
 *   - 不使用 Background Sync API（iOS Safari 不支持）。
 *   - 不依赖 Service Worker，纯页面端逻辑。
 *   - 所有 IndexedDB 操作均包成 Promise；打开失败时降级为内存队列并 console.warn，
 *     不会把错误抛给调用方。
 */

(function () {
  'use strict';

  var DB_NAME = 'sb-offline';
  var DB_VERSION = 1;
  var STORE = 'queue';

  var dbPromise = null; // Promise<IDBDatabase|null>；null 表示已降级为内存队列
  var memoryQueue = []; // 降级用：{ id, method, url, headers, body, enqueuedAt }
  var memoryNextId = 1;
  var usingMemory = false;

  // ---------- IndexedDB 打开 ----------

  function openDB() {
    if (dbPromise) return dbPromise;

    dbPromise = new Promise(function (resolve) {
      var req;
      try {
        if (typeof indexedDB === 'undefined' || !indexedDB) {
          throw new Error('IndexedDB unavailable');
        }
        req = indexedDB.open(DB_NAME, DB_VERSION);
      } catch (err) {
        fallbackToMemory('open threw: ' + (err && err.message ? err.message : err));
        resolve(null);
        return;
      }

      req.onupgradeneeded = function (event) {
        var db = event.target.result;
        if (!db.objectStoreNames.contains(STORE)) {
          db.createObjectStore(STORE, { keyPath: 'id', autoIncrement: true });
        }
      };

      req.onsuccess = function (event) {
        var db = event.target.result;
        db.onversionchange = function () {
          try { db.close(); } catch (e) { /* ignore */ }
        };
        resolve(db);
      };

      req.onerror = function () {
        fallbackToMemory('open error: ' + (req.error && req.error.message ? req.error.message : 'unknown'));
        resolve(null);
      };

      req.onblocked = function () {
        // 不阻塞：其它标签页持有旧连接时，仍然尝试继续（可能稍后成功）。
        console.warn('[offline-queue] IndexedDB open blocked by another connection.');
      };
    });

    return dbPromise;
  }

  function fallbackToMemory(reason) {
    if (!usingMemory) {
      usingMemory = true;
      console.warn('[offline-queue] IndexedDB 不可用，已降级为内存队列（刷新页面即丢失）。原因：' + reason);
    }
  }

  // ---------- 通用事务辅助 ----------

  function withStore(mode, fn) {
    return openDB().then(function (db) {
      if (!db) return null; // 降级标记
      return new Promise(function (resolve, reject) {
        var tx, store, result;
        try {
          tx = db.transaction(STORE, mode);
          store = tx.objectStore(STORE);
          result = fn(store, tx);
        } catch (err) {
          reject(err);
          return;
        }

        tx.oncomplete = function () { resolve(result && result.__value !== undefined ? result.__value : result); };
        tx.onerror = function () { reject(tx.error || new Error('transaction error')); };
        tx.onabort = function () { reject(tx.error || new Error('transaction aborted')); };
      });
    });
  }

  function reqToPromise(request) {
    return new Promise(function (resolve, reject) {
      request.onsuccess = function () { resolve(request.result); };
      request.onerror = function () { reject(request.error); };
    });
  }

  // ---------- 规范化输入 ----------

  function normalizeHeaders(headers) {
    if (!headers || typeof headers !== 'object') return {};
    var out = {};
    Object.keys(headers).forEach(function (k) {
      var v = headers[k];
      if (v !== undefined && v !== null) out[k] = String(v);
    });
    return out;
  }

  function normalizeBody(body) {
    if (body === undefined || body === null) return null;
    if (typeof body === 'string') return body;
    try {
      return JSON.stringify(body);
    } catch (e) {
      return String(body);
    }
  }

  // ---------- 公开 API ----------

  /**
   * 入队一条写操作。
   * @param {{method:string,url:string,headers?:object,body?:string|object|null}} op
   * @returns {Promise<number>} 记录 id
   */
  function enqueue(op) {
    if (!op || typeof op !== 'object') {
      return Promise.reject(new TypeError('enqueue(op): op 必须是对象'));
    }
    var method = String(op.method || '').toUpperCase();
    var url = op.url;
    if (!method) return Promise.reject(new TypeError('enqueue(op): method 必填'));
    if (!url) return Promise.reject(new TypeError('enqueue(op): url 必填'));

    var record = {
      method: method,
      url: String(url),
      headers: normalizeHeaders(op.headers),
      body: normalizeBody(op.body),
      enqueuedAt: Date.now()
    };

    return openDB().then(function (db) {
      if (!db) {
        // 内存降级
        var id = memoryNextId++;
        var mem = Object.assign({ id: id }, record);
        memoryQueue.push(mem);
        return id;
      }
      return new Promise(function (resolve, reject) {
        var tx;
        try {
          tx = db.transaction(STORE, 'readwrite');
        } catch (err) {
          reject(err);
          return;
        }
        var store = tx.objectStore(STORE);
        var req = store.add(record);
        req.onsuccess = function () {
          var id = req.result;
          tx.oncomplete = function () { resolve(id); };
        };
        req.onerror = function () { reject(req.error); };
        tx.onerror = function () { reject(tx.error || new Error('transaction error')); };
        tx.onabort = function () { reject(tx.error || new Error('transaction aborted')); };
      });
    });
  }

  /**
   * 当前待回放条数。
   * @returns {Promise<number>}
   */
  function pendingCount() {
    return openDB().then(function (db) {
      if (!db) return memoryQueue.length;
      return withStore('readonly', function (store) {
        var req = store.count();
        return { __value: null, promise: reqToPromise(req) };
      }).then(function () {
        // 上面写法不够直接，改用下方专用实现（保留简洁性）。
        return 0;
      }).catch(function () { return 0; }).then(function () {
        // 重新做一次干净的 count，避免复杂包装。
        return new Promise(function (resolve) {
          var tx = db.transaction(STORE, 'readonly');
          var r = tx.objectStore(STORE).count();
          r.onsuccess = function () { resolve(r.result || 0); };
          r.onerror = function () { resolve(0); };
          tx.onabort = function () { resolve(0); };
        });
      });
    });
  }

  /**
   * 按 id 升序返回全部记录（调试/展示用）。
   * @returns {Promise<Array>}
   */
  function peekAll() {
    return openDB().then(function (db) {
      if (!db) {
        return memoryQueue.slice().sort(function (a, b) { return a.id - b.id; });
      }
      return new Promise(function (resolve) {
        var tx = db.transaction(STORE, 'readonly');
        var r = tx.objectStore(STORE).getAll();
        r.onsuccess = function () {
          var arr = r.result || [];
          arr.sort(function (a, b) { return a.id - b.id; });
          resolve(arr);
        };
        r.onerror = function () {
          console.warn('[offline-queue] peekAll failed:', r.error);
          resolve([]);
        };
        tx.onabort = function () { resolve([]); };
      });
    });
  }

  /**
   * 清空队列。
   * @returns {Promise<void>}
   */
  function clear() {
    return openDB().then(function (db) {
      if (!db) {
        memoryQueue = [];
        memoryNextId = 1;
        return;
      }
      return new Promise(function (resolve, reject) {
        var tx;
        try {
          tx = db.transaction(STORE, 'readwrite');
        } catch (err) {
          reject(err);
          return;
        }
        tx.objectStore(STORE).clear();
        tx.oncomplete = function () { resolve(); };
        tx.onerror = function () { reject(tx.error || new Error('clear failed')); };
        tx.onabort = function () { reject(tx.error || new Error('clear aborted')); };
      });
    });
  }

  function deleteById(db, id) {
    return new Promise(function (resolve) {
      var tx;
      try {
        tx = db.transaction(STORE, 'readwrite');
      } catch (err) {
        resolve(false);
        return;
      }
      tx.objectStore(STORE).delete(id);
      tx.oncomplete = function () { resolve(true); };
      tx.onerror = function () { resolve(false); };
      tx.onabort = function () { resolve(false); };
    });
  }

  function fetchOne(rec) {
    var init = { method: rec.method, headers: rec.headers || {} };
    if (rec.body !== null && rec.body !== undefined && rec.method !== 'GET' && rec.method !== 'HEAD') {
      init.body = rec.body;
    }
    return fetch(rec.url, init);
  }

  /**
   * 回放队列（严格按 id 升序）。
   *   - 网络错误（fetch 抛 TypeError 等）或 HTTP >= 500：停止回放，保留该条及之后所有记录。
   *   - HTTP 4xx：视为服务端已拒绝，丢弃该条，计入 failed，继续下一条。
   *   - HTTP 2xx/3xx：成功，丢弃该条，计入 ok。
   * @returns {Promise<{ok:number, failed:number}>}
   */
  function replay() {
    var stats = { ok: 0, failed: 0 };

    return openDB().then(function (db) {
      if (!db) {
        return replayMemory(stats);
      }
      return replayIDB(db, stats);
    });
  }

  function replayMemory(stats) {
    memoryQueue.sort(function (a, b) { return a.id - b.id; });
    var remaining = [];
    var stopped = false;

    function step(i) {
      if (i >= memoryQueue.length) return Promise.resolve();
      if (stopped) {
        remaining = remaining.concat(memoryQueue.slice(i));
        return Promise.resolve();
      }
      var rec = memoryQueue[i];
      return fetchOne(rec).then(function (res) {
        if (res.status >= 500) {
          // 服务端错误：停止并保留本条及之后
          remaining.push(rec);
          stopped = true;
          return step(i + 1);
        }
        if (res.status >= 400) {
          // 4xx：丢弃，计入 failed
          stats.failed += 1;
          return step(i + 1);
        }
        stats.ok += 1;
        return step(i + 1);
      }).catch(function () {
        // 网络错误：停止并保留本条及之后
        remaining.push(rec);
        stopped = true;
        return step(i + 1);
      });
    }

    return step(0).then(function () {
      memoryQueue = remaining;
      return stats;
    });
  }

  function replayIDB(db, stats) {
    // 先取全部，逐条处理；处理成功/丢弃后删除，失败则中止。
    return new Promise(function (resolve) {
      var tx = db.transaction(STORE, 'readonly');
      var r = tx.objectStore(STORE).getAll();
      r.onsuccess = function () { resolve(r.result || []); };
      r.onerror = function () { resolve([]); };
      tx.onabort = function () { resolve([]); };
    }).then(function (all) {
      all.sort(function (a, b) { return a.id - b.id; });
      var stopped = false;

      function step(i) {
        if (i >= all.length || stopped) return Promise.resolve();
        var rec = all[i];
        return fetchOne(rec).then(function (res) {
          if (res.status >= 500) {
            stats.failed += 0; // 不计入 failed；保留等待下次
            stopped = true;
            return step(i + 1);
          }
          if (res.status >= 400) {
            // 4xx：丢弃，继续
            stats.failed += 1;
            return deleteById(db, rec.id).then(function () { return step(i + 1); });
          }
          stats.ok += 1;
          return deleteById(db, rec.id).then(function () { return step(i + 1); });
        }).catch(function () {
          // 网络错误：停止，保留本条及之后
          stopped = true;
          return step(i + 1);
        });
      }

      return step(0).then(function () { return stats; });
    });
  }

  // ---------- 导出 ----------

  window.__sbOfflineQueue = {
    enqueue: enqueue,
    pendingCount: pendingCount,
    peekAll: peekAll,
    replay: replay,
    clear: clear
  };
})();
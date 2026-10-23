(function() {
  'use strict';

  const PAGE_I18N = {
    "zh-CN": {
      "dc.pageTitle": "视频拆解",
      "dc.kicker": "VIDEO DECONSTRUCTION · 反推爆款结构",
      "dc.heading": "视频拆解",
      "dc.subtitle": "看到喜欢的视频、想学它的拍法时，把它拆开看：分镜、节奏、结构公式与逐镜反推提示词，一键变成你项目里的同款分镜草稿。",
      "dc.createTitle": "发起拆解",
      "dc.project": "项目",
      "dc.episode": "目标剧集（生成同款用）",
      "dc.asset": "已有视频素材",
      "dc.file": "上传本地视频",
      "dc.uploadBtn": "上传并发起拆解",
      "dc.assetBtn": "用所选素材拆解",
      "dc.linkNote": "链接导入（抖音 / TikTok / 小红书）为后续功能，尚未接入；当前请先把视频下载到本地再上传，或选择素材库里已有的视频。",
      "dc.listTitle": "本项目的拆解",
      "dc.empty": "还没有拆解记录，先在上面发起一个。",
      "dc.reportBtn": "导出 Markdown 报告",
      "dc.genBtn": "生成同款分镜",
      "dc.deleteBtn": "删除",
      "dc.backBtn": "返回",
      "dc.structureTitle": "全片结构",
      "dc.formulaTitle": "爆款公式（规则提炼）",
      "dc.shotsTitle": "逐镜拆解",
      "dc.scriptTitle": "创作剧本模板",
      "dc.basisNote": "口径说明：时长/切分/关键帧为实测数据；结构与公式为规则推断；画面主体、景别、运镜等视觉字段待 AI 增强，当前以占位标注，不冒充识别结果。",
      "status.PENDING": "等待中",
      "status.RUNNING": "拆解中",
      "status.DONE": "已完成",
      "status.FAILED": "失败",
      "error.loadFailed": "加载失败",
      "error.requestFailed": "请求失败",
      "toast.generated": "已生成 {count} 个分镜草稿到目标剧集",
      "toast.uploadSuccess": "已发起拆解，处理中会自动刷新",
      "toast.copySuccess": "复制提示词成功",
      "toast.copyFail": "复制提示词失败",
      "confirm.delete": "确定删除这条拆解记录？源视频文件副本与关键帧会一并删除。",
      "error.noProject": "请先选择项目",
      "error.noFile": "请先选择视频文件",
      "error.noAsset": "请先选择素材",
      "error.noEpisode": "请先选择剧集"
    },
    "en": {
      "dc.pageTitle": "Video Deconstruction",
      "dc.kicker": "VIDEO DECONSTRUCTION",
      "dc.heading": "Video Deconstruction",
      "dc.subtitle": "Break down a video you like: shots, rhythm, structure formula and per-shot reverse prompts, turned into shot drafts in your project with one click.",
      "dc.createTitle": "New Deconstruction",
      "dc.project": "Project",
      "dc.episode": "Target Episode (for shot generation)",
      "dc.asset": "Existing Video Asset",
      "dc.file": "Upload Local Video",
      "dc.uploadBtn": "Upload & Deconstruct",
      "dc.assetBtn": "Deconstruct Selected Asset",
      "dc.linkNote": "Link import (Douyin / TikTok / Xiaohongshu) is a future feature and not yet available; please download the video and upload it, or pick an existing asset.",
      "dc.listTitle": "Deconstructions in This Project",
      "dc.empty": "No deconstruction records yet. Start one above.",
      "dc.reportBtn": "Export Markdown Report",
      "dc.genBtn": "Generate Matching Shots",
      "dc.deleteBtn": "Delete",
      "dc.backBtn": "Back",
      "dc.structureTitle": "Overall Structure",
      "dc.formulaTitle": "Viral Formula (rule-derived)",
      "dc.shotsTitle": "Shot-by-Shot Breakdown",
      "dc.scriptTitle": "Reusable Script Template",
      "dc.basisNote": "Basis: durations/cuts/keyframes are measured data; structure and formula are rule-derived; visual fields (subject, shot size, camera movement) await AI enrichment and are marked as placeholders, not recognition results.",
      "status.PENDING": "Pending",
      "status.RUNNING": "Running",
      "status.DONE": "Done",
      "status.FAILED": "Failed",
      "error.loadFailed": "Load failed",
      "error.requestFailed": "Request failed",
      "toast.generated": "Generated {count} shot drafts to target episode",
      "toast.uploadSuccess": "Deconstruction started. Processing will refresh automatically.",
      "toast.copySuccess": "Prompt copied successfully",
      "toast.copyFail": "Failed to copy prompt",
      "confirm.delete": "Are you sure to delete this deconstruction? Source video copies and keyframes will be deleted permanently.",
      "error.noProject": "Please select a project",
      "error.noFile": "Please select a video file",
      "error.noAsset": "Please select an asset",
      "error.noEpisode": "Please select an episode"
    }
  };

  if (window.DFI18N) {
    // DFI18N.register 期望 key 优先的字典（{ 'dc.x': { 'zh-CN': .., en: .. } }），
    // 本页表是语言优先组织的，这里转置后再注册，否则 applyI18n 会把正文覆盖成键名。
    const byKey = {};
    Object.entries(PAGE_I18N).forEach(([lang, dict]) => {
      Object.entries(dict).forEach(([k, v]) => {
        (byKey[k] = byKey[k] || {})[lang] = v;
      });
    });
    DFI18N.register(byKey);
  }

  function _t(key, zh) {
    const lang = (window.DFI18N && typeof DFI18N.getLang === 'function') ? DFI18N.getLang() : 'zh-CN';
    return (PAGE_I18N[lang] && PAGE_I18N[lang][key]) || PAGE_I18N['zh-CN'][key] || zh || key;
  }

  function api(path, opts) {
    const url = path.startsWith('/') ? path : '/api/projects/' + path;
    const defaultOpts = {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json'
      }
    };
    const options = { ...defaultOpts, ...opts };
    
    if (options.body && typeof options.body === 'object') {
      options.body = JSON.stringify(options.body);
    }

    return fetch(url, options)
      .then(response => {
        if (!response.ok) {
          return response.json().then(err => {
            throw new Error(err.message || err.error || _t('error.requestFailed'));
          });
        }
        if (options.raw) return response;
        if (response.status === 204) return null;
        return response.json();
      });
  }

  function esc(s) {
    return s ? s.toString().replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;') : '';
  }

  let toastTimer = null;
  function showToast(msg) {
    const toast = document.getElementById('toast');
    const body = document.getElementById('toastMessage');
    if (body) body.textContent = msg;
    toast.classList.add('show');
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { toast.classList.remove('show'); }, 2600);
  }

  function fmt1(v) {
    return v === null || v === undefined ? '—' : Number(v).toFixed(1);
  }

  function fmtTime(seconds) {
    if (seconds === null || seconds === undefined) return '—';
    return `${Math.floor(seconds)}s`;
  }

  const state = {
    projectId: null,
    episodeId: null,
    currentId: null,
    pollTimer: null
  };

  function init() {
    const params = new URLSearchParams(window.location.search);
    const projectIdParam = params.get('projectId');
    loadProjects().then(() => {
      const projectSelect = document.getElementById('dcProject');
      if (projectIdParam) {
        const option = Array.from(projectSelect.options).find(opt => opt.value === projectIdParam);
        if (option) option.selected = true;
      }
      onProjectChange();
    });
  }

  function loadProjects() {
    return api('/api/projects')
      .then(projects => {
        const select = document.getElementById('dcProject');
        select.innerHTML = projects.map(p => `<option value="${esc(p.id)}">${esc(p.title)}</option>`).join('');
      });
  }

  function onProjectChange() {
    const projectSelect = document.getElementById('dcProject');
    state.projectId = projectSelect.value ? parseInt(projectSelect.value) : null;
    
    if (!state.projectId) {
      showToast(_t('error.noProject'));
      return;
    }
    
    const episodeSelect = document.getElementById('dcEpisode');
    episodeSelect.innerHTML = '<option value="">加载中...</option>';
    episodeSelect.disabled = true;
    
    loadEpisodes()
      .then(() => { episodeSelect.disabled = false; })
      .catch(() => { episodeSelect.disabled = false; });

    loadAssets();
    loadList();
  }

  function loadEpisodes() {
    return api(`${state.projectId}/episodes`)
      .then(episodes => {
        const select = document.getElementById('dcEpisode');
        if (!episodes || episodes.length === 0) {
          select.innerHTML = '<option value="">无可用剧集</option>';
          state.episodeId = null;
          return;
        }
        select.innerHTML = episodes.map(ep =>
          `<option value="${esc(ep.id)}">第 ${ep.episodeNo} 集 ${esc(ep.title)}</option>`
        ).join('');
        state.episodeId = select.value;
      });
  }

  function loadAssets() {
    // 素材库是全站共享的（Asset 无项目归属），走全局接口按类型过滤。
    return api('/api/assets/?type=VIDEO')
      .then(assets => {
        const select = document.getElementById('dcAsset');
        const videos = (assets || []).filter(a => a.type === 'VIDEO');
        if (videos.length === 0) {
          select.innerHTML = '<option value="">无视频素材</option>';
          return;
        }
        select.innerHTML = videos.map(a =>
          `<option value="${esc(a.id)}">${esc(a.fileName)}</option>`
        ).join('');
      })
      .catch(() => {
        document.getElementById('dcAsset').innerHTML = '<option value="">无视频素材</option>';
      });
  }

  function loadList() {
    return api(`${state.projectId}/deconstructions`)
      .then(list => {
        const listEl = document.getElementById('dcList');
        const emptyEl = document.getElementById('dcEmpty');
        
        if (list.length === 0) {
          listEl.innerHTML = '';
          emptyEl.hidden = false;
          return;
        }

        emptyEl.hidden = true;
        listEl.innerHTML = list.map(item => {
          const statusText = _t(`status.${item.status}`);
          const meta = item.status === 'DONE'
            ? `${statusText} · ${item.shotCount} 镜 · ${fmt1(item.avgShotDurationSec)}s · ${item.rhythmClass || ''}`
            : statusText;
          const createdAt = new Date(item.createdAt).toISOString().replace('T', ' ').slice(0, 16);
          
          return `
            <div class="border rounded p-2 mb-2 d-flex justify-content-between">
              <div>
                <strong>${esc(item.sourceName)}</strong>
                <div class="dc-meta small text-muted">${meta} · ${createdAt}</div>
                ${item.status === 'FAILED' ? `<div class="text-danger">${esc(item.errorMessage)}</div>` : ''}
              </div>
              <div>
                <button class="btn btn-sm btn-outline-primary" data-action="view" data-id="${item.id}">查看</button>
                <button class="btn btn-sm btn-outline-danger" data-action="delete" data-id="${item.id}">删除</button>
              </div>
            </div>
          `;
        }).join('');
        
        const hasRunning = list.some(item => item.status === 'PENDING' || item.status === 'RUNNING');
        if (hasRunning) {
          startPolling();
        } else {
          stopPolling();
        }
      })
      .catch(err => showToast(err.message || _t('error.loadFailed')));
  }

  function startPolling() {
    stopPolling();
    state.pollTimer = setInterval(() => {
      loadList().then(() => {
        if (state.currentId) {
          api(`${state.projectId}/deconstructions/${state.currentId}`)
            .then(detail => {
              if (detail.status === 'DONE' || detail.status === 'FAILED') {
                loadList();
              }
            });
        }
      });
    }, 2500);
  }

  function stopPolling() {
    if (state.pollTimer) {
      clearInterval(state.pollTimer);
      state.pollTimer = null;
    }
  }

  function uploadFile() {
    if (!state.projectId) {
      showToast(_t('error.noProject'));
      return;
    }
    
    const fileInput = document.getElementById('dcFile');
    const file = fileInput.files[0];
    if (!file) {
      showToast(_t('error.noFile'));
      return;
    }
    
    const formData = new FormData();
    formData.append('file', file);
    
    const errorEl = document.getElementById('dcError');
    errorEl.textContent = '';
    errorEl.hidden = true;

    fetch(`/api/projects/${state.projectId}/deconstructions/upload`, {
      method: 'POST',
      body: formData
    })
      .then(response => {
        if (!response.ok) return response.json().then(err => { throw err; });
        return response.json();
      })
      .then(() => {
        loadList();
        showToast(_t('toast.uploadSuccess'));
      })
      .catch(err => {
        errorEl.textContent = err.message || _t('error.requestFailed');
        errorEl.hidden = false;
      });
  }

  function useAsset() {
    if (!state.projectId) {
      showToast(_t('error.noProject'));
      return;
    }
    
    const assetSelect = document.getElementById('dcAsset');
    const assetId = parseInt(assetSelect.value);
    if (!assetId) {
      showToast(_t('error.noAsset'));
      return;
    }
    
    api(`${state.projectId}/deconstructions`, {
      method: 'POST',
      body: { assetId }
    })
      .then(() => {
        loadList();
      })
      .catch(err => {
        showToast(err.message || _t('error.requestFailed'));
      });
  }

  function viewDetail(id) {
    state.currentId = id;
    api(`${state.projectId}/deconstructions/${id}`)
      .then(detail => {
        const card = document.getElementById('dcDetailCard');
        const reportBtn = document.getElementById('dcReportBtn');
        const titleEl = document.getElementById('dcDetailTitle');
        
        // Title
        titleEl.textContent = detail.sourceName;
        
        // Report button
        reportBtn.href = `/api/projects/${state.projectId}/deconstructions/${id}/report`;
        if (detail.status !== 'DONE') {
          reportBtn.classList.add('disabled');
          reportBtn.setAttribute('aria-disabled', 'true');
        } else {
          reportBtn.classList.remove('disabled');
          reportBtn.removeAttribute('aria-disabled');
        }
        
        // Metrics
        const metrics = [
          { label: '时长', value: fmt1(detail.durationSec) },
          { label: '分辨率', value: `${detail.width}×${detail.height}` },
          { label: '镜数', value: detail.shotCount },
          { label: '平均镜长', value: fmt1(detail.avgShotDurationSec) },
          { label: '每分钟切数', value: fmt1(detail.cutsPerMinute) },
          { label: '节奏分类', value: detail.rhythmClass || '' }
        ];
        
        document.getElementById('dcMetrics').innerHTML = metrics.map(m => 
          `<div class="col-6 col-md-2">
            <div class="card">
              <div class="card-body py-2 text-center">
                <div class="dc-label small">${esc(m.label)}</div>
                <div class="dc-value">${esc(m.value)}</div>
              </div>
            </div>
          </div>`
        ).join('');
        
        // Parse resultJson
        const result = detail.resultJson ? JSON.parse(detail.resultJson) : {};
        const structure = result.structure || [];
        const formula = result.formula || {};
        
        // Timeline
        document.getElementById('dcTimeline').innerHTML = structure.map(s => {
          const percentage = (s.endSec - s.startSec) / detail.durationSec * 100;
          const colorMap = {
            '钩子': '#d63939',
            '主体': '#206bc4',
            '转折': '#f76707',
            '收尾': '#2fb344'
          };
          return `
            <div class="dc-timeline-segment" 
                 style="width: ${percentage}%; background-color: ${colorMap[s.kind] || '#ccc'}"
                 title="${esc(s.kind)} ${fmtTime(s.startSec)}–${fmtTime(s.endSec)}">
            </div>
          `;
        }).join('');
        
        // Structure List
        document.getElementById('dcStructureList').innerHTML = structure.map(s => 
          `<li>${esc(s.kind)} ${fmtTime(s.startSec)}–${fmtTime(s.endSec)}（${s.shotNos} 镜）: ${esc(s.note)}</li>`
        ).join('');
        
        // Formula（构成占比已包含在 notes 的「镜头构成」一条里，不再重复渲染）
        document.getElementById('dcFormula').innerHTML = `
          <ul>${(formula.notes || []).map(n => `<li>${esc(n)}</li>`).join('')}</ul>
        `;
        
        // Script
        document.getElementById('dcScript').textContent = result.scriptTemplate || '';
        
        // Shots
        const shotsHtml = detail.shots.map((shot, idx) => {
          const frameSrc = shot.keyframeUrl ? shot.keyframeUrl : '';
          const frameContent = shot.keyframeUrl ? 
            `<img class="dc-frame" src="${esc(frameSrc)}" alt="Shot ${idx+1}">` : 
            `<div class="dc-frame">无关键帧</div>`;
          
          return `
            <div class="card">
              ${frameContent}
              <div class="card-body">
                <h6>第 ${shot.shotNo} 镜</h6>
                <div class="dc-meta">
                  ${fmt1(shot.startSec)}s–${fmt1(shot.endSec)}s · ${fmt1(shot.durationSec)}s
                </div>
                <div class="mt-1">
                  ${shot.segmentRole ? `<span class="badge bg-secondary me-1">${esc(shot.segmentRole)}</span>` : ''}
                  ${shot.durationClass ? `<span class="badge bg-info">${esc(shot.durationClass)}</span>` : ''}
                </div>
                <div class="dc-prompt small mt-2">
                  <span class="dc-prompt-text">${esc(shot.promptSeedance || shot.promptGeneric)}</span>
                </div>
                <button class="btn btn-sm btn-outline-secondary mt-2" data-copy="${idx}">复制 Seedance 提示词</button>
              </div>
            </div>
          `;
        }).join('');
        document.getElementById('dcShots').innerHTML = shotsHtml;

        card.hidden = false;
      })
      .catch(err => {
        showToast(err.message || _t('error.requestFailed'));
      });
  }

  function generateShots() {
    if (!state.episodeId) {
      showToast(_t('error.noEpisode'));
      return;
    }
    
    api(`${state.projectId}/deconstructions/${state.currentId}/generate-shots`, {
      method: 'POST',
      body: { episodeId: parseInt(state.episodeId) }
    })
      .then(res => {
        showToast(_t('toast.generated').replace('{count}', res.createdCount));
      })
      .catch(err => {
        showToast(err.message || _t('error.requestFailed'));
      });
  }

  function deleteDeconstruction(id) {
    if (!confirm(_t('confirm.delete'))) return;
    
    api(`${state.projectId}/deconstructions/${id}`, { method: 'DELETE' })
      .then(() => {
        if (id === state.currentId) {
          state.currentId = null;
          document.getElementById('dcDetailCard').hidden = true;
        }
        loadList();
        showToast('已删除');
      })
      .catch(err => {
        showToast(err.message || _t('error.requestFailed'));
      });
  }

  document.addEventListener('DOMContentLoaded', () => {
    init();
    
    // Project change
    document.getElementById('dcProject').addEventListener('change', onProjectChange);
    
    // Episode change
    document.getElementById('dcEpisode').addEventListener('change', e => {
      state.episodeId = e.target.value;
    });
    
    // Upload button
    document.getElementById('dcUploadBtn').addEventListener('click', uploadFile);
    
    // Asset button
    document.getElementById('dcAssetBtn').addEventListener('click', useAsset);
    
    // Back button
    document.getElementById('dcBackBtn').addEventListener('click', () => {
      state.currentId = null;
      document.getElementById('dcDetailCard').hidden = true;
    });
    
    // Generate button
    document.getElementById('dcGenBtn').addEventListener('click', generateShots);
    
    // Detail delete button
    document.getElementById('dcDeleteBtn').addEventListener('click', () => {
      if (state.currentId) {
        deleteDeconstruction(state.currentId);
      }
    });
    
    // Event delegation for list buttons
    document.getElementById('dcList').addEventListener('click', e => {
      const btn = e.target.closest('button');
      if (!btn) return;
      
      const action = btn.getAttribute('data-action');
      const id = parseInt(btn.getAttribute('data-id'));
      
      if (action === 'view') {
        viewDetail(id);
      } else if (action === 'delete') {
        deleteDeconstruction(id);
      }
    });
    
    // Copy buttons in shots
    document.getElementById('dcShots').addEventListener('click', e => {
      const btn = e.target.closest('button[data-copy]');
      if (!btn) return;
      
      const idx = parseInt(btn.getAttribute('data-copy'));
      const shotsEl = document.getElementById('dcShots');
      const promptSpan = shotsEl.children[idx].querySelector('.dc-prompt-text');
      const prompt = promptSpan ? promptSpan.textContent.trim() : '';
      
      navigator.clipboard.writeText(prompt)
        .then(() => showToast(_t('toast.copySuccess')))
        .catch(() => showToast(_t('toast.copyFail')));
    });
  });
})();

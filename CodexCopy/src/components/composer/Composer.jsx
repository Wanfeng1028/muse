import { useState, useRef, useEffect } from 'react';
import { SendIcon, ChevronDown, CheckIcon, StopIcon, GitIcon, FolderIcon, MonitorIcon, MicIcon, GoalIcon, ZapIcon } from '../icons';
import { models } from '../../data/mock';

// 真实 Codex composer（flaviocopes.com 真机截图逐像素对照）：
// 顶部 chips：[项目] [Local] [分支]（在文本框上方）
// 底部：+ | Approve for me | Goal | … | 模型（闪电图标）| 麦克风 | 发送（黑圆上箭头）
export default function Composer({ onSend, streaming, onStop, placeholder, model, onModelChange, threadMode, branch, projectName }) {
  const [text, setText] = useState('');
  const [pickerOpen, setPickerOpen] = useState(false);
  const [plusOpen, setPlusOpen] = useState(false);
  const [reasoning, setReasoning] = useState('Medium');
  const [fast, setFast] = useState(false);
  const [planMode, setPlanMode] = useState(false);
  const [approveForMe, setApproveForMe] = useState(false);
  const taRef = useRef(null);

  useEffect(() => {
    const ta = taRef.current;
    if (ta) {
      ta.style.height = 'auto';
      ta.style.height = Math.min(ta.scrollHeight, 200) + 'px';
    }
  }, [text]);

  const submit = () => {
    const v = text.trim();
    if (!v || streaming) return;
    onSend(v);
    setText('');
  };

  return (
    <div className="composer-wrap">
      <div className="composer-inner">
        <div className="composer">
          {/* 顶部：项目 + 关联文件（新版样式） */}
          <div className="composer-chips">
            <span className="chip"><FolderIcon size={12} /> {projectName || 'codex-copy'}</span>
            <span className="chip"><DocIcon size={12} /> Plugins</span>
          </div>
          <textarea
            ref={taRef}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit(); }
            }}
            placeholder={placeholder}
            rows={1}
          />
          <div className="composer-bar">
            <div style={{ position: 'relative' }}>
              <button className="composer-plus" title="Add files and more" onClick={() => setPlusOpen(!plusOpen)}>
                +
              </button>
              {plusOpen && (
                <>
                  <div className="drop-mask" onClick={() => setPlusOpen(false)} />
                  <div className="drop-menu" style={{ bottom: 'calc(100% + 8px)', top: 'auto', minWidth: 200 }}>
                    <div className="drop-item" onClick={() => setPlusOpen(false)}>
                      <span style={{ flex: 1 }}>Files and folders</span>
                    </div>
                    <div className="drop-item" onClick={() => { setPlanMode(!planMode); setPlusOpen(false); }}>
                      <span style={{ flex: 1 }}>Plan mode</span>
                      {planMode && <CheckIcon size={13} />}
                    </div>
                  </div>
                </>
              )}
            </div>
            <button className={'composer-pill' + (approveForMe ? ' active' : '')}
              onClick={() => setApproveForMe(!approveForMe)} title="Approval setting">
              <CheckIcon size={12} /> Ask for approval
            </button>
            <button className="composer-pill" title="Set a goal">
              <GoalIcon size={13} /> Goal
            </button>
            {planMode && <span className="pill blue">Plan</span>}
            <span className="composer-sp" />
            <div style={{ position: 'relative' }}>
              <button className="model-control" onClick={() => setPickerOpen(!pickerOpen)} title="Model settings (Ctrl+Shift+M)">
                <ZapIcon size={12} /> {model} <ChevronDown size={12} />
              </button>
              {pickerOpen && (
                <>
                  <div className="drop-mask" onClick={() => setPickerOpen(false)} />
                  <div className="model-picker">
                    <div className="filter-menu-title">Model</div>
                    {models.map((m) => (
                      <div key={m} className="drop-item" onClick={() => { onModelChange(m); }}>
                        <span style={{ flex: 1 }}>{m}</span>
                        {m === model && <CheckIcon size={13} />}
                      </div>
                    ))}
                    <div className="filter-menu-title">Reasoning effort</div>
                    <div className="reasoning-row">
                      {['Low', 'Medium', 'High', 'XHigh'].map((r) => (
                        <button key={r}
                          className={'reason-pill' + (reasoning === r ? ' active' : '')}
                          onClick={() => setReasoning(r)}>{r === 'XHigh' ? 'Extra High' : r}</button>
                      ))}
                    </div>
                    <div className="drop-item" onClick={() => setFast(!fast)}>
                      <span style={{ flex: 1 }}>Fast mode</span>
                      <span className={'toggle' + (fast ? ' on' : '')} />
                    </div>
                  </div>
                </>
              )}
            </div>
            <button className="composer-tool" title="Voice input"><MicIcon size={15} /></button>
            {streaming ? (
              <button className="stop-btn" onClick={onStop} title="Stop (Esc)">
                <StopIcon size={13} />
              </button>
            ) : (
              <button className={'send-btn' + (text.trim() ? ' ready' : '')} onClick={submit} title="Send (⌘↵)">
                <SendIcon />
              </button>
            )}
          </div>
        </div>
        <div className="composer-hint">Codex can make mistakes. Review output before applying.</div>
      </div>
    </div>
  );
}

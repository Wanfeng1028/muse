import { useState, useRef, useEffect } from 'react';
import { SendIcon, ChevronDown, CheckIcon, StopIcon, GitIcon } from '../icons';
import { models } from '../../data/mock';

// 真实 Codex composer（实证）：
// - 左下角 "+"（Add files and more），菜单：Files and folders + Plan mode
// - 右下角模型控制，picker：model + reasoning（4档） + Fast
// - 发送中按钮变 Stop
// - 输入框下方：分支指示器 + 模式标
export default function Composer({ onSend, streaming, onStop, placeholder, model, onModelChange, threadMode, branch }) {
  const [text, setText] = useState('');
  const [pickerOpen, setPickerOpen] = useState(false);
  const [plusOpen, setPlusOpen] = useState(false);
  const [reasoning, setReasoning] = useState('Medium');
  const [fast, setFast] = useState(false);
  const [planMode, setPlanMode] = useState(false);
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
            {planMode && <span className="pill blue">Plan</span>}
            <span className="composer-sp" />
            <div style={{ position: 'relative' }}>
              <button className="model-control" onClick={() => setPickerOpen(!pickerOpen)} title="Model settings (Ctrl+Shift+M)">
                {model} <ChevronDown size={12} />
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
        {/* 输入框下方：分支 + 模式（真实位置，issue #14182） */}
        <div className="composer-context">
          <span className="ctx-item"><GitIcon size={12} /> {branch || 'main'}</span>
          <span className="ctx-sep">·</span>
          <span className="ctx-item">{threadMode === 'worktree' ? 'Worktree' : threadMode === 'cloud' ? 'Cloud' : 'Local'}</span>
        </div>
        <div className="composer-hint">Codex can make mistakes. Review output before applying.</div>
      </div>
    </div>
  );
}

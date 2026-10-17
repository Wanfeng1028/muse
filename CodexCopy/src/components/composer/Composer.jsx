import { useState, useRef, useEffect } from 'react';
import { AttachIcon, SendIcon, ChevronDown, CheckIcon } from '../icons';
import { models } from '../../data/mock';

// 真实 Codex 输入框：模型选择器在右下角（GitHub issue #38961 实证：
// "Click the model control at the lower-right of the composer"）
// 完整 picker 含：model + reasoning effort + Fast/service-tier
export default function Composer({ onSend, disabled, placeholder, model, onModelChange }) {
  const [text, setText] = useState('');
  const [pickerOpen, setPickerOpen] = useState(false);
  const [reasoning, setReasoning] = useState('Medium');
  const [fast, setFast] = useState(false);
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
    if (!v || disabled) return;
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
            placeholder={placeholder || "Ask Codex to do something…"}
            rows={1}
          />
          <div className="composer-bar">
            <button className="composer-tool" title="Attach files or images">
              <AttachIcon />
            </button>
            <span className="composer-sp" />
            {/* 模型控制在右下角 */}
            <div style={{ position: 'relative' }}>
              <button className="model-control" onClick={() => setPickerOpen(!pickerOpen)} title="Model settings">
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
                      {['Low', 'Medium', 'High'].map((r) => (
                        <button key={r}
                          className={'reason-pill' + (reasoning === r ? ' active' : '')}
                          onClick={() => setReasoning(r)}>{r}</button>
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
            <button className={'send-btn' + (text.trim() ? ' ready' : '')} onClick={submit} title="Send (⌘↵)">
              <SendIcon />
            </button>
          </div>
        </div>
        <div className="composer-hint">Codex can make mistakes. Review output before applying.</div>
      </div>
    </div>
  );
}

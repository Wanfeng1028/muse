import { useState, useRef, useEffect } from 'react';
import { AttachIcon, SendIcon, ChevronDown } from './icons';
import { models } from '../data/mock';

export default function Composer({ onSend, disabled }) {
  const [text, setText] = useState('');
  const [model, setModel] = useState(models[0]);
  const [modelOpen, setModelOpen] = useState(false);
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
            placeholder="Ask Codex to do something…"
            rows={1}
          />
          <div className="composer-bar">
            <button className="composer-tool" title="Attach files">
              <AttachIcon />
            </button>
            <div style={{ position: 'relative' }}>
              <button className="composer-tool" onClick={() => setModelOpen(!modelOpen)}>
                {model} <ChevronDown />
              </button>
              {modelOpen && (
                <div style={{
                  position: 'absolute', bottom: '100%', left: 0, marginBottom: 6,
                  background: 'var(--bg-elevated)', border: '1px solid var(--border)',
                  borderRadius: 'var(--radius-md)', minWidth: 160, overflow: 'hidden',
                  boxShadow: '0 8px 24px rgba(0,0,0,0.4)', zIndex: 10,
                }}>
                  {models.map((m) => (
                    <div
                      key={m}
                      onClick={() => { setModel(m); setModelOpen(false); }}
                      style={{
                        padding: '9px 14px', fontSize: 13, cursor: 'pointer',
                        background: m === model ? 'var(--bg-active)' : 'transparent',
                        color: m === model ? 'var(--text-primary)' : 'var(--text-secondary)',
                      }}
                    >
                      {m}
                    </div>
                  ))}
                </div>
              )}
            </div>
            <span className="composer-sp" />
            <button className={'send-btn' + (text.trim() ? ' ready' : '')} onClick={submit} title="Send">
              <SendIcon />
            </button>
          </div>
        </div>
        <div className="composer-hint">Codex can make mistakes. Review output before applying.</div>
      </div>
    </div>
  );
}

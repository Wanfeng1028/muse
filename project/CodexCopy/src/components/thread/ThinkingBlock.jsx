import { useState } from 'react';
import { ChevronRight } from '../icons';

export default function ThinkingBlock({ text, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="thinking">
      <div className="thinking-head" onClick={() => setOpen(!open)}>
        <span className={'twisty' + (open ? ' open' : '')}><ChevronRight size={13} /></span>
        <span>Thought for a moment</span>
      </div>
      {open && <div className="thinking-body">{text}</div>}
    </div>
  );
}

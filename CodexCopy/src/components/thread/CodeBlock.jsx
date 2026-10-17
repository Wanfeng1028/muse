import { useState } from 'react';
import { CheckIcon } from '../icons';

export default function CodeBlock({ lang = 'code', code }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard?.writeText(code).catch(() => {});
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };
  return (
    <div className="codeblock">
      <div className="codeblock-head">
        <span>{lang}</span>
        <span style={{ flex: 1 }} />
        <button className="mini-btn" onClick={copy}>
          {copied ? <><CheckIcon size={12} /> copied</> : 'copy'}
        </button>
      </div>
      <pre>{code}</pre>
    </div>
  );
}

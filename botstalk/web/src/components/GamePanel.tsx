import { useState } from 'react';
import { Gamepad2, Send, Hash } from 'lucide-react';
import type { GameStatePayload } from '../api';

interface Props {
  gameState: GameStatePayload | null;
  onSendAction: (game: string, action: unknown) => void;
}

export default function GamePanel({ gameState, onSendAction }: Props) {
  const [draft, setDraft] = useState('');

  if (!gameState) {
    return (
      <div className="game-panel game-panel-empty">
        <Gamepad2 size={20} strokeWidth={2} />
        <div>还没开始游戏</div>
        <div className="game-panel-hint">在娱乐厅里开一局，局面会显示在这里</div>
      </div>
    );
  }

  const send = () => {
    const text = draft.trim();
    if (!text) return;
    let action: unknown;
    try {
      action = JSON.parse(text);
    } catch {
      action = text;
    }
    onSendAction(gameState.game, action);
    setDraft('');
  };

  return (
    <div className="game-panel">
      <div className="game-panel-title">
        <Gamepad2 size={16} strokeWidth={2} />
        <span>{gameState.game}</span>
        {gameState.seat && <span className="game-panel-seat">座位 {gameState.seat}</span>}
      </div>
      <pre className="game-panel-state">
        {JSON.stringify(gameState.state ?? null, null, 2)}
      </pre>
      {gameState.state_hash && (
        <div className="game-panel-hash">
          <Hash size={12} strokeWidth={2} />
          <span>{gameState.state_hash.slice(0, 8)}</span>
        </div>
      )}
      <div className="game-panel-action">
        <input
          className="game-panel-input"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') send(); }}
          placeholder='输入动作 JSON，如 {"vote": "2"}'
        />
        <button className="btn-primary" type="button" onClick={send} title="发送动作">
          <Send size={14} strokeWidth={2} />
        </button>
      </div>
    </div>
  );
}
export type WSStatus = 'idle' | 'connecting' | 'open' | 'closed';

export interface InboundMessage {
  v: number;
  type: string;
  seq: number;
  gseq?: number;
  ack: number;
  sender: string;
  room: string;
  ts: number;
  payload: Record<string, unknown>;
}

export interface WSEvents {
  onStatus: (s: WSStatus) => void;
  onFrame: (frame: InboundMessage) => void;
}

const PROTOCOL_VERSION = '1.3';
const HEARTBEAT_MS = 20_000;
const RECONNECT_BASE_MS = 800;
const RECONNECT_MAX_MS = 15_000;

export class ChatSocket {
  private ws: WebSocket | null = null;
  private nick: string;
  private room: string;
  private events: WSEvents;
  private sendSeq = 1;
  private maxGseq = 0;
  private heartbeatTimer: number | null = null;
  private reconnectTimer: number | null = null;
  private reconnectAttempt = 0;
  private manuallyClosed = false;

  constructor(nick: string, room: string, events: WSEvents) {
    this.nick = nick;
    this.room = room;
    this.events = events;
  }

  connect(): void {
    this.manuallyClosed = false;
    this.openSocket();
  }

  close(): void {
    this.manuallyClosed = true;
    this.stopHeartbeat();
    if (this.reconnectTimer !== null) {
      window.clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      try {
        this.ws.close();
      } catch {
        /* noop */
      }
      this.ws = null;
    }
    this.events.onStatus('closed');
  }

  sendMessage(text: string, mentions: string[], replyTo?: string): void {
    const msg_id = makeUuid();
    this.send('message', {
      msg_id,
      text,
      mentions,
      intent: 'chat',
      ...(replyTo ? { reply_to: replyTo } : {}),
    });
  }

  sendTask(text: string, mentions: string[]): string {
    const taskId = makeUuid();
    this.send('message', {
      msg_id: makeUuid(),
      text,
      mentions,
      intent: 'task',
      task_id: taskId,
    });
    return taskId;
  }

  sendGameAction(game: string, action: unknown, seat?: string): void {
    this.send('game_action', {
      game,
      seat,
      action,
    });
  }

  sendApprovalDecision(approvalId: string, decision: 'approve' | 'reject', note?: string): void {
    const payload: Record<string, unknown> = { approval_id: approvalId, decision };
    if (note !== undefined && note.trim() !== '') {
      payload.note = note.trim();
    }
    this.send('approval_decision', payload);
  }

  private openSocket(): void {
    this.events.onStatus('connecting');
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const host = window.location.hostname || 'localhost';
    const url = `${proto}://${host}:8765`;
    let ws: WebSocket;
    try {
      ws = new WebSocket(url);
    } catch {
      this.scheduleReconnect();
      return;
    }
    this.ws = ws;

    ws.onopen = () => {
      this.reconnectAttempt = 0;
      this.events.onStatus('open');
      this.sendHello();
      this.startHeartbeat();
    };

    ws.onmessage = (ev) => {
      let frame: InboundMessage;
      try {
        frame = JSON.parse(typeof ev.data === 'string' ? ev.data : '') as InboundMessage;
      } catch {
        return;
      }
      if (typeof frame.gseq === 'number') {
        if (frame.gseq < this.maxGseq) {
          // 网关重启了（gseq 回退），重置水位，避免用旧高水位漏消息。
          this.maxGseq = frame.gseq;
        } else if (frame.gseq > this.maxGseq) {
          this.maxGseq = frame.gseq;
        }
      }
      this.events.onFrame(frame);
    };

    ws.onclose = () => {
      this.stopHeartbeat();
      this.ws = null;
      if (this.manuallyClosed) {
        this.events.onStatus('closed');
        return;
      }
      this.events.onStatus('closed');
      this.scheduleReconnect();
    };

    ws.onerror = () => {
      /* onclose 会接着触发 */
    };
  }

  private scheduleReconnect(): void {
    if (this.manuallyClosed) return;
    const delay = Math.min(
      RECONNECT_MAX_MS,
      RECONNECT_BASE_MS * Math.pow(2, this.reconnectAttempt),
    );
    this.reconnectAttempt += 1;
    this.reconnectTimer = window.setTimeout(() => {
      this.reconnectTimer = null;
      this.openSocket();
    }, delay);
  }

  private sendHello(): void {
    this.send('hello', {
      adapter_id: this.nick,
      protocol_version: PROTOCOL_VERSION,
      last_seen_seq: this.maxGseq,
    });
  }

  private startHeartbeat(): void {
    this.stopHeartbeat();
    this.heartbeatTimer = window.setInterval(() => {
      this.send('presence', { status: 'online' });
    }, HEARTBEAT_MS);
  }

  private stopHeartbeat(): void {
    if (this.heartbeatTimer !== null) {
      window.clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
  }

  private send(type: string, payload: Record<string, unknown>): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
    const seq = this.sendSeq++;
    const frame = {
      v: 1,
      type,
      seq,
      ack: 0,
      sender: this.nick,
      room: this.room,
      ts: Date.now(),
      payload,
    };
    try {
      this.ws.send(JSON.stringify(frame));
    } catch {
      /* 断线由 onclose 处理 */
    }
  }
}

function makeUuid(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID();
  }
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

import { useState } from 'react';
import { X, Copy, KeyRound } from 'lucide-react';
import {
  issuePairingCode,
  redeemPairingCode,
  type IssuedPairingCode,
  type RedeemedPairingCode
} from '../api';

interface Props {
  room: string;
  nick: string;
  onClose: () => void;
}

export default function PairingPanel({ room, nick, onClose }: Props) {
  const [issueMins, setIssueMins] = useState<string>('10');
  const [issueLoading, setIssueLoading] = useState(false);
  const [issueError, setIssueError] = useState('');
  const [issued, setIssued] = useState<IssuedPairingCode | null>(null);
  const [copied, setCopied] = useState(false);

  const [redeemCode, setRedeemCode] = useState('');
  const [redeemDevice, setRedeemDevice] = useState(nick);
  const [redeemLoading, setRedeemLoading] = useState(false);
  const [redeemError, setRedeemError] = useState('');
  const [redeemed, setRedeemed] = useState<RedeemedPairingCode | null>(null);

  const handleIssue = async () => {
    let mins = parseInt(issueMins, 10);
    if (isNaN(mins)) mins = 10;
    mins = Math.max(1, Math.min(60, mins));

    setIssueLoading(true);
    setIssueError('');
    setIssued(null);
    setCopied(false);
    try {
      const res = await issuePairingCode(room, nick, mins);
      setIssued(res);
    } catch (e: any) {
      setIssueError(e?.message ?? String(e));
    } finally {
      setIssueLoading(false);
    }
  };

  const handleRedeem = async () => {
    setRedeemLoading(true);
    setRedeemError('');
    setRedeemed(null);
    try {
      const res = await redeemPairingCode(redeemCode, redeemDevice);
      setRedeemed(res);
    } catch (e: any) {
      setRedeemError(e?.message ?? String(e));
    } finally {
      setRedeemLoading(false);
    }
  };

  const copyCode = async () => {
    if (!issued) return;
    try {
      await navigator.clipboard.writeText(issued.code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  };

  return (
    <div className="appr-panel">
      <div className="appr-head">
        <span className="appr-title">配对码</span>
        <button className="appr-close" onClick={onClose} aria-label="关闭">
          <X size={16} />
        </button>
      </div>

      <div className="appr-card">
        <h3>签发配对码</h3>
        <div className="appr-meta">
          <input
            type="number"
            value={issueMins}
            onChange={(e) => setIssueMins(e.target.value)}
            placeholder="分钟数"
          />
          <button className="appr-actions" onClick={handleIssue} disabled={issueLoading}>
            <KeyRound size={14} /> 签发
          </button>
        </div>

        {issueLoading && <div className="appr-meta">加载中…</div>}
        {issueError && <div className="appr-meta">{issueError}</div>}
        {issued && (
          <div className="appr-meta">
            <div>配对码：{issued.code}</div>
            <div>过期：{new Date(issued.expires_at_ms).toLocaleString()}</div>
            <button className="appr-actions" onClick={copyCode}>
              <Copy size={14} /> {copied ? '已复制' : '复制'}
            </button>
          </div>
        )}
      </div>

      <div className="appr-card">
        <h3>兑换配对码</h3>
        <div className="appr-meta">
          <input
            value={redeemCode}
            onChange={(e) => setRedeemCode(e.target.value)}
            placeholder="配对码"
          />
        </div>
        <div className="appr-meta">
          <input
            value={redeemDevice}
            onChange={(e) => setRedeemDevice(e.target.value)}
            placeholder="设备ID"
          />
        </div>
        <div className="appr-actions">
          <button onClick={handleRedeem} disabled={redeemLoading}>
            兑码
          </button>
        </div>

        {redeemLoading && <div className="appr-meta">加载中…</div>}
        {redeemError && <div className="appr-meta">{redeemError}</div>}
        {redeemed && (
          <div className="appr-meta">
            <div>已加入房间 {redeemed.room}，设备 {redeemed.adapter_id}</div>
            <div>兑码时间：{new Date(redeemed.redeemed_at_ms).toLocaleString()}</div>
          </div>
        )}
      </div>
    </div>
  );
}
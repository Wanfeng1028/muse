import { useEffect, useState } from 'react';
import { X, ShieldCheck, Check, Ban } from 'lucide-react';

export interface ApprovalRequest {
  approval_id: string;
  task_id: string;
  requester: string;
  assignee: string;
  title: string;
  expires_at_ms: number;
}

interface Props {
  approvals: ApprovalRequest[];
  nick: string;
  onClose: () => void;
  onDecide: (approvalId: string, decision: 'approve' | 'reject', note?: string) => void;
}

function formatCountdown(expiresAt: number, now: number) {
  const totalSeconds = Math.max(0, Math.floor((expiresAt - now) / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${String(seconds).padStart(2, '0')}`;
}

export default function ApprovalQueue({ approvals, nick, onClose, onDecide }: Props) {
  const [now, setNow] = useState(() => Date.now());
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [submitted, setSubmitted] = useState<Set<string>>(() => new Set());

  useEffect(() => {
    const timer = window.setInterval(() => {
      setNow(Date.now());
    }, 1000);

    return () => {
      window.clearInterval(timer);
    };
  }, []);

  const handleDecide = (
    approval: ApprovalRequest,
    decision: 'approve' | 'reject',
  ) => {
    const isExpired = Date.now() >= approval.expires_at_ms;
    const isSelf = nick === approval.assignee;

    if (submitted.has(approval.approval_id) || isExpired || isSelf) {
      return;
    }

    const note = (notes[approval.approval_id] || '').trim() || undefined;

    setSubmitted((previous) => {
      const next = new Set(previous);
      next.add(approval.approval_id);
      return next;
    });

    onDecide(approval.approval_id, decision, note);
  };

  return (
    <section className="appr-panel" aria-label="审批中心">
      <header className="appr-head">
        <h2 className="appr-title">审批中心</h2>
        <span className="appr-stats">待审批 {approvals.length}</span>
        <button
          type="button"
          className="appr-close"
          onClick={onClose}
          aria-label="关闭审批中心"
        >
          <X size={20} aria-hidden="true" />
        </button>
      </header>

      {approvals.length > 0 && (
        <div className="appr-hint">
          请核对任务信息后选择放行或驳回，备注会一起发送给执行者和派发人。
        </div>
      )}

      {approvals.length === 0 ? (
        <div className="appr-empty">
          <ShieldCheck size={44} aria-hidden="true" />
          <div>没有待审批的任务</div>
          <div className="appr-empty-sub">
            网关开启人工审批模式（TASK_APPROVAL_MODE=all）后，被挂起的任务会出现在这里
          </div>
        </div>
      ) : (
        <div className="appr-list">
          {approvals.map((approval) => {
            const isExpired = now >= approval.expires_at_ms;
            const isSelf = nick === approval.assignee;
            const isSubmitted = submitted.has(approval.approval_id);
            const actionsDisabled = isExpired || isSelf || isSubmitted;

            return (
              <article className="appr-card" key={approval.approval_id}>
                <div className="appr-card-top">
                  <h3 className="appr-title-text">{approval.title}</h3>
                  <span
                    className={`appr-countdown${isExpired ? ' is-expired' : ''}`}
                    aria-live="polite"
                  >
                    {isExpired
                      ? '已过期'
                      : formatCountdown(approval.expires_at_ms, now)}
                  </span>
                </div>

                <div className="appr-meta">
                  <span>
                    派发人 {approval.requester} → 执行者 {approval.assignee}
                  </span>
                  <span>任务 {approval.task_id.slice(0, 8)}</span>
                </div>

                <input
                  className="appr-note"
                  type="text"
                  value={notes[approval.approval_id] || ''}
                  onChange={(event) => {
                    const value = event.target.value;
                    setNotes((previous) => ({
                      ...previous,
                      [approval.approval_id]: value,
                    }));
                  }}
                  placeholder="给执行者/派发人留句话（可选）"
                  aria-label={`给${approval.title}填写审批备注`}
                />

                <div className="appr-actions">
                  <button
                    type="button"
                    className="appr-approve"
                    onClick={() => handleDecide(approval, 'approve')}
                    disabled={actionsDisabled}
                  >
                    <Check size={16} aria-hidden="true" />
                    放行
                  </button>
                  <button
                    type="button"
                    className="appr-reject"
                    onClick={() => handleDecide(approval, 'reject')}
                    disabled={actionsDisabled}
                  >
                    <Ban size={16} aria-hidden="true" />
                    驳回
                  </button>

                  {isSubmitted && (
                    <span className="appr-submitted">
                      已提交，等待网关处理…
                    </span>
                  )}
                  {!isSubmitted && isExpired && (
                    <span className="appr-expired-note">
                      已过期，等待网关清扫…
                    </span>
                  )}
                  {!isSubmitted && !isExpired && isSelf && (
                    <span className="appr-warn">
                      执行者不能给自己的任务放行（防自批规则）
                    </span>
                  )}
                </div>
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}
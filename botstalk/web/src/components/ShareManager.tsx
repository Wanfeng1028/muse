import { useCallback, useEffect, useState } from "react";
import { X, Share2, Copy, Trash2 } from "lucide-react";
import {
  issueShareLink,
  listShareLinks,
  revokeShareLink,
  type IssuedShareLink,
  type ShareLinkMeta,
} from "../api";

interface ShareManagerProps {
  room: string;
  nick: string;
  onClose: () => void;
}

function formatDateTime(ms: number): string {
  return new Date(ms).toLocaleString();
}

export default function ShareManager({
  room,
  nick,
  onClose,
}: ShareManagerProps) {
  const [links, setLinks] = useState<ShareLinkMeta[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [ttlHours, setTtlHours] = useState<number>(168);
  const [issuing, setIssuing] = useState(false);
  const [issued, setIssued] = useState<IssuedShareLink | null>(null);

  const [revokingId, setRevokingId] = useState<string | null>(null);

  const issuedUrl = issued
    ? window.location.origin && window.location.origin !== "null"
      ? window.location.origin + issued.share_url
      : issued.share_url
    : "";

  const fetchLinks = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listShareLinks(room, nick);
      setLinks(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [room, nick]);

  useEffect(() => {
    void fetchLinks();
  }, [fetchLinks]);

  const handleIssue = async () => {
    setIssuing(true);
    setError(null);
    try {
      const hours = Math.min(720, Math.max(1, Math.trunc(Number(ttlHours) || 168)));
      const result = await issueShareLink(room, nick, hours);
      setIssued(result);
      await fetchLinks();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setIssuing(false);
    }
  };

  const handleRevoke = async (id: string) => {
    setRevokingId(id);
    setError(null);
    try {
      await revokeShareLink(room, id, nick);
      await fetchLinks();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setRevokingId(null);
    }
  };

  const handleCopy = async () => {
    if (!issued) return;
    try {
      await navigator.clipboard.writeText(issuedUrl);
    } catch {
      // 静默失败
    }
  };

  const forbidden =
    typeof error === "string" && error.includes("ROOM_MANAGE_FORBIDDEN");

  return (
    <div className="appr-panel">
      <div className="appr-head">
        <div className="appr-title">
          <Share2 size={18} />
          分享管理
        </div>
        <button className="appr-close" onClick={onClose} aria-label="关闭">
          <X size={16} />
        </button>
      </div>

      {error && (
        <div className="appr-meta">
          {forbidden ? "只有房主或管理员能管理分享链接" : error}
        </div>
      )}

      <div className="appr-card">
        <div className="appr-meta">
          有效期小时（1–720）
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <input
            type="number"
            value={Number.isFinite(Number(ttlHours)) ? ttlHours : ""}
            onChange={(e) => setTtlHours(Number(e.target.value))}
            min={1}
            max={720}
            style={{ width: 120 }}
          />
          <button
            className="appr-actions"
            disabled={issuing}
            onClick={handleIssue}
          >
            {issuing ? "签发中…" : "签发链接"}
          </button>
        </div>
      </div>

      {issued && (
        <div className="appr-card">
          <div className="appr-meta">
            完整链接：{issuedUrl}
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button className="appr-actions" onClick={handleCopy}>
              <Copy size={14} />
              复制
            </button>
          </div>
          <div className="appr-meta">
            链接只显示这一次，关闭面板后不再显示，列表里只有元数据、没有令牌。
          </div>
        </div>
      )}

      {loading ? (
        <div className="appr-meta">正在加载分享链接…</div>
      ) : links.length === 0 ? (
        <div className="appr-meta">还没有分享链接</div>
      ) : (
        <div className="appr-list">
          {links.map((link) => {
            const isRevoked = link.revoked_at_ms !== null;
            const isExpired = Date.now() >= link.expires_at_ms;
            const isValid = !isRevoked && !isExpired;
            const status = isRevoked
              ? "已撤销"
              : isExpired
                ? "已过期"
                : "有效";

            return (
              <div className="appr-card" key={link.id}>
                <div className="appr-meta">
                  <div>ID：{link.id.slice(0, 8)}</div>
                  <div>创建：{formatDateTime(link.created_at_ms)}</div>
                  <div>到期：{formatDateTime(link.expires_at_ms)}</div>
                  <div>状态：{status}</div>
                </div>
                {isValid && (
                  <div className="appr-actions">
                    <button
                      disabled={revokingId === link.id}
                      onClick={() => handleRevoke(link.id)}
                    >
                      <Trash2 size={14} />
                      {revokingId === link.id ? "撤销中…" : "撤销"}
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

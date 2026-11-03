import { useEffect, useState } from 'react';
import { X, Smartphone } from 'lucide-react';
import { listDevices, revokeDevice, type DeviceMeta } from '../api';

interface Props {
  room: string;
  nick: string;
  onClose: () => void;
}

export default function DevicesPanel({ room, nick, onClose }: Props) {
  const [devices, setDevices] = useState<DeviceMeta[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [revokingId, setRevokingId] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await listDevices(room, nick);
      setDevices(res);
    } catch (e: any) {
      setError(e?.message ?? String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, [room, nick]);

  const handleRevoke = async (deviceId: string) => {
    setRevokingId(deviceId);
    setError('');
    try {
      await revokeDevice(room, deviceId, nick);
      await load();
    } catch (e: any) {
      setError(e?.message ?? String(e));
    } finally {
      setRevokingId(null);
    }
  };

  return (
    <div className="appr-panel">
      <div className="appr-head">
        <span className="appr-title">设备管理</span>
        <button className="appr-close" onClick={onClose} aria-label="关闭">
          <X size={16} />
        </button>
      </div>

      <div className="appr-card">
        <h3>
          <Smartphone size={16} /> 设备列表
        </h3>
        <div className="appr-actions">
          <button onClick={load} disabled={loading}>
            刷新
          </button>
        </div>

        {loading && <div className="appr-meta">加载中…</div>}
        {error && <div className="appr-meta">{error}</div>}

        {!loading && devices.length === 0 && <div className="appr-meta">暂无设备</div>}

        {devices.map((d) => (
          <div className="appr-card" key={d.device_id}>
            <div className="appr-meta">设备：{d.device_id}</div>
            <div className="appr-meta">适配器：{d.adapter_id}</div>
            <div className="appr-meta">接入：{new Date(d.created_at_ms).toLocaleString()}</div>
            <div className="appr-meta">最近活跃：{new Date(d.last_seen_ms).toLocaleString()}</div>
            {d.revoked_at_ms === null ? (
              <div className="appr-meta">状态：正常</div>
            ) : (
              <div className="appr-meta">
                状态：已吊销（{new Date(d.revoked_at_ms).toLocaleString()}）
              </div>
            )}
            {d.revoked_at_ms === null && (
              <div className="appr-actions">
                <button onClick={() => handleRevoke(d.device_id)} disabled={revokingId === d.device_id}>
                  吊销
                </button>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

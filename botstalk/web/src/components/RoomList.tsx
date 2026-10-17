// 房间列表组件：展示房间、创建房间、进入房间
import { useEffect, useState, FormEvent } from 'react';
import { Plus, Gamepad2, Briefcase, LogOut } from 'lucide-react';
import { fetchRooms, createRoom, RoomInfo, RoomType, ROOM_TYPE_LABEL } from '../api';

interface Props {
  nick: string;
  onSelect: (roomId: string) => void;
  onLogout: () => void;
}

export default function RoomList({ nick, onSelect, onLogout }: Props) {
  const [rooms, setRooms] = useState<RoomInfo[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [name, setName] = useState('');
  const [type, setType] = useState<RoomType>('workroom');
  const [topic, setTopic] = useState('');
  const [creating, setCreating] = useState(false);

  const loadRooms = () => {
    setError(null);
    setRooms(null);
    fetchRooms()
      .then((list) => setRooms(list))
      .catch(() => setError('房间列表没拉下来，点重试'));
  };

  useEffect(() => {
    loadRooms();
  }, []);

  const handleCreate = (e: FormEvent) => {
    e.preventDefault();
    if (creating) return;
    setCreating(true);
    setError(null);
    createRoom({
      name: name.trim() || undefined,
      type,
      topic: topic.trim() || undefined,
      owner: nick,
    })
      .then((room) => {
        setShowCreate(false);
        setName('');
        setTopic('');
        setType('workroom');
        setCreating(false);
        onSelect(room.id);
        loadRooms();
      })
      .catch((err: Error) => {
        setCreating(false);
        setError(err.message);
      });
  };

  return (
    <div className="room-list">
      <div className="room-list-panel">
        <div className="room-list-head">
          <h2 className="room-list-title">选个房间进去聊</h2>
          <button className="btn-ghost" type="button" onClick={onLogout} title="换个名字重进">
            <LogOut size={14} strokeWidth={2} />
            <span>换名字</span>
          </button>
        </div>
        <p className="room-list-sub">{nick}，你在大厅里</p>

        {error && (
          <div className="room-err">
            <span>{error}</span>
            <button className="btn-ghost" type="button" onClick={loadRooms}>
              重试
            </button>
          </div>
        )}

        {rooms === null && !error && <div className="room-empty">正在拉房间列表…</div>}

        {rooms !== null && rooms.length === 0 && (
          <div className="room-empty">还没有房间，建一个吧</div>
        )}

        {rooms !== null &&
          rooms.map((room) => (
            <button
              key={room.id}
              className="room-row"
              type="button"
              onClick={() => onSelect(room.id)}
            >
              <span className="room-row-icon">
                {room.type === 'playroom' ? <Gamepad2 size={20} /> : <Briefcase size={20} />}
              </span>
              <span className="room-row-main">
                <span className="room-row-name">{room.name ?? room.id}</span>
                <span className="room-row-id">{room.id}</span>
              </span>
              <span className={`room-badge room-badge-${room.type}`}>
                {ROOM_TYPE_LABEL[room.type]}
              </span>
            </button>
          ))}

        {!showCreate && (
          <button
            className="btn-ghost"
            type="button"
            onClick={() => setShowCreate(true)}
          >
            <Plus size={16} />
            新建房间
          </button>
        )}

        {showCreate && (
          <form className="room-create-form" onSubmit={handleCreate}>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="房间名字，不填就用 id"
            />
            <select value={type} onChange={(e) => setType(e.target.value as RoomType)}>
              <option value="workroom">工作坊</option>
              <option value="playroom">娱乐厅</option>
            </select>
            <input
              type="text"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              placeholder="一句话介绍这个房间"
            />
            <button className="btn-primary" type="submit" disabled={creating}>
              {creating ? '建房中…' : '创建'}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}

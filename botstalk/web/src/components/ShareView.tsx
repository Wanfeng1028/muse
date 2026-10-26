import { useEffect, useState } from "react";
import { fetchShareView, type ShareViewData } from "../api";

export default function ShareView({ token }: { token: string }) {
  const [data, setData] = useState<ShareViewData | null>(null);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    let alive = true;
    setData(null);
    setError(null);
    fetchShareView(token)
      .then((d) => {
        if (alive) setData(d);
      })
      .catch((e: unknown) => {
        if (alive) setError(e instanceof Error ? e : new Error(String(e)));
      });
    return () => {
      alive = false;
    };
  }, [token]);

  if (error) {
    return (
      <section className="room-list">
        <div className="room-list-panel">
          <h2 className="room-list-title">打不开这个分享</h2>
          <p className="room-err">{error.message}</p>
        </div>
      </section>
    );
  }

  if (!data) {
    return (
      <section className="room-list">
        <div className="room-list-panel">
          <h2 className="room-list-title">正在打开分享…</h2>
        </div>
      </section>
    );
  }

  const { room, messages } = data;

  return (
    <section className="room-list">
      <div className="room-list-panel">
        <h2 className="room-list-title">{room.name || room.id}</h2>
        {room.topic ? <p className="room-list-sub">{room.topic}</p> : null}
        <p className="room-list-sub">只读查看 · 不用登录也能看</p>
      </div>
      <div className="room-list-panel">
        {messages.length === 0 ? (
          <p className="room-empty">这个房间还没有消息</p>
        ) : (
          <ul className="room-list">
            {messages.map((m) => {
              const text = m.payload && m.payload.text ? m.payload.text : m.type;
              return (
                <li key={m.id} className="room-list-sub">
                  {m.sender}：{text}
                </li>
              );
            })}
          </ul>
        )}
      </div>
      <div className="room-list-panel">
        <p className="room-list-sub">只读：不能在这里发消息、派活或改房间</p>
      </div>
    </section>
  );
}

import { useCallback, useState } from 'react';
import Join from './components/Join';
import RoomList from './components/RoomList';
import Chat from './components/Chat';

export default function App() {
  const [nick, setNick] = useState<string | null>(null);
  const [roomId, setRoomId] = useState<string | null>(null);
  const [sessionKey, setSessionKey] = useState(0);

  const handleJoin = useCallback((name: string) => {
    setNick(name);
    setRoomId(null);
    setSessionKey((k) => k + 1);
  }, []);

  const handleSelectRoom = useCallback((id: string) => {
    setRoomId(id);
    setSessionKey((k) => k + 1);
  }, []);

  const handleBackToRooms = useCallback(() => {
    setRoomId(null);
  }, []);

  const handleLeave = useCallback(() => {
    setNick(null);
    setRoomId(null);
  }, []);

  if (!nick) return <Join onJoin={handleJoin} />;
  if (!roomId) return <RoomList nick={nick} onSelect={handleSelectRoom} onLogout={handleLeave} />;
  return <Chat key={`${sessionKey}-${roomId}`} nick={nick} room={roomId} onLeave={handleBackToRooms} />;
}

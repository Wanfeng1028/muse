import { useCallback, useState } from 'react';
import Join from './components/Join';
import Chat from './components/Chat';

export default function App() {
  const [nick, setNick] = useState<string | null>(null);
  const [sessionKey, setSessionKey] = useState(0);

  const handleJoin = useCallback((name: string) => {
    setNick(name);
    setSessionKey((k) => k + 1);
  }, []);

  const handleLeave = useCallback(() => {
    setNick(null);
  }, []);

  if (!nick) return <Join onJoin={handleJoin} />;
  return <Chat key={sessionKey} nick={nick} onLeave={handleLeave} />;
}

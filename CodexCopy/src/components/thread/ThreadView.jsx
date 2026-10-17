import { UserMessage, AgentMessage, StreamingMessage } from './Message';

export default function ThreadView({ thread, streaming }) {
  return (
    <div className="thread-scroll">
      <div className="thread-inner">
        {thread.messages.map((m, i) =>
          m.role === 'user'
            ? <UserMessage key={i} text={m.text} />
            : <AgentMessage key={i} msg={m} />
        )}
        {streaming && <StreamingMessage />}
      </div>
    </div>
  );
}

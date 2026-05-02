import { useSession, type ChatSession } from "../hooks/useSession";
import "../styles/ChatSidebar.css";

interface ChatSidebarProps {
  onSelectSession: (sessionId: string) => void;
  onCreateSession: () => void;
  currentSessionId: string | null;
}

export function ChatSidebar({ onSelectSession, onCreateSession, currentSessionId }: ChatSidebarProps) {
  const { sessions, loadingSessions, deleteSession } = useSession();

  const handleDelete = async (e: React.MouseEvent, sessionId: string) => {
    e.stopPropagation();
    const confirmed = window.confirm("Delete this chat session?");
    if (confirmed) {
      await deleteSession(sessionId);
    }
  };

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return "just now";
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;

    return date.toLocaleDateString();
  };

  return (
    <div className="chat-sidebar">
      <button className="chat-new-btn" onClick={onCreateSession}>
        + New Chat
      </button>

      <div className="chat-sessions-list">
        {loadingSessions ? (
          <div className="chat-loading">Loading sessions...</div>
        ) : sessions.length === 0 ? (
          <div className="chat-empty">No chat sessions yet</div>
        ) : (
          sessions.map((session: ChatSession) => (
            <div
              key={session.id}
              className={`chat-session-item ${currentSessionId === session.id ? "active" : ""}`}
              onClick={() => onSelectSession(session.id)}
            >
              <div className="chat-session-content">
                <div className="chat-session-title">{session.title || "Untitled Chat"}</div>
                <div className="chat-session-date">{formatDate(session.updated_at)}</div>
              </div>
              <button
                className="chat-session-delete"
                onClick={(e) => handleDelete(e, session.id)}
                title="Delete session"
              >
                ×
              </button>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

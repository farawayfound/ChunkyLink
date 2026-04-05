import { useState } from "react";
import type { ChatMessage as Msg } from "../types";

interface Props {
  message: Msg;
}

export function ChatMessage({ message }: Props) {
  const isUser = message.role === "user";
  const [thinkingOpen, setThinkingOpen] = useState(false);

  return (
    <div className={`chat-message ${isUser ? "user" : "assistant"}`}>
      <div className="message-role">{isUser ? "You" : "ChunkyLink"}</div>
      {!isUser && message.thinking && (
        <div className="thinking-block">
          <button
            className="thinking-toggle"
            onClick={() => setThinkingOpen((o) => !o)}
          >
            <span className={`thinking-arrow ${thinkingOpen ? "open" : ""}`}>&#9654;</span>
            {" "}Thinking
          </button>
          {thinkingOpen && (
            <div className="thinking-content">{message.thinking}</div>
          )}
        </div>
      )}
      <div className="message-content">{message.content || "\u00A0"}</div>
    </div>
  );
}
